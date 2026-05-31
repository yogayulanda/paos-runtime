import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "assistant" / "opportunities"


def _render_priority_group(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- None"

    lines: list[str] = []
    for item in items:
        reason = str(item.get("reason") or "").strip()
        action = str(item.get("next_action") or "").strip()
        type_name = str(item.get("type") or "review").strip().lower()
        title = str(item.get("title") or "Untitled opportunity").strip()
        lines.append(f"- [{type_name}] {title}")
        if reason:
            lines.append(f"  Reason: {reason}")
        if action:
            lines.append(f"  Next: {action}")
    return "\n".join(lines)


def render_markdown(payload: dict[str, Any]) -> str:
    opportunities = payload.get("opportunities") or []
    high = [item for item in opportunities if str(item.get("priority") or "") == "high"]
    medium = [item for item in opportunities if str(item.get("priority") or "") == "medium"]
    low = [item for item in opportunities if str(item.get("priority") or "") == "low"]

    lines = [
        "# PAOS Opportunities",
        "",
        "## High Priority",
        _render_priority_group(high),
        "",
        "## Medium Priority",
        _render_priority_group(medium),
        "",
        "## Low Priority",
        _render_priority_group(low),
        "",
        "## Source Coverage",
    ]

    source_artifacts = payload.get("source_artifacts") or {}
    if source_artifacts:
        for name, meta in source_artifacts.items():
            if isinstance(meta, dict):
                status = "available" if meta.get("exists") else "missing"
                lines.append(
                    f"- `{name}`: {status}"
                    f" | path={meta.get('path') or '-'}"
                    f" | date={meta.get('date') or '-'}"
                    f" | modified_at={meta.get('modified_at') or '-'}"
                )
    else:
        lines.append("- No source artifact metadata available.")

    lines.extend(["", "## Warnings"])
    warnings = [str(item) for item in payload.get("warnings") or []]
    if warnings:
        lines.extend([f"- {item}" for item in warnings])
    else:
        lines.append("- None")

    return "\n".join(lines).strip() + "\n"


def build_output_paths(generated_at: str) -> tuple[Path, Path]:
    generated_date = date.fromisoformat(generated_at[:10])
    output_dir = OUTPUT_ROOT / generated_date.isoformat()
    return (output_dir / "opportunities.md", output_dir / "opportunities.json")


def write_opportunities_outputs(payload: dict[str, Any]) -> tuple[Path, Path]:
    generated_at = payload["generated_at"]
    markdown_path, json_path = build_output_paths(generated_at)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return markdown_path, json_path
