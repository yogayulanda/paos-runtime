from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

ApprovalStatus = Literal["pending", "approved", "rejected", "cancelled", "applied", "failed", "blocked"]
OperationType = Literal[
    "read_only",
    "local_action_state_update",
    "memory_candidate_promotion",
    "draft_only",
    "blocked",
    "future_external_write",
]
RiskLevel = Literal["low", "medium", "high", "critical"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_approval_id() -> str:
    return f"approval_{uuid4().hex[:12]}"


@dataclass
class ApprovalEvent:
    event_id: str
    approval_id: str
    event_type: str
    actor: str
    created_at: str
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "approval_id": self.approval_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "created_at": self.created_at,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class ApprovalRecord:
    approval_id: str
    source: str
    requested_by: str
    proposed_operation: str
    operation_type: OperationType
    risk_level: RiskLevel
    evidence_refs: list[str] = field(default_factory=list)
    payload_preview: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = "pending"
    created_at: str = field(default_factory=now_iso)
    decided_at: str | None = None
    applied_at: str | None = None
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "source": self.source,
            "requested_by": self.requested_by,
            "proposed_operation": self.proposed_operation,
            "operation_type": self.operation_type,
            "risk_level": self.risk_level,
            "evidence_refs": list(self.evidence_refs),
            "payload_preview": dict(self.payload_preview),
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "applied_at": self.applied_at,
            "audit_events": list(self.audit_events),
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "ApprovalRecord":
        return ApprovalRecord(
            approval_id=str(payload.get("approval_id") or ""),
            source=str(payload.get("source") or ""),
            requested_by=str(payload.get("requested_by") or "unknown"),
            proposed_operation=str(payload.get("proposed_operation") or ""),
            operation_type=str(payload.get("operation_type") or "blocked"),
            risk_level=str(payload.get("risk_level") or "high"),
            evidence_refs=[str(x) for x in (payload.get("evidence_refs") or [])],
            payload_preview=payload.get("payload_preview") if isinstance(payload.get("payload_preview"), dict) else {},
            status=str(payload.get("status") or "pending"),
            created_at=str(payload.get("created_at") or now_iso()),
            decided_at=str(payload.get("decided_at")) if payload.get("decided_at") else None,
            applied_at=str(payload.get("applied_at")) if payload.get("applied_at") else None,
            audit_events=[x for x in (payload.get("audit_events") or []) if isinstance(x, dict)],
        )
