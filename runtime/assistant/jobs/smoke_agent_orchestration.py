from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.mcp.server import (  # type: ignore
    tool_paos_agent_handoff_create,
    tool_paos_agent_handoff_get,
    tool_paos_agent_handoff_list,
    tool_paos_agent_memory_candidate_create,
    tool_paos_agent_next_action_draft,
    tool_paos_agent_result_review,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    created = tool_paos_agent_handoff_create(target_agent="codex", source="focus now")
    _assert(created.get("ok"), "handoff create failed")
    handoff = (created.get("sections") or {}).get("handoff") or {}
    package = handoff.get("context_package") or {}
    hid = str(handoff.get("handoff_id") or "")
    _assert(bool(hid), "handoff id missing")
    _assert(bool(package.get("task_intent")), "handoff context package missing task_intent")
    _assert(bool(package.get("constraints")), "handoff context package missing constraints")
    _assert(bool(package.get("expected_output_format")), "handoff context package missing expected_output_format")

    listed = tool_paos_agent_handoff_list(limit=3)
    _assert(listed.get("ok"), "handoff list failed")

    loaded = tool_paos_agent_handoff_get(handoff_id=hid)
    _assert(loaded.get("ok"), "handoff get failed")

    review = tool_paos_agent_result_review(
        content="Implemented runtime/assistant/mcp/server.py and bot/commands/assistant_query.py. smoke: PASS",
        target_agent="codex",
        handoff_id=hid,
    )
    _assert(review.get("ok"), "result review failed")
    review_payload = (review.get("sections") or {}).get("review") or {}
    _assert(review_payload.get("classification") in {"accepted", "needs_follow_up", "unsafe", "incomplete"}, "invalid review classification")

    next_draft = tool_paos_agent_next_action_draft(content="Need follow-up for failing e2e logs", handoff_id=hid)
    _assert(next_draft.get("ok"), "next action draft failed")
    _assert(bool(((next_draft.get("sections") or {}).get("draft") or {}).get("title")), "next action draft title missing")

    mem = tool_paos_agent_memory_candidate_create(
        content="Codex report menunjukkan validasi runtime lebih stabil setelah runner standar.",
        handoff_id=hid,
        target_agent="codex",
    )
    _assert(mem.get("ok"), "agent memory candidate failed")
    _assert(bool(((mem.get("sections") or {}).get("candidate") or {}).get("candidate_id")), "memory candidate id missing")

    print("smoke_agent_orchestration: PASS")
    print("No external action was applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
