from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.mcp import server as mcp_server  # type: ignore


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _check_source_status() -> None:
    payload = mcp_server.tool_paos_source_status_get()
    _assert("summary" in payload, "source status summary missing")
    _assert("candidate_count" in payload, "source status candidate_count missing")


def _check_interesting_today_latest_insight() -> None:
    payload = mcp_server.tool_paos_source_insight_get(category="ai", limit=3)
    _assert(payload.get("ok") is True, "source insight not ok")
    for item in (payload.get("items") or [])[:3]:
        _assert("title" in item, "insight title missing")
        _assert("reason" in item, "insight reason missing")


def _check_opportunity_scoring() -> None:
    payload = mcp_server.tool_paos_source_recommendation_get(category="ai")
    _assert(payload.get("ok") is True, "source recommendation not ok")
    for item in (payload.get("opportunities") or [])[:3]:
        _assert(item.get("opportunity_score") is not None, "opportunity_score missing")
        _assert("suggested_next_action_draft" in item, "suggested_next_action_draft missing")


def _check_action_draft_and_read_only_boundary() -> None:
    payload = mcp_server.tool_paos_source_action_draft_create(category="ai")
    if not payload.get("ok"):
        return
    summary = str(payload.get("summary") or "")
    action = payload.get("action") or {}
    _assert("No external action was applied." in summary, "missing read-only boundary in summary")
    _assert(action.get("state") in {"proposed", "accepted", "deferred", "rejected"}, "invalid action state")


def main() -> int:
    _check_source_status()
    _check_interesting_today_latest_insight()
    _check_opportunity_scoring()
    _check_action_draft_and_read_only_boundary()
    print("e2e_source_intelligence_handler: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
