from __future__ import annotations

import re

from .models import ActionClassification


_BLOCKED_TERMS = (
    "delete",
    "drop",
    "destroy",
    "wipe",
    "shutdown",
    "gateway",
    "public api",
    "tunnel",
    "expose",
    "deploy",
)
_APPROVAL_TERMS = (
    "apply",
    "write",
    "commit",
    "push",
    "merge",
    "schedule",
    "cron",
    "memory write",
    "paos_memory_write",
)
_GITHUB_MUTATION_PATTERN = r"\b(?:buat|bikin|create|push|commit|merge|update|ubah|edit|apply)\b.{0,40}\b(?:github|pr|pull request|issue|repo|repository)\b|\b(?:github|pr|pull request|issue|repo|repository)\b.{0,40}\b(?:buat|bikin|create|push|commit|merge|update|ubah|edit|apply)\b"
_READ_ONLY_TERMS = ("status", "health", "context", "dashboard", "daily", "handoff", "read", "show", "list")


def classify_action_intent(intent: str, target: str | None = None, category: str | None = None) -> ActionClassification:
    text = " ".join(
        [
            str(intent or "").strip().lower(),
            str(target or "").strip().lower(),
            str(category or "").strip().lower(),
        ]
    ).strip()
    matches_blocked = [term for term in _BLOCKED_TERMS if term in text]
    if matches_blocked:
        return ActionClassification(
            action_class="blocked",
            reason="Intent includes forbidden or unsafe mutation/exposure operation.",
            matched_terms=matches_blocked,
        )

    matches_approval = [term for term in _APPROVAL_TERMS if term in text]
    if re.search(_GITHUB_MUTATION_PATTERN, text):
        matches_approval.append("github_mutation")
    if matches_approval:
        return ActionClassification(
            action_class="approval_required",
            reason="Intent appears mutation-like and must stop at approval boundary.",
            matched_terms=matches_approval,
        )

    matches_read = [term for term in _READ_ONLY_TERMS if term in text]
    if matches_read and len(matches_read) >= 2:
        return ActionClassification(
            action_class="read_only",
            reason="Intent is informational and can stay read-only.",
            matched_terms=matches_read,
        )

    return ActionClassification(
        action_class="draft_only",
        reason="Intent can be translated into a bounded draft without applying changes.",
        matched_terms=[],
    )
