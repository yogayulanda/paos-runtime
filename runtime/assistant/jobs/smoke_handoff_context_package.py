from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.mcp.server import tool_paos_agent_handoff_create  # type: ignore


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    payload = tool_paos_agent_handoff_create(target_agent="codex", source="upgrade orchestration loop")
    _assert(payload.get("ok"), "handoff create failed")
    handoff = (payload.get("sections") or {}).get("handoff") or {}
    package = handoff.get("context_package") or {}
    _assert(package.get("task_intent"), "missing task_intent")
    _assert((package.get("evidence") or {}).get("memory_points") is not None, "missing memory evidence")
    _assert((package.get("evidence") or {}).get("source_intelligence_points") is not None, "missing source evidence")
    _assert(package.get("validation_commands"), "missing validation_commands")
    _assert("No external action was applied." in str(handoff.get("notice") or ""), "missing boundary notice")
    print("smoke_handoff_context_package: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
