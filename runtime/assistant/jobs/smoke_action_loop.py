from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from assistant.action_loop import (  # type: ignore
    accept_action,
    create_daily_action,
    defer_action,
    list_actions,
    list_events,
    reject_action,
    render_action_update_result,
    resolve_action_reference,
)
from assistant.actions import create_action_draft  # type: ignore
from assistant.mcp.server import (  # type: ignore
    tool_paos_action_event_list,
    tool_paos_action_get,
    tool_paos_action_list,
    tool_paos_action_resolve,
    tool_paos_action_state_transition,
    tool_paos_daily_action_generate,
    tool_paos_runtime_status_get,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    daily = create_daily_action(category="runtime", persist=True, actor="smoke")
    _assert(daily.ok and daily.action is not None, "daily create failed")

    pending = [a for a in list_actions(limit=20) if a.state in {"proposed", "deferred"}]
    _assert(len(pending) >= 1, "pending list empty")

    latest = resolve_action_reference("action terakhir")
    _assert(latest is not None, "latest resolve failed")

    tool_paos_action_list(limit=5)
    tool_paos_action_get(action_id=latest.action_id)
    tool_paos_action_event_list(action_id=latest.action_id)
    tool_paos_daily_action_generate(category="runtime", persist=True)

    tool_pending = tool_paos_action_list(limit=5)
    latest_ids = [x.get("action_id") for x in (tool_pending.get("sections", {}).get("actions") or [])]
    _assert(len(latest_ids) > 0, "mcp list returned empty")
    resolved = tool_paos_action_resolve(reference="nomor 1")
    _assert(bool(resolved.get("ok")), "ordinal resolve failed")

    accepted = accept_action(latest.action_id, actor="smoke", note="accept smoke")
    _assert(accepted.ok and accepted.action and accepted.action.state == "accepted", "accept failed")
    _assert("No external action was applied." in render_action_update_result(accepted), "notice missing")

    rejected_target = create_daily_action(category="runtime", persist=True, actor="smoke").action
    _assert(rejected_target is not None, "reject target missing")
    rejected = reject_action(rejected_target.action_id, actor="smoke", note="reject smoke")
    _assert(rejected.ok and rejected.action and rejected.action.state == "rejected", "reject failed")

    deferred_target = create_daily_action(category="runtime", persist=True, actor="smoke").action
    _assert(deferred_target is not None, "defer target missing")
    deferred = defer_action(deferred_target.action_id, actor="smoke", note="defer smoke")
    _assert(deferred.ok and deferred.action and deferred.action.state == "deferred", "defer failed")

    blocked_draft = create_action_draft(intent="enable hermes gateway and scheduler mutation")
    from assistant.action_loop.service import create_action_from_draft  # type: ignore
    blocked_result = create_action_from_draft(blocked_draft, actor="smoke")
    _assert(blocked_result.ok and blocked_result.action is not None, "blocked action create failed")
    from assistant.action_loop.store import update_state  # type: ignore
    update_state(blocked_result.action.action_id, "blocked", note="blocked for safety")
    blocked_accept = tool_paos_action_state_transition(
        action_id=blocked_result.action.action_id,
        transition="accepted",
        note="should fail",
    )
    _assert(not blocked_accept.get("ok"), "blocked action unexpectedly accepted")

    sched_draft = create_action_draft(intent="scheduler update needed")
    _assert(sched_draft.get("action_class") == "approval_required", "scheduler draft class mismatch")
    _assert(sched_draft.get("applied") is False, "approval_required should remain applied=false")

    events = list_events(limit=50)
    _assert(len(events) > 0, "event log empty")

    accepted_list = list_actions(state="accepted", limit=1)
    _assert(len(accepted_list) >= 1, "latest accepted missing")
    handoff_text = f"Codex handoff: {accepted_list[0].title}\nNo external action was applied."
    _assert("No external action was applied." in handoff_text, "handoff notice missing")

    _assert(not hasattr(sys.modules[__name__], "controlled_write_apply"), "forbidden apply mechanism exists")

    runtime_status = tool_paos_runtime_status_get()
    gateway_status = ((runtime_status.get("sections") or {}).get("hermes_gateway_status"))
    _assert(gateway_status == "stopped_expected", f"gateway status is {gateway_status}")

    print("smoke_action_loop: PASS")
    print("No external action was applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
