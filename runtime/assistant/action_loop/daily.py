from __future__ import annotations

from assistant.actions import create_action_draft

from .models import ActionRecord, make_id


def generate_daily_action(category: str = "runtime", persist: bool = True) -> ActionRecord:
    draft = create_action_draft(intent="daily action draft", category=category)
    return ActionRecord(
        action_id=make_id("action"),
        title=str(draft.get("title") or "Daily Action Draft"),
        summary=str(draft.get("summary") or "Draft prioritas harian."),
        steps=[str(x) for x in (draft.get("steps") or [])],
        state="proposed",
        source="daily_generator",
        category=category,
        tags=["daily", "phase5"],
        evidence={"draft": draft, "persist_requested": bool(persist)},
    )
