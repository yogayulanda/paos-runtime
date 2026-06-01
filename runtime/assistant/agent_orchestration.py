from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from assistant.action_loop import list_actions
from assistant.actions import create_action_draft
from assistant.memory import create_candidate, memory_relevant_get
from assistant.source_intelligence import get_source_insights

HandoffStatus = Literal["draft", "ready", "sent_manual", "result_received", "reviewed", "closed"]
_ALLOWED_STATUSES: set[str] = {"draft", "ready", "sent_manual", "result_received", "reviewed", "closed"}
_ALLOWED_AGENTS: set[str] = {"codex", "claude_code", "claude_cowork", "hermes", "generic"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _store_dir() -> Path:
    override = str(os.getenv("PAOS_AGENT_ORCH_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "assistant" / "agent-orchestration"


def _handoffs_path() -> Path:
    return _store_dir() / "handoffs.jsonl"


def _reviews_path() -> Path:
    return _store_dir() / "reviews.jsonl"


def _ensure_store() -> None:
    root = _store_dir()
    root.mkdir(parents=True, exist_ok=True)
    for path in (_handoffs_path(), _reviews_path()):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _normalize_agent(target_agent: str | None) -> str:
    raw = str(target_agent or "generic").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"claude", "claudecode"}:
        raw = "claude_code"
    if raw in {"cowork", "claudecowork"}:
        raw = "claude_cowork"
    if raw not in _ALLOWED_AGENTS:
        return "generic"
    return raw


def _latest_focus() -> dict[str, Any]:
    accepted = list_actions(state="accepted", limit=1, remember_list=False)
    if accepted:
        item = accepted[0]
        return {
            "action_id": item.action_id,
            "title": item.title,
            "summary": item.summary,
            "steps": item.steps[:5],
            "state": item.state,
        }
    proposed = list_actions(state="proposed", limit=1, remember_list=False)
    if proposed:
        item = proposed[0]
        return {
            "action_id": item.action_id,
            "title": item.title,
            "summary": item.summary,
            "steps": item.steps[:5],
            "state": item.state,
        }
    return {}


def _memory_summary(goal: str) -> list[str]:
    payload = memory_relevant_get(query=goal or "PAOS runtime", limit=4)
    items = payload.get("items") or []
    lines: list[str] = []
    for item in items[:4]:
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(content[:160])
    return lines


def _insight_summary() -> list[str]:
    payload = get_source_insights(category="ai", limit=2)
    items = payload.get("items") or []
    out: list[str] = []
    for item in items[:2]:
        title = str(item.get("title") or item.get("summary") or "").strip()
        if title:
            out.append(title[:160])
    return out


def _make_handoff_id() -> str:
    return f"handoff-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}"


def _handoff_map() -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl(_handoffs_path()):
        hid = str(row.get("handoff_id") or "").strip()
        if hid:
            by_id[hid] = row
    return by_id


def create_handoff(
    *,
    target_agent: str | None = None,
    source: str | None = None,
    action_id: str | None = None,
    goal: str | None = None,
    category: str | None = None,
    status: str = "draft",
) -> dict[str, Any]:
    _ensure_store()
    normalized_status = str(status or "draft").strip().lower()
    if normalized_status not in _ALLOWED_STATUSES:
        normalized_status = "draft"

    focus = _latest_focus()
    source_action_id = str(action_id or focus.get("action_id") or "").strip() or None
    source_focus = str(source or focus.get("title") or "").strip() or "Fokus belum tersedia"
    task_goal = str(goal or focus.get("summary") or "Lanjutkan fokus runtime PAOS saat ini").strip()

    payload = {
        "handoff_id": _make_handoff_id(),
        "target_agent": _normalize_agent(target_agent),
        "source_action_id": source_action_id,
        "source_focus": source_focus,
        "goal": task_goal,
        "context_summary": str(focus.get("summary") or source_focus)[:240],
        "relevant_memory_summary": _memory_summary(task_goal),
        "source_evidence_summary": _insight_summary(),
        "acceptance_criteria": [
            "Perubahan hanya di scope file yang relevan.",
            "Tidak ada commit/push/PR/issue.",
            "Semua validasi lokal yang relevan dijalankan dan dilaporkan.",
            "No external action was applied.",
        ],
        "validation_requirements": [
            "Jalankan smoke/E2E terkait perubahan.",
            "Laporkan hasil pass/fail + blocker secara eksplisit.",
            "Sebutkan file yang diubah.",
        ],
        "safety_constraints": [
            "Dilarang mutasi GitHub/repo remote/scheduler/gateway.",
            "Tidak menulis memory durable tanpa approval eksplisit.",
            "Tidak mutasi di luar scope task.",
        ],
        "expected_output_format": [
            "Summary",
            "Files changed",
            "Validation results",
            "Risk/blockers",
            "Next safe step",
        ],
        "category": str(category or "runtime"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": normalized_status,
        "notice": "No external action was applied.",
    }
    _append_jsonl(_handoffs_path(), payload)
    return {"ok": True, "handoff": payload, "notice": "No external action was applied."}


def get_handoff(handoff_id: str | None = None) -> dict[str, Any]:
    _ensure_store()
    handoffs = _handoff_map()
    if handoff_id:
        item = handoffs.get(str(handoff_id).strip())
        if not item:
            return {"ok": False, "errors": ["handoff_not_found"]}
        return {"ok": True, "handoff": item}
    if not handoffs:
        return {"ok": True, "handoff": None}
    latest = sorted(handoffs.values(), key=lambda x: str(x.get("updated_at") or ""), reverse=True)[0]
    return {"ok": True, "handoff": latest}


def list_handoffs(status: str | None = None, limit: int = 10) -> dict[str, Any]:
    _ensure_store()
    items = sorted(_handoff_map().values(), key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    if status:
        st = str(status).strip().lower()
        items = [x for x in items if str(x.get("status") or "").lower() == st]
    return {"ok": True, "items": items[: max(1, int(limit))]}


def _build_prompt(handoff: dict[str, Any]) -> str:
    target = str(handoff.get("target_agent") or "generic")
    goal = str(handoff.get("goal") or "")
    source_focus = str(handoff.get("source_focus") or "")
    action_id = str(handoff.get("source_action_id") or "-")
    mem = handoff.get("relevant_memory_summary") or []
    evidence = handoff.get("source_evidence_summary") or []
    criteria = handoff.get("acceptance_criteria") or []
    validations = handoff.get("validation_requirements") or []
    safety = handoff.get("safety_constraints") or []

    lines = [
        f"Role: Anda adalah {target} yang membantu implementasi PAOS Runtime.",
        f"Task goal: {goal}",
        f"Source focus: {source_focus}",
        f"Source action id: {action_id}",
        "",
        "Context memory relevan:",
    ]
    lines.extend([f"- {x}" for x in mem] or ["- Tidak ada memory relevan yang kuat."])
    lines.extend(["", "Source intelligence/evidence:"])
    lines.extend([f"- {x}" for x in evidence] or ["- Tidak ada insight tambahan."])
    lines.extend(["", "Acceptance criteria:"])
    lines.extend([f"- {x}" for x in criteria])
    lines.extend(["", "Validation requirements:"])
    lines.extend([f"- {x}" for x in validations])
    lines.extend(["", "Safety constraints:"])
    lines.extend([f"- {x}" for x in safety])
    lines.extend(
        [
            "",
            "Instruksi kerja wajib:",
            "- Inspect file terkait sebelum ubah apa pun.",
            "- Implement atau analisis sesuai scope secara lengkap.",
            "- Jalankan test/validation yang relevan dan self-review hasil.",
            "- Patch issue obvious sebelum final report.",
            "- Jelaskan blocker secara spesifik jika ada.",
            "- Jangan meminta user menjalankan routine validation.",
            "- Jangan commit/push kecuali diminta eksplisit.",
            "",
            "Format output:",
            "1. Summary",
            "2. Files changed",
            "3. Validations run (pass/fail)",
            "4. Blockers/Risks",
            "5. Next safe step",
        ]
    )
    return "\n".join(lines).strip()


def handoff_prompt(target_agent: str | None = None, source: str | None = None, action_id: str | None = None, category: str | None = None) -> dict[str, Any]:
    created = create_handoff(target_agent=target_agent, source=source, action_id=action_id, category=category, status="draft")
    handoff = created.get("handoff") or {}
    prompt = _build_prompt(handoff)
    return {
        "ok": True,
        "handoff": handoff,
        "prompt": prompt,
        "summary": "Handoff dibuat sebagai draft/manual prompt.",
        "notice": "No external action was applied.",
    }


def _extract_files(content: str) -> list[str]:
    hits = re.findall(r"([A-Za-z0-9_./-]+\.(?:py|md|yml|yaml|json|sh|txt))", content)
    out: list[str] = []
    for item in hits:
        if item not in out:
            out.append(item)
    return out[:20]


def review_result(content: str, target_agent: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
    _ensure_store()
    text = str(content or "").strip()
    lowered = text.lower()
    files = _extract_files(text)

    goal_met = any(x in lowered for x in ("done", "completed", "selesai", "implemented", "pass"))
    validations_passed = any(x in lowered for x in ("all tests passed", "pass", "smoke: pass", "e2e", "pytest"))
    validation_failed = any(x in lowered for x in ("fail", "failed", "error", "traceback"))
    safety_violations: list[str] = []
    for token, reason in (
        ("git push", "Mengandung indikasi push remote."),
        ("pull request", "Mengandung indikasi PR/GitHub mutation."),
        ("create issue", "Mengandung indikasi create issue."),
        ("systemctl", "Mengandung indikasi mutasi service/systemd."),
        ("crontab", "Mengandung indikasi mutasi scheduler."),
        ("enable hermes gateway", "Mengandung indikasi enable gateway."),
    ):
        if token in lowered:
            safety_violations.append(reason)

    blockers: list[str] = []
    if validation_failed:
        blockers.append("Ada indikasi validation gagal/error yang perlu ditangani.")
    if not files:
        blockers.append("Report belum menyebut file yang diperiksa/diubah.")
    if not validations_passed:
        blockers.append("Report belum menunjukkan validation pass yang memadai.")

    commit_ready = bool(goal_met and validations_passed and not validation_failed and not safety_violations)

    review = {
        "review_id": f"review-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}",
        "target_agent": _normalize_agent(target_agent),
        "handoff_id": str(handoff_id or "").strip() or None,
        "goal_met": goal_met,
        "files_changed": files,
        "validations_passed_signal": validations_passed,
        "validation_failed_signal": validation_failed,
        "safety_violations": safety_violations,
        "missing_tests": not validations_passed,
        "runtime_artifact_risk": any(x in lowered for x in ("actions.jsonl", "events.jsonl", "local.jsonl", "mnemosyne-data")),
        "stale_wording_risk": "todo" in lowered or "tbd" in lowered,
        "commit_readiness": "ready" if commit_ready else "not_ready",
        "next_safe_step": "Lanjutkan ke commit-readiness validation runner lokal." if commit_ready else "Patch blocker utama, lalu ulangi smoke/E2E yang relevan.",
        "status": "reviewed",
        "created_at": _now_iso(),
        "notice": "No external action was applied.",
        "blockers": blockers,
    }
    _append_jsonl(_reviews_path(), review)
    return {"ok": True, "review": review, "summary": "Agent result direview secara lokal."}


def draft_next_action_from_result(content: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
    signal = str(content or "")[:280]
    intent = signal or "Lanjutkan perbaikan dari hasil review agent terbaru"
    draft = create_action_draft(intent=intent, target="local-action-loop", category="runtime")
    return {
        "ok": True,
        "handoff_id": str(handoff_id or "").strip() or None,
        "draft": draft,
        "summary": "Draft next action dibuat (local-only).",
        "notice": "No external action was applied.",
    }


def create_memory_candidate_from_result(content: str | None = None, handoff_id: str | None = None, target_agent: str | None = None) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return {"ok": False, "errors": ["content_empty"]}
    compact = text[:220]
    src = _normalize_agent(target_agent)
    source_type = "agent_report"
    if src == "codex":
        source_type = "codex_report"
    elif src.startswith("claude"):
        source_type = "claude_report"

    result = create_candidate(
        content=compact,
        memory_type="project_fact",
        source_type=source_type,
        source_ref=f"handoff:{str(handoff_id or '-')}:{src}",
        evidence_summary=f"Agent result summary: {compact[:160]}",
        confidence=0.75,
    )
    return {
        "ok": bool(result.get("ok")),
        "candidate": result.get("result"),
        "summary": "Memory candidate dibuat dari hasil agent (belum durable write).",
        "notice": "No external action was applied.",
    }
