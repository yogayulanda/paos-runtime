import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "assistant" / "context"


def _section_body(text: str, fallback: str) -> str:
    content = (text or "").strip()
    return content if content else fallback


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def render_markdown(payload: dict[str, Any]) -> str:
    context = payload.get("context") or {}
    sources = payload.get("sources") or {}
    warnings = (payload.get("diagnostics") or {}).get("warnings") or []

    repo_context = sources.get("repo_context") or []
    runtime_state = context.get("runtime_state") or []
    latest_intelligence = context.get("latest_intelligence") or {}
    temporary_memory = context.get("temporary_memory") or []
    assistant_guidance = context.get("assistant_guidance") or []

    def repo_section(name: str) -> str:
        for section in repo_context:
            if section.get("name") == name:
                return section.get("content") or ""
        return ""

    identity = _section_body(repo_section("identity"), "No repository context available.")
    working_style = _section_body(
        repo_section("working_style"), "No repository context available."
    )
    active_projects = _section_body(
        repo_section("active_projects"), "No repository context available."
    )

    lines = [
        "# PAOS Assistant Context",
        "",
        "## Identity Context",
        identity,
        "",
        "## Working Style",
        working_style,
        "",
        "## Active Projects",
        active_projects,
        "",
        "## Runtime State",
    ]

    if runtime_state:
        runtime_state_lines = []
        for item in runtime_state:
            if isinstance(item, dict):
                summary = item.get("summary") or item.get("status") or ""
            else:
                summary = str(item)
            if summary:
                runtime_state_lines.append(summary)
        lines.append(_bullet_list(runtime_state_lines))
    else:
        lines.append("- No runtime state snapshots available.")

    lines.extend(["", "## Latest Intelligence"])

    digest = latest_intelligence.get("digest") or {}
    insight = latest_intelligence.get("insight") or {}
    if digest:
        lines.extend(
            [
                "### Digest",
                f"- Path: `{digest.get('path')}`",
                f"- Status: {'available' if digest.get('exists') else 'missing'}",
                f"- Modified: {digest.get('modified_at') or 'unknown'}",
            ]
        )
        if digest.get("excerpt"):
            lines.extend(["", digest.get("excerpt"), ""])
    else:
        lines.append("- No latest digest available.")
    if insight:
        lines.extend(
            [
                "### Insight",
                f"- Path: `{insight.get('path')}`",
                f"- Status: {'available' if insight.get('exists') else 'missing'}",
                f"- Modified: {insight.get('modified_at') or 'unknown'}",
            ]
        )
        if insight.get("excerpt"):
            lines.extend(["", insight.get("excerpt"), ""])
    else:
        lines.append("- No latest insight available.")

    lines.extend(["## Temporary Memory"])
    if temporary_memory:
        for item in temporary_memory:
            content = (item.get("content") or "").strip()
            created_at = item.get("created_at") or "unknown"
            scope = item.get("scope") or "global"
            if content:
                lines.append(f"- `{created_at}` [{scope}] {content}")
    else:
        lines.append("- No temporary memory entries available.")

    lines.extend(["", "## Current Assistant Guidance"])
    if assistant_guidance:
        lines.extend(_bullet_list([item for item in assistant_guidance if item]).splitlines())
    else:
        lines.append("- No additional guidance available.")

    if warnings:
        lines.extend(["", "## Diagnostics Notes", _bullet_list([str(item) for item in warnings])])

    return "\n".join(lines).strip() + "\n"


def build_output_paths(generated_at: str) -> tuple[Path, Path]:
    generated_date = date.fromisoformat(generated_at[:10])
    output_dir = OUTPUT_ROOT / generated_date.isoformat()
    return (
        output_dir / "assistant-context.md",
        output_dir / "assistant-context.json",
    )


def write_context_outputs(payload: dict[str, Any]) -> tuple[Path, Path]:
    generated_at = payload["generated_at"]
    markdown_path, json_path = build_output_paths(generated_at)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return markdown_path, json_path
