from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.mcp.server import tool_paos_agent_next_action_draft  # type: ignore


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    payload = tool_paos_agent_next_action_draft(content="Follow-up: patch failing e2e in bot/commands/assistant_query.py")
    _assert(payload.get("ok"), "next action draft failed")
    draft = (payload.get("sections") or {}).get("draft") or {}
    _assert(bool(draft.get("title")), "draft title missing")
    _assert(str(draft.get("apply_mechanism_available") or "").lower() in {"false", "none", ""} or draft.get("apply_mechanism_available") is False, "draft must stay local-only")
    print("e2e_result_to_action_handler: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
