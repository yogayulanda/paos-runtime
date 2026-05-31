from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

ActionState = Literal["proposed", "accepted", "rejected", "deferred", "expired", "blocked"]
ActionEventType = Literal["created", "accepted", "rejected", "deferred", "expired", "blocked"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:10]}"


@dataclass
class ActionRecord:
    action_id: str
    title: str
    summary: str
    steps: list[str]
    state: ActionState
    source: str
    category: str
    tags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    applied: bool = False
    apply_mechanism_available: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "summary": self.summary,
            "steps": self.steps,
            "state": self.state,
            "source": self.source,
            "category": self.category,
            "tags": self.tags,
            "evidence": self.evidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "applied": False,
            "apply_mechanism_available": False,
            "note": self.note,
            "notice": "No external action was applied.",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionRecord":
        return cls(
            action_id=str(payload.get("action_id") or ""),
            title=str(payload.get("title") or ""),
            summary=str(payload.get("summary") or ""),
            steps=[str(x) for x in (payload.get("steps") or [])],
            state=str(payload.get("state") or "proposed"),
            source=str(payload.get("source") or "action_loop"),
            category=str(payload.get("category") or "runtime"),
            tags=[str(x) for x in (payload.get("tags") or [])],
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
            created_at=str(payload.get("created_at") or now_iso()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or now_iso()),
            applied=False,
            apply_mechanism_available=False,
            note=str(payload.get("note") or ""),
        )


@dataclass
class ActionEvent:
    event_id: str
    action_id: str
    event_type: ActionEventType
    created_at: str
    actor: str
    note: str
    snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "action_id": self.action_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "actor": self.actor,
            "note": self.note,
            "snapshot": self.snapshot,
        }


@dataclass
class ActionQuery:
    state: ActionState | None = None
    limit: int = 20


@dataclass
class ActionReference:
    reference: str = ""
    ordinal: int | None = None
    query: str | None = None


@dataclass
class ActionLoopResult:
    ok: bool
    message: str
    action: ActionRecord | None = None
    events: list[ActionEvent] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "action": self.action.to_dict() if self.action else None,
            "events": [e.to_dict() for e in self.events],
            "actions": [a.to_dict() for a in self.actions],
            "warnings": self.warnings,
            "errors": self.errors,
            "applied": False,
            "apply_mechanism_available": False,
            "notice": "No external action was applied.",
        }
