from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.mcp.server import tool_paos_agent_memory_candidate_create  # type: ignore


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    payload = tool_paos_agent_memory_candidate_create(
        content="Decision: gunakan validate_commit_readiness runner sebelum status commit-ready.",
        target_agent="codex",
    )
    _assert(payload.get("ok"), "memory candidate create failed")
    candidate = (payload.get("sections") or {}).get("candidate") or {}
    _assert(bool(candidate.get("candidate_id")), "candidate_id missing")
    _assert(str(candidate.get("status") or "") == "candidate", "candidate must remain candidate")
    print("e2e_result_to_memory_candidate_handler: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
