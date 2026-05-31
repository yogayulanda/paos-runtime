from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


ActionClass = Literal["read_only", "draft_only", "approval_required", "blocked"]
DraftKind = Literal["daily", "handoff", "memory_promotion", "implementation_plan"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ActionPolicy:
    version: str = "phase4-draft-boundary-v1"
    forbidden_operations: list[str] = field(
        default_factory=lambda: [
            "paos_memory_write",
            "controlled_write_apply",
            "scheduler_mutation",
            "github_mutation",
            "public_api_tunnel",
            "enable_hermes_gateway",
        ]
    )
    read_only_tools: list[str] = field(
        default_factory=lambda: [
            "paos_health",
            "paos_context_get",
            "paos_brief_get",
            "paos_opportunities_get",
            "paos_memory_recall",
            "paos_dashboard_get",
            "paos_daily_get",
            "paos_context_health_get",
            "paos_handoff_get",
            "paos_runtime_status_get",
            "paos_source_status_get",
            "paos_action_policy_get",
            "paos_action_draft_create",
            "paos_action_list",
            "paos_action_get",
            "paos_action_event_list",
            "paos_daily_action_generate",
            "paos_action_resolve",
            "paos_action_state_transition",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "mode": "draft_only_boundary",
            "mutations_enabled": False,
            "approval_apply_enabled": False,
            "forbidden_operations": self.forbidden_operations,
            "read_only_tools": self.read_only_tools,
            "notice": "Draft-only layer active. No action was applied.",
        }


@dataclass
class ActionClassification:
    action_class: ActionClass
    reason: str
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_class": self.action_class,
            "reason": self.reason,
            "matched_terms": self.matched_terms,
        }


@dataclass
class ActionDraft:
    draft_id: str
    kind: DraftKind
    action_class: ActionClass
    title: str
    summary: str
    steps: list[str]
    evidence: dict[str, Any]
    approval_payload: dict[str, Any] | None = None
    blocked_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "kind": self.kind,
            "action_class": self.action_class,
            "title": self.title,
            "summary": self.summary,
            "steps": self.steps,
            "evidence": self.evidence,
            "approval_payload": self.approval_payload,
            "blocked_reason": self.blocked_reason,
            "warnings": self.warnings,
            "generated_at": self.generated_at,
            "applied": False,
            "apply_mechanism_available": False,
            "notice": "No action was applied. This output is a draft only.",
        }
