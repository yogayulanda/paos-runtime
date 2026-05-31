import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from assistant.brief import resolve_latest_assistant_brief
from assistant.config import load_assistant_config

from .renderer import write_opportunities_outputs


MISSING_BRIEF_REMEDIATION = "venv/bin/python runtime/assistant/jobs/run_assistant_brief.py --category ai"


@dataclass(frozen=True)
class AssistantOpportunitiesBuildResult:
    status: str
    category: str
    generated_at: str
    markdown_path: Path
    json_path: Path
    payload: dict[str, Any]
    warnings: list[str]
    errors: list[str]


def _normalize_key(*parts: str) -> str:
    return " ".join(part.strip().lower() for part in parts if part).strip()


def _priority_from_text(text: str, default: str = "medium") -> str:
    lowered = text.lower()
    if "no critical risks" in lowered or "no critical risk" in lowered:
        return "low"
    if any(token in lowered for token in ["fail", "error", "missing", "stale", "blocked", "critical"]):
        return "high"
    if any(token in lowered for token in ["warning", "check", "review"]):
        return "medium"
    return default


def build_assistant_opportunities(category: str) -> AssistantOpportunitiesBuildResult:
    _ = load_assistant_config()
    generated_at = datetime.now().astimezone().isoformat()
    warnings: list[str] = []
    errors: list[str] = []

    brief_resolution = resolve_latest_assistant_brief()
    warnings.extend([str(item) for item in brief_resolution.warnings])

    brief_json = brief_resolution.json
    if not brief_json.exists or not brief_json.path:
        raise RuntimeError(
            "assistant brief JSON artifact is missing; "
            f"remediation: {MISSING_BRIEF_REMEDIATION}"
        )

    raw = Path(brief_json.path).read_text(encoding="utf-8", errors="ignore")
    try:
        brief_payload = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(
            f"assistant brief JSON parse failure: {exc}; remediation: {MISSING_BRIEF_REMEDIATION}"
        ) from exc

    opportunity_items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_opportunity(
        *,
        opp_type: str,
        priority: str,
        title: str,
        reason: str,
        next_action: str,
        evidence: str | None = None,
    ) -> None:
        normalized = _normalize_key(opp_type, title, next_action)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        item = {
            "id": f"opp-{len(opportunity_items) + 1:03d}",
            "type": opp_type,
            "priority": priority,
            "title": title.strip(),
            "reason": reason.strip(),
            "next_action": next_action.strip(),
            "source": "assistant_brief",
        }
        if evidence:
            item["evidence"] = evidence.strip()
        opportunity_items.append(item)

    focus_today = str(brief_payload.get("focus_today") or "").strip()
    if focus_today:
        add_opportunity(
            opp_type="build",
            priority="high",
            title="Execute today focus",
            reason="Daily brief defines a concrete execution focus.",
            next_action=focus_today,
            evidence=focus_today,
        )

    grouped = brief_payload.get("opportunities") or {}
    mappings = [
        ("build", "high", "Build"),
        ("learn", "medium", "Learn"),
        ("content", "medium", "Content"),
        ("review", "medium", "Review"),
    ]
    for group_name, default_priority, title_prefix in mappings:
        for entry in grouped.get(group_name) or []:
            text = str(entry or "").strip()
            if not text:
                continue
            add_opportunity(
                opp_type=group_name,
                priority=default_priority,
                title=f"{title_prefix}: {text}",
                reason=f"Derived from assistant brief {group_name} opportunities.",
                next_action=text,
                evidence=text,
            )

    for risk in brief_payload.get("risks_or_checks") or []:
        text = str(risk or "").strip()
        if not text:
            continue
        if text.lower().startswith("no critical risks detected"):
            continue
        add_opportunity(
            opp_type="review",
            priority=_priority_from_text(text, default="medium"),
            title=f"Mitigate risk: {text}",
            reason="Brief highlights this risk/check item.",
            next_action=f"Validate and resolve: {text}",
            evidence=text,
        )

    suggested = str(brief_payload.get("suggested_next_action") or "").strip()
    if suggested:
        add_opportunity(
            opp_type="career",
            priority="low",
            title="Plan next execution loop",
            reason="Brief includes a suggested next action for momentum.",
            next_action=suggested,
            evidence=suggested,
        )

    if len(opportunity_items) < 3:
        add_opportunity(
            opp_type="review",
            priority="medium",
            title="Refresh diagnostics baseline",
            reason="Opportunity list is sparse and needs baseline runtime state.",
            next_action="venv/bin/python runtime/assistant/jobs/run_assistant_diagnostics.py --category ai",
            evidence="assistant brief opportunities are limited",
        )

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    opportunity_items.sort(key=lambda item: (priority_rank.get(str(item.get("priority")), 3), item["id"]))
    opportunity_items = opportunity_items[:7]

    if len(opportunity_items) < 3:
        warnings.append("generated fewer than 3 opportunities due to limited brief content")

    payload_date = str(brief_payload.get("date") or generated_at[:10])
    payload = {
        "date": payload_date,
        "category": category,
        "generated_at": generated_at,
        "opportunities": opportunity_items,
        "source_artifacts": {
            "assistant_brief_json": brief_resolution.json.to_dict(),
            "assistant_brief_markdown": brief_resolution.markdown.to_dict(),
        },
        "warnings": warnings,
    }

    markdown_path, json_path = write_opportunities_outputs(payload)
    status = "success_with_warnings" if warnings else "success"

    return AssistantOpportunitiesBuildResult(
        status=status,
        category=category,
        generated_at=generated_at,
        markdown_path=markdown_path,
        json_path=json_path,
        payload=payload,
        warnings=warnings,
        errors=errors,
    )
