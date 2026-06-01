from __future__ import annotations

import json
import os
import re
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
    if raw in {"cowork", "claudecowork", "external", "agent_lain"}:
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
            lines.append(content[:150])
    return lines


def _insight_summary(goal: str) -> list[str]:
    payload = get_source_insights(category="ai", limit=3)
    items = payload.get("items") or []
    out: list[str] = []
    lowered_goal = goal.lower()
    for item in items:
        title = str(item.get("title") or "").strip()
        reason = str(item.get("reason") or "").strip()
        blob = f"{title} {reason}".lower()
        if lowered_goal and not any(token in blob for token in lowered_goal.split()[:4]):
            continue
        line = title[:120] if title else reason[:120]
        if line:
            out.append(line)
    if out:
        return out[:2]

    fallback: list[str] = []
    for item in items[:2]:
        title = str(item.get("title") or item.get("reason") or "").strip()
        if title:
            fallback.append(title[:120])
    return fallback


def _is_coding_goal(goal: str, source_focus: str) -> bool:
    blob = f"{goal} {source_focus}".lower()
    return any(token in blob for token in ("repo", "code", "bug", "patch", "python", ".py", "test", "e2e", "smoke"))


def _compact_unique(items: list[str], limit: int = 4, max_chars: int = 150) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in items:
        text = " ".join(str(value or "").split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:max_chars])
        if len(out) >= limit:
            break
    return out


def _context_package(
    target_agent: str,
    source_focus: str,
    task_goal: str,
    source_action_id: str | None,
    focus: dict[str, Any],
) -> dict[str, Any]:
    memory_points = _compact_unique(_memory_summary(task_goal), limit=4)
    insight_points = _compact_unique(_insight_summary(task_goal), limit=2, max_chars=120)
    focus_steps = _compact_unique([str(x) for x in (focus.get("steps") or [])], limit=4, max_chars=140)
    is_coding = _is_coding_goal(task_goal, source_focus)

    validation_commands = [
        "git status -sb",
        "git diff --check",
    ]
    if is_coding:
        validation_commands.extend(
            [
                "python3 -m py_compile <changed_python_files>",
                "python3 runtime/assistant/jobs/validate_commit_readiness.py",
            ]
        )

    return {
        "task_intent": task_goal[:220],
        "current_focus_state": {
            "action_id": source_action_id,
            "title": source_focus[:160],
            "state": str(focus.get("state") or "unknown"),
            "steps": focus_steps,
            "accepted_means": "chosen focus, not execution",
        },
        "evidence": {
            "paos_context_summary": str(focus.get("summary") or source_focus)[:220],
            "memory_points": memory_points,
            "source_intelligence_points": insight_points,
        },
        "constraints": [
            "No auto-dispatch to Codex/Claude/Hermes.",
            "No auto-commit/push/PR/merge/apply.",
            "No GitHub mutation and no scheduler/systemd mutation.",
            "No controlled execution.",
            "No external action was applied.",
        ],
        "expected_output_format": [
            "Summary",
            "Files changed",
            "Validation results",
            "Risk/blockers",
            "Next safe step",
        ],
        "validation_commands": validation_commands,
        "is_coding_task": is_coding,
        "compact_mode": True,
    }


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

    normalized_target = _normalize_agent(target_agent)
    focus = _latest_focus()
    source_action_id = str(action_id or focus.get("action_id") or "").strip() or None
    source_focus = str(source or focus.get("title") or "").strip() or "Fokus belum tersedia"
    task_goal = str(goal or focus.get("summary") or "Lanjutkan fokus runtime PAOS saat ini").strip()

    package = _context_package(
        target_agent=normalized_target,
        source_focus=source_focus,
        task_goal=task_goal,
        source_action_id=source_action_id,
        focus=focus,
    )

    payload = {
        "handoff_id": _make_handoff_id(),
        "target_agent": normalized_target,
        "source_action_id": source_action_id,
        "source_focus": source_focus,
        "goal": task_goal,
        "context_package": package,
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
        "safety_constraints": package["constraints"],
        "expected_output_format": package["expected_output_format"],
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


def _build_agent_specific_guidance(target: str, package: dict[str, Any]) -> list[str]:
    if target == "codex":
        return [
            "Utamakan inspection + edit pada file repo yang relevan saja.",
            "Jalankan validation commands yang disediakan sebelum final report.",
            "Sertakan ringkasan diff behavior before/after secara teknis.",
        ]
    if target == "claude_code":
        return [
            "Fokus pada reasoning, risk review, dan rencana implementasi yang teruji.",
            "Jika ada perubahan kode, tetap laporkan validasi dan risiko regresi.",
            "Pastikan rekomendasi tetap local-safe dan tidak auto-apply.",
        ]
    if target == "hermes":
        return [
            "Buat orchestration summary yang ringkas untuk Telegram UX.",
            "Gunakan evidence top-only dan hindari tool-internal leakage.",
            "Pastikan fallback safe-step jelas saat output agent belum siap apply.",
        ]
    if target == "claude_cowork":
        return [
            "Siapkan prompt lintas-agent yang cukup konteks tapi tetap compact.",
            "Prioritaskan outcome, batas safety, dan format hasil yang bisa direview cepat.",
            "Jangan asumsikan akses mutation; tetap draft/manual only.",
        ]
    return [
        "Selesaikan analisis/implementasi sesuai scope.",
        "Laporkan validasi dan blocker dengan jelas.",
        "Tetap patuhi seluruh boundary safety.",
    ]


def _build_prompt(handoff: dict[str, Any]) -> str:
    target = str(handoff.get("target_agent") or "generic")
    goal = str(handoff.get("goal") or "")
    source_focus = str(handoff.get("source_focus") or "")
    action_id = str(handoff.get("source_action_id") or "-")
    package = handoff.get("context_package") or {}

    evidence = (package.get("evidence") or {}) if isinstance(package, dict) else {}
    memory_points = evidence.get("memory_points") or []
    source_points = evidence.get("source_intelligence_points") or []
    constraints = package.get("constraints") or []
    expected = package.get("expected_output_format") or []
    validation_commands = package.get("validation_commands") or []

    lines = [
        f"Role: Anda adalah {target} untuk handoff PAOS Runtime (manual draft prompt).",
        f"Task intent: {goal}",
        f"Current focus: {source_focus}",
        f"Source action id: {action_id}",
        "",
        "PAOS evidence (compact):",
        f"- Context: {str(evidence.get('paos_context_summary') or '-')}",
    ]
    lines.extend([f"- Memory: {x}" for x in memory_points] or ["- Memory: tidak ada poin kuat."])
    lines.extend([f"- Intelligence: {x}" for x in source_points] or ["- Intelligence: tidak ada insight relevan."])

    lines.extend(["", "Agent-specific guidance:"])
    lines.extend([f"- {x}" for x in _build_agent_specific_guidance(target, package)])

    lines.extend(["", "Safety constraints:"])
    lines.extend([f"- {x}" for x in constraints])

    lines.extend(["", "Validation commands (jalankan jika relevan):"])
    lines.extend([f"- {x}" for x in validation_commands] or ["- Tidak ada command khusus."])

    lines.extend(["", "Expected output format:"])
    lines.extend([f"- {x}" for x in expected])

    lines.extend(
        [
            "",
            "Instruksi kerja wajib:",
            "- Handoff ini manual/draft only, bukan dispatch.",
            "- Jangan commit/push/PR/merge/apply kecuali diminta eksplisit.",
            "- Jika hasil belum aman, berikan next safe action draft.",
            "- Selalu tutup dengan: No external action was applied.",
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


def _review_classification(
    *,
    validation_failed: bool,
    safety_violations: list[str],
    goal_met: bool,
    validations_passed: bool,
    files: list[str],
) -> str:
    if safety_violations:
        return "unsafe"
    if validation_failed:
        return "needs_follow_up"
    if not files or not validations_passed:
        return "incomplete"
    if goal_met and validations_passed:
        return "accepted"
    return "needs_follow_up"


def review_result(content: str, target_agent: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
    _ensure_store()
    text = str(content or "").strip()
    lowered = text.lower()
    files = _extract_files(text)

    goal_met = any(x in lowered for x in ("done", "completed", "selesai", "implemented", "pass", "beres"))
    validations_passed = any(x in lowered for x in ("all tests passed", "smoke: pass", "e2e", "pytest", "pass"))
    validation_failed = any(x in lowered for x in ("fail", "failed", "error", "traceback"))

    safety_violations: list[str] = []
    for token, reason in (
        ("git push", "Mengandung indikasi push remote."),
        ("pull request", "Mengandung indikasi PR/GitHub mutation."),
        ("create issue", "Mengandung indikasi create issue."),
        ("systemctl", "Mengandung indikasi mutasi service/systemd."),
        ("crontab", "Mengandung indikasi mutasi scheduler."),
        ("enable hermes gateway", "Mengandung indikasi enable gateway."),
        ("auto-dispatch", "Mengandung indikasi auto-dispatch external agent."),
        ("controlled execution", "Mengandung indikasi controlled execution."),
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

    classification = _review_classification(
        validation_failed=validation_failed,
        safety_violations=safety_violations,
        goal_met=goal_met,
        validations_passed=validations_passed,
        files=files,
    )

    commit_ready = classification == "accepted"
    next_safe_step = "Patch blocker utama, lalu ulangi smoke/E2E yang relevan."
    if classification == "accepted":
        next_safe_step = "Lanjutkan ke commit-readiness validation runner lokal."
    elif classification == "unsafe":
        next_safe_step = "Batalkan langkah unsafe, lalu ulang dari draft-only plan yang sesuai boundary."

    review = {
        "review_id": f"review-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}",
        "target_agent": _normalize_agent(target_agent),
        "handoff_id": str(handoff_id or "").strip() or None,
        "classification": classification,
        "goal_met": goal_met,
        "files_changed": files,
        "validations_passed_signal": validations_passed,
        "validation_failed_signal": validation_failed,
        "safety_violations": safety_violations,
        "missing_tests": not validations_passed,
        "runtime_artifact_risk": any(x in lowered for x in ("actions.jsonl", "events.jsonl", "local.jsonl", "mnemosyne-data")),
        "stale_wording_risk": "todo" in lowered or "tbd" in lowered,
        "commit_readiness": "ready" if commit_ready else "not_ready",
        "next_safe_step": next_safe_step,
        "status": "reviewed",
        "created_at": _now_iso(),
        "notice": "No external action was applied.",
        "blockers": blockers,
        "compact_evidence": {
            "files_top": files[:3],
            "safety_flags": safety_violations[:2],
            "validation_status": "pass" if validations_passed and not validation_failed else "needs_follow_up",
        },
    }
    _append_jsonl(_reviews_path(), review)
    return {"ok": True, "review": review, "summary": "Agent result direview secara lokal."}


def draft_next_action_from_result(content: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
    signal = str(content or "")[:280]
    intent = signal or "Lanjutkan perbaikan dari hasil review agent terbaru"
    draft = create_action_draft(intent=intent, target="local-action-loop", category="runtime")
    draft["summary"] = str(draft.get("summary") or "")[:220]
    draft["notice"] = "No external action was applied."
    return {
        "ok": True,
        "handoff_id": str(handoff_id or "").strip() or None,
        "draft": draft,
        "summary": "Draft next action dibuat (local-only).",
        "notice": "No external action was applied.",
    }


def _candidate_memory_type(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("decision", "diputuskan", "decided", "keputusan")):
        return "decision"
    if any(token in lowered for token in ("fact", "fakta", "state", "status")):
        return "project_fact"
    return "project_fact"


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
    elif src == "hermes":
        source_type = "hermes_report"

    result = create_candidate(
        content=compact,
        memory_type=_candidate_memory_type(compact),
        source_type=source_type,
        source_ref=f"handoff:{str(handoff_id or '-')}:{src}",
        evidence_summary=f"Agent result summary: {compact[:160]}",
        confidence=0.75,
    )
    return {
        "ok": bool(result.get("ok")),
        "candidate": result.get("candidate"),
        "summary": "Memory candidate dibuat dari hasil agent (belum durable write).",
        "notice": "No external action was applied.",
    }
