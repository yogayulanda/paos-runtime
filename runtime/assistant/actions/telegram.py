from __future__ import annotations

from typing import Any

MAX_TELEGRAM = 3900


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def render_action_draft_telegram(payload: dict[str, Any]) -> str:
    action_class = _compact(payload.get("action_class")) or "draft_only"
    title = _compact(payload.get("title")) or "Action Draft"
    summary = _compact(payload.get("summary")) or "Draft-only output."
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    blocked_reason = _compact(payload.get("blocked_reason"))
    approval_payload = payload.get("approval_payload") if isinstance(payload.get("approval_payload"), dict) else None

    lines = [
        "🧩 PAOS Draft Boundary",
        f"Class: {action_class}",
        f"Title: {title}",
        "",
        summary,
    ]

    if steps:
        lines.extend(["", "Draft Steps"])
        for idx, step in enumerate(steps[:6], start=1):
            lines.append(f"{idx}. {_compact(step)}")

    if blocked_reason:
        lines.extend(["", f"Blocked: {blocked_reason}"])

    if approval_payload:
        lines.extend(
            [
                "",
                "Approval Payload",
                f"- intent: {_compact(approval_payload.get('intent'))}",
                f"- target: {_compact(approval_payload.get('target')) or 'n/a'}",
                f"- category: {_compact(approval_payload.get('category')) or 'n/a'}",
                "- apply_enabled: false",
            ]
        )

    if warnings:
        lines.extend(["", "Warnings"])
        for item in warnings[:4]:
            lines.append(f"- {_compact(item)}")

    lines.extend(
        [
            "",
            "No action was applied.",
            "This is draft-only output with approval boundary.",
        ]
    )
    return "\n".join(lines)[:MAX_TELEGRAM]
