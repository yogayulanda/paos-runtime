from __future__ import annotations

MEMORY_TYPES: tuple[str, ...] = (
    "preference",
    "working_style",
    "project_fact",
    "decision",
    "task_state",
    "note",
)

MEMORY_STATUSES: tuple[str, ...] = (
    "candidate",
    "active",
    "rejected",
    "superseded",
)

SOURCE_TYPES: tuple[str, ...] = (
    "conversation",
    "telegram_message",
    "codex_report",
    "action_loop",
    "source_intelligence",
    "handoff",
    "existing_context",
    "manual_user_instruction",
)


def normalize_memory_type(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in MEMORY_TYPES:
        return raw
    return "note"


def normalize_status(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in MEMORY_STATUSES:
        return raw
    return "candidate"


def normalize_source_type(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in SOURCE_TYPES:
        return raw
    return "conversation"
