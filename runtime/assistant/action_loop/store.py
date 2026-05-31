from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import ActionEvent, ActionRecord, ActionState, now_iso


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _store_dir() -> Path:
    override = str(os.getenv("PAOS_ACTION_LOOP_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "assistant" / "action-loop"


def _actions_path() -> Path:
    return _store_dir() / "actions.jsonl"


def _events_path() -> Path:
    return _store_dir() / "events.jsonl"


def _index_path() -> Path:
    return _store_dir() / "index.json"


def _ensure_store() -> None:
    root = _store_dir()
    root.mkdir(parents=True, exist_ok=True)
    for path, initial in ((
        _actions_path(), ""), (_events_path(), ""), (_index_path(), "{}")
    ):
        if not path.exists():
            path.write_text(initial, encoding="utf-8")


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


def append_action(record: ActionRecord) -> None:
    _ensure_store()
    _append_jsonl(_actions_path(), record.to_dict())


def append_event(event: ActionEvent) -> None:
    _ensure_store()
    _append_jsonl(_events_path(), event.to_dict())


def _action_map() -> dict[str, ActionRecord]:
    data: dict[str, ActionRecord] = {}
    for row in _load_jsonl(_actions_path()):
        action = ActionRecord.from_dict(row)
        if action.action_id:
            data[action.action_id] = action
    return data


def get_action(action_id: str) -> ActionRecord | None:
    return _action_map().get(str(action_id or "").strip())


def list_actions(state: ActionState | None = None, limit: int = 20) -> list[ActionRecord]:
    items = list(_action_map().values())
    items.sort(key=lambda x: x.updated_at, reverse=True)
    if state:
        items = [item for item in items if item.state == state]
    return items[: max(1, int(limit))]


def update_state(action_id: str, new_state: ActionState, note: str = "") -> ActionRecord | None:
    current = get_action(action_id)
    if not current:
        return None
    updated = ActionRecord.from_dict(current.to_dict())
    updated.state = new_state
    updated.note = str(note or "").strip()
    updated.updated_at = now_iso()
    append_action(updated)
    return updated


def load_index() -> dict[str, Any]:
    _ensure_store()
    try:
        payload = json.loads(_index_path().read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def save_index(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_store()
    normalized = payload if isinstance(payload, dict) else {}
    normalized["updated_at"] = now_iso()
    _index_path().write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def rebuild_index() -> dict[str, Any]:
    actions = list_actions(limit=1000)
    events = _load_jsonl(_events_path())
    latest_created = actions[0].action_id if actions else None
    latest_accepted = next((a.action_id for a in actions if a.state == "accepted"), None)
    latest_deferred = next((a.action_id for a in actions if a.state == "deferred"), None)
    payload = {
        "latest_created_action_id": latest_created,
        "latest_accepted_action_id": latest_accepted,
        "latest_deferred_action_id": latest_deferred,
        "latest_listed_action_ids": [],
        "events_count": len(events),
        "actions_count": len(actions),
    }
    return save_index(payload)
