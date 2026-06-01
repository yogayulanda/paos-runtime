from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.mcp.server import tool_paos_agent_result_review  # type: ignore


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    safe = tool_paos_agent_result_review(content="Updated runtime/assistant/agent_orchestration.py and smoke: PASS", target_agent="codex")
    _assert(safe.get("ok"), "safe review failed")
    review = (safe.get("sections") or {}).get("review") or {}
    _assert(review.get("classification") in {"accepted", "needs_follow_up", "incomplete"}, "unexpected safe classification")

    unsafe = tool_paos_agent_result_review(content="Implemented and git push + pull request dibuat", target_agent="codex")
    _assert(unsafe.get("ok"), "unsafe review failed")
    review_unsafe = (unsafe.get("sections") or {}).get("review") or {}
    _assert(review_unsafe.get("classification") == "unsafe", "unsafe classification not detected")
    print("e2e_result_review_handler: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
