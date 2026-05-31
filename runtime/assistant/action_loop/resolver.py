from __future__ import annotations

from .models import ActionReference
from .service import get_action, list_actions
from .store import load_index


def resolve_action_reference(reference: str = "", ordinal: int | None = None, query: str | None = None):
    ref = ActionReference(reference=reference, ordinal=ordinal, query=query)
    lowered = f"{ref.reference} {ref.query or ''}".strip().lower()
    idx = load_index()

    if ref.ordinal and ref.ordinal > 0:
        ids = idx.get("latest_listed_action_ids") if isinstance(idx.get("latest_listed_action_ids"), list) else []
        if len(ids) >= ref.ordinal:
            return get_action(str(ids[ref.ordinal - 1]))

    if any(k in lowered for k in ("nomor", "number")):
        parts = [p for p in lowered.split() if p.isdigit()]
        if parts:
            n = int(parts[0])
            ids = idx.get("latest_listed_action_ids") if isinstance(idx.get("latest_listed_action_ids"), list) else []
            if len(ids) >= n:
                return get_action(str(ids[n - 1]))

    if any(k in lowered for k in ("yang tadi", "action terakhir", "terakhir", "ini")):
        latest = idx.get("latest_created_action_id")
        if latest:
            return get_action(str(latest))

    if "accepted" in lowered or "fokus" in lowered:
        aid = idx.get("latest_accepted_action_id")
        if aid:
            return get_action(str(aid))

    if "deferred" in lowered or "ditunda" in lowered:
        aid = idx.get("latest_deferred_action_id")
        if aid:
            return get_action(str(aid))

    if "daily" in lowered:
        for action in list_actions(limit=30):
            if "daily" in action.tags or "daily" in action.title.lower():
                return action

    if "scheduler" in lowered:
        for action in list_actions(limit=30):
            blob = f"{action.title} {action.summary} {' '.join(action.steps)}".lower()
            if "scheduler" in blob:
                return action

    if "handoff codex" in lowered or "codex" in lowered:
        for action in list_actions(state="accepted", limit=30):
            if "codex" in " ".join(action.tags).lower() or "handoff" in action.title.lower():
                return action

    return None
