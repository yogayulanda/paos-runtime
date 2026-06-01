from __future__ import annotations

from typing import Any
from uuid import uuid4

from assistant.action_loop import accept_action, defer_action, reject_action
from assistant.memory import transition_candidate

from .models import ApprovalEvent, ApprovalRecord, now_iso, make_approval_id
from .store import append_approval, append_audit_event, get_approval as store_get_approval, list_approvals as store_list_approvals, list_audit_events as store_list_audit

_DECISIONS = {"approve": "approved", "reject": "rejected", "cancel": "cancelled"}
_ALLOWED_APPLY_TYPES = {"local_action_state_update", "memory_candidate_promotion"}
_BLOCKED_KEYWORDS = (
    "github", "commit", "push", "merge", "pull request", "pr", "systemd", "systemctl", "cron", "scheduler", "gateway start", "enable hermes gateway", "public api", "tunnel", "shell",
)


def _event(event_type: str, approval_id: str, actor: str, message: str = "", detail: dict[str, Any] | None = None) -> ApprovalEvent:
    return ApprovalEvent(
        event_id=f"aevt_{uuid4().hex[:10]}",
        approval_id=approval_id,
        event_type=event_type,
        actor=actor,
        created_at=now_iso(),
        message=message,
        detail=detail or {},
    )


def _persist_with_event(record: ApprovalRecord, event: ApprovalEvent) -> ApprovalRecord:
    record.audit_events.append(event.to_dict())
    append_approval(record)
    append_audit_event(event.to_dict())
    return record


def classify_operation(proposed_operation: str, operation_type: str | None = None) -> tuple[str, str, bool]:
    op = str(proposed_operation or "").strip().lower()
    otype = str(operation_type or "").strip().lower()
    blocked = any(k in op for k in _BLOCKED_KEYWORDS)
    if blocked:
        return "blocked", "critical", True
    if otype in {"read_only", "draft_only"}:
        return otype, "low", False
    if otype in _ALLOWED_APPLY_TYPES:
        risk = "medium" if otype == "local_action_state_update" else "high"
        return otype, risk, False
    if otype == "future_external_write":
        return "future_external_write", "critical", True
    return "blocked", "high", True


def create_approval(
    *,
    source: str,
    requested_by: str,
    proposed_operation: str,
    operation_type: str,
    evidence_refs: list[str] | None = None,
    payload_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type, risk_level, blocked = classify_operation(proposed_operation, operation_type)
    status = "blocked" if blocked else "pending"
    record = ApprovalRecord(
        approval_id=make_approval_id(),
        source=str(source or "unknown"),
        requested_by=str(requested_by or "unknown"),
        proposed_operation=str(proposed_operation or ""),
        operation_type=normalized_type,
        risk_level=risk_level,
        evidence_refs=[str(x) for x in (evidence_refs or [])],
        payload_preview=payload_preview if isinstance(payload_preview, dict) else {},
        status=status,
    )
    event = _event("proposed" if not blocked else "blocked", record.approval_id, requested_by, message="approval created")
    _persist_with_event(record, event)
    return {"ok": True, "approval": record.to_dict(), "blocked": blocked, "warnings": [], "errors": []}


def list_approvals(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    items = [item.to_dict() for item in store_list_approvals(status=status, limit=limit)]
    return {"ok": True, "items": items, "warnings": [], "errors": []}


def get_approval(approval_id: str) -> dict[str, Any]:
    item = store_get_approval(approval_id)
    if not item:
        return {"ok": False, "errors": ["approval_not_found"], "warnings": []}
    return {"ok": True, "approval": item.to_dict(), "warnings": [], "errors": []}


def decide_approval(approval_id: str, decision: str, actor: str) -> dict[str, Any]:
    record = store_get_approval(approval_id)
    if not record:
        return {"ok": False, "warnings": [], "errors": ["approval_not_found"]}
    if record.status != "pending":
        return {"ok": False, "warnings": [], "errors": [f"invalid_status:{record.status}"]}
    normalized = _DECISIONS.get(str(decision or "").strip().lower())
    if not normalized:
        return {"ok": False, "warnings": [], "errors": ["invalid_decision"]}
    record.status = normalized
    record.decided_at = now_iso()
    evt = _event(normalized, record.approval_id, actor, message=f"approval {normalized}")
    _persist_with_event(record, evt)
    return {"ok": True, "approval": record.to_dict(), "warnings": [], "errors": []}


def apply_approval(approval_id: str, actor: str) -> dict[str, Any]:
    record = store_get_approval(approval_id)
    if not record:
        return {"ok": False, "warnings": [], "errors": ["approval_not_found"]}
    if record.status != "approved":
        return {"ok": False, "warnings": [], "errors": [f"approval_not_approved:{record.status}"]}
    if record.operation_type not in _ALLOWED_APPLY_TYPES:
        record.status = "blocked"
        evt = _event("blocked", record.approval_id, actor, message="apply blocked by policy")
        _persist_with_event(record, evt)
        return {"ok": False, "warnings": [], "errors": ["operation_blocked_in_v1_5a"]}

    try:
        preview = record.payload_preview
        if record.operation_type == "local_action_state_update":
            action_id = str(preview.get("action_id") or "").strip()
            transition = str(preview.get("transition") or "").strip().lower()
            note = str(preview.get("note") or "approval apply")
            if transition == "accepted":
                applied = accept_action(action_id, actor=actor, note=note)
            elif transition == "rejected":
                applied = reject_action(action_id, actor=actor, note=note)
            elif transition == "deferred":
                applied = defer_action(action_id, actor=actor, note=note)
            else:
                raise RuntimeError("invalid local_action_state_update transition")
            if not applied.ok:
                raise RuntimeError(",".join(applied.errors or ["action_apply_failed"]))
        elif record.operation_type == "memory_candidate_promotion":
            candidate_id = str(preview.get("candidate_id") or "").strip()
            promoted = transition_candidate(candidate_id, "approve")
            if not promoted.get("ok"):
                raise RuntimeError(",".join(promoted.get("errors") or ["memory_apply_failed"]))

        record.status = "applied"
        record.applied_at = now_iso()
        evt = _event("applied", record.approval_id, actor, message="approval applied", detail={"operation_type": record.operation_type})
        _persist_with_event(record, evt)
        return {"ok": True, "approval": record.to_dict(), "warnings": [], "errors": []}
    except Exception as exc:
        record.status = "failed"
        evt = _event("failed", record.approval_id, actor, message=f"apply failed: {exc}")
        _persist_with_event(record, evt)
        return {"ok": False, "approval": record.to_dict(), "warnings": [], "errors": [str(exc)]}


def list_audit_events(approval_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"ok": True, "items": store_list_audit(approval_id=approval_id, limit=limit), "warnings": [], "errors": []}
