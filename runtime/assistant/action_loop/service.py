from __future__ import annotations

from typing import Any

from .daily import generate_daily_action
from .models import ActionEvent, ActionLoopResult, ActionRecord, ActionState, make_id, now_iso
from .store import append_action, append_event, get_action as store_get_action, list_actions as store_list_actions, load_index, rebuild_index, save_index, update_state as store_update_state

TRANSITIONS: dict[ActionState, set[ActionState]] = {
    "proposed": {"accepted", "rejected", "deferred", "expired", "blocked"},
    "accepted": {"deferred", "expired", "blocked"},
    "rejected": {"proposed"},
    "deferred": {"accepted", "rejected", "expired", "blocked"},
    "expired": set(),
    "blocked": set(),
}


def _record_event(action: ActionRecord, event_type: str, actor: str = "hermes", note: str = "") -> ActionEvent:
    event = ActionEvent(
        event_id=make_id("event"),
        action_id=action.action_id,
        event_type=event_type,
        created_at=now_iso(),
        actor=actor,
        note=note,
        snapshot=action.to_dict(),
    )
    append_event(event)
    return event


def _touch_index(action: ActionRecord | None = None, listed_ids: list[str] | None = None) -> dict[str, Any]:
    idx = load_index()
    if action:
        idx["latest_created_action_id"] = action.action_id
        if action.state == "accepted":
            idx["latest_accepted_action_id"] = action.action_id
        if action.state == "deferred":
            idx["latest_deferred_action_id"] = action.action_id
    if listed_ids is not None:
        idx["latest_listed_action_ids"] = listed_ids
    return save_index(idx)


def create_action_from_draft(draft: dict[str, Any], actor: str = "hermes") -> ActionLoopResult:
    action = ActionRecord(
        action_id=make_id("action"),
        title=str(draft.get("title") or "Action Draft"),
        summary=str(draft.get("summary") or ""),
        steps=[str(x) for x in (draft.get("steps") or [])],
        state="proposed",
        source="draft",
        category=str(draft.get("category") or "runtime"),
        tags=[str(draft.get("kind") or "draft"), str(draft.get("action_class") or "draft_only")],
        evidence={"draft": draft},
    )
    append_action(action)
    event = _record_event(action, "created", actor=actor, note="created from draft")
    _touch_index(action=action)
    return ActionLoopResult(ok=True, message="Action draft persisted.", action=action, events=[event])


def create_daily_action(category: str = "runtime", persist: bool = True, actor: str = "hermes") -> ActionLoopResult:
    action = generate_daily_action(category=category, persist=persist)
    if persist:
        append_action(action)
        event = _record_event(action, "created", actor=actor, note="daily action generated")
        _touch_index(action=action)
        return ActionLoopResult(ok=True, message="Daily action created.", action=action, events=[event])
    return ActionLoopResult(ok=True, message="Daily action generated (not persisted).", action=action)


def list_actions(state: ActionState | None = None, limit: int = 20, remember_list: bool = True) -> list[ActionRecord]:
    actions = store_list_actions(state=state, limit=limit)
    if remember_list:
        _touch_index(listed_ids=[item.action_id for item in actions])
    return actions


def get_action(action_id: str) -> ActionRecord | None:
    return store_get_action(action_id)


def _transition(action_id: str, new_state: ActionState, actor: str = "hermes", note: str = "") -> ActionLoopResult:
    current = store_get_action(action_id)
    if not current:
        return ActionLoopResult(ok=False, message="Action not found.", errors=["action_not_found"])
    if current.state == "blocked" and new_state == "accepted":
        return ActionLoopResult(ok=False, message="Blocked action cannot be accepted.", errors=["blocked_action"])
    if new_state not in TRANSITIONS.get(current.state, set()):
        return ActionLoopResult(ok=False, message="Invalid transition.", errors=[f"invalid:{current.state}->{new_state}"])
    updated = store_update_state(action_id, new_state, note=note)
    if not updated:
        return ActionLoopResult(ok=False, message="Action update failed.", errors=["update_failed"])
    event = _record_event(updated, new_state, actor=actor, note=note)
    _touch_index(action=updated)
    return ActionLoopResult(ok=True, message=f"Action {new_state}.", action=updated, events=[event])


def accept_action(action_id: str, actor: str = "hermes", note: str = "") -> ActionLoopResult:
    return _transition(action_id, "accepted", actor=actor, note=note)


def reject_action(action_id: str, actor: str = "hermes", note: str = "") -> ActionLoopResult:
    return _transition(action_id, "rejected", actor=actor, note=note)


def defer_action(action_id: str, actor: str = "hermes", note: str = "") -> ActionLoopResult:
    return _transition(action_id, "deferred", actor=actor, note=note)


def list_events(action_id: str | None = None, limit: int = 30) -> list[ActionEvent]:
    from .store import _events_path, _load_jsonl

    rows = _load_jsonl(_events_path())
    events: list[ActionEvent] = []
    for row in rows:
        if action_id and str(row.get("action_id")) != str(action_id):
            continue
        events.append(
            ActionEvent(
                event_id=str(row.get("event_id") or ""),
                action_id=str(row.get("action_id") or ""),
                event_type=str(row.get("event_type") or "created"),
                created_at=str(row.get("created_at") or now_iso()),
                actor=str(row.get("actor") or "unknown"),
                note=str(row.get("note") or ""),
                snapshot=row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {},
            )
        )
    events.sort(key=lambda item: item.created_at, reverse=True)
    return events[: max(1, int(limit))]


def ensure_index() -> dict[str, Any]:
    return rebuild_index()
