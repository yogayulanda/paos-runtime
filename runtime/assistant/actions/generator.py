from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .classifier import classify_action_intent
from .models import ActionDraft, ActionPolicy, DraftKind


def _resolve_latest_file(root_dir: Path, filename: str) -> Path | None:
    if not root_dir.exists() or not root_dir.is_dir():
        return None
    candidates = sorted(
        [path for path in root_dir.glob(f"*/{filename}") if path.is_file()],
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _evidence_snapshot() -> dict[str, Any]:
    root = _runtime_root()
    brief_path = _resolve_latest_file(root / "assistant" / "briefs", "assistant-brief.json")
    opportunities_path = _resolve_latest_file(root / "assistant" / "opportunities", "opportunities.json")
    context_path = _resolve_latest_file(root / "assistant" / "context", "assistant-context.json")
    brief = _read_json(brief_path)
    opps = _read_json(opportunities_path)
    context = _read_json(context_path)
    return {
        "artifact_dates": {
            "brief": brief_path.parent.name if brief_path else None,
            "opportunities": opportunities_path.parent.name if opportunities_path else None,
            "context": context_path.parent.name if context_path else None,
        },
        "focus_today": str(brief.get("focus_today") or "").strip() if isinstance(brief, dict) else "",
        "suggested_next_action": str(brief.get("suggested_next_action") or "").strip() if isinstance(brief, dict) else "",
        "top_opportunities": [
            str(item.get("title") or "").strip()
            for item in (opps.get("opportunities") or [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ][:3],
        "context_decisions": [
            str(x).strip()
            for x in (((context.get("sections") or {}).get("decisions") or []) if isinstance(context, dict) else [])
            if str(x).strip()
        ][:3],
    }


def _draft_id(kind: DraftKind) -> str:
    date_part = datetime.now().strftime("%Y%m%d")
    return f"draft-{kind}-{date_part}-{uuid4().hex[:8]}"


def get_action_policy() -> dict[str, Any]:
    return ActionPolicy().to_dict()


def create_action_draft(intent: str, target: str | None = None, category: str | None = None) -> dict[str, Any]:
    classification = classify_action_intent(intent=intent, target=target, category=category)
    evidence = _evidence_snapshot()
    normalized = str(intent or "").strip().lower()

    kind: DraftKind = "implementation_plan"
    if "daily" in normalized:
        kind = "daily"
    elif "handoff" in normalized:
        kind = "handoff"
    elif "memory" in normalized or "promot" in normalized:
        kind = "memory_promotion"

    steps: list[str]
    title: str
    summary: str
    approval_payload: dict[str, Any] | None = None
    blocked_reason: str | None = None
    warnings: list[str] = []

    if classification.action_class == "blocked":
        title = "Blocked Action"
        summary = "Permintaan diblokir oleh kebijakan keamanan Phase 4."
        blocked_reason = classification.reason
        steps = ["Permintaan ini tidak dapat disusun menjadi aksi yang aman."]
    elif classification.action_class == "approval_required":
        title = "Approval-Required Draft"
        summary = "Permintaan termasuk mutation-like action. Hanya approval payload yang disiapkan."
        steps = [
            "Review evidence dan ruang lingkup perubahan.",
            "Review risk dan dampak operasi.",
            "Minta approval manusia di luar runtime.",
        ]
        approval_payload = {
            "intent": intent,
            "target": target,
            "category": category,
            "classification": classification.to_dict(),
            "requested_operation": "mutation_like",
            "apply_enabled": False,
        }
        warnings.append("No apply path is provided in Phase 4.")
    elif kind == "daily":
        title = "Draft aksi harian"
        summary = "Draft prioritas harian generik dari evidence terbaru; belum otomatis jadi fokus utama."
        focus = evidence.get("focus_today") or "Belum ada focus_today."
        top_opp = (evidence.get("top_opportunities") or [])[:2]
        steps = [f"Fokus: {focus}", *[f"Prioritas: {item}" for item in top_opp], "Validasi output lewat /daily atau paos_daily_get."]
    elif kind == "handoff":
        dst = str(target or "generic").strip().lower() or "generic"
        title = "Handoff Draft"
        summary = f"Draft handoff untuk {dst}."
        steps = [
            f"Target assistant: {dst}",
            f"Current focus: {evidence.get('focus_today') or 'n/a'}",
            f"Next action: {evidence.get('suggested_next_action') or 'n/a'}",
            "Tidak ada eksekusi otomatis; hanya bahan handoff.",
        ]
    elif kind == "memory_promotion":
        title = "Memory Promotion Suggestion Draft"
        summary = "Saran promosi memory berbasis context decisions."
        decisions = evidence.get("context_decisions") or []
        steps = [f"Candidate: {item}" for item in decisions] or ["Belum ada candidate decisions yang cukup kuat."]
        steps.append("Review manual sebelum promosi memory.")
    else:
        title = "Next Implementation Plan Draft"
        summary = "Draft rencana implementasi berikutnya tanpa mutation."
        steps = [
            "Verifikasi status runtime + context health.",
            "Turunkan scope kecil untuk perubahan berikutnya.",
            "Tetapkan validasi berbasis read-only tools.",
        ]

    draft = ActionDraft(
        draft_id=_draft_id(kind),
        kind=kind,
        action_class=classification.action_class,
        title=title,
        summary=summary,
        steps=steps,
        evidence=evidence,
        approval_payload=approval_payload,
        blocked_reason=blocked_reason,
        warnings=warnings,
    )
    payload = draft.to_dict()
    payload["classification"] = classification.to_dict()
    return payload
