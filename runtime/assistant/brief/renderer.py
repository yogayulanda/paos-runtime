import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "assistant" / "briefs"


def _bullet(items: list[str], empty_label: str = "None") -> str:
    if not items:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in items)


def render_markdown(payload: dict[str, Any]) -> str:
    opportunities = payload.get("opportunities") or {}
    source_artifacts = payload.get("source_artifacts") or {}

    lines = [
        "# PAOS Assistant Brief",
        "",
        "## Fokus Hari Ini",
        f"- {(payload.get('focus_today') or 'No clear focus generated.').strip()}",
        "",
        "## Opportunity Ringan",
        "### Build",
        _bullet([str(item) for item in opportunities.get("build") or []]),
        "",
        "### Learn",
        _bullet([str(item) for item in opportunities.get("learn") or []]),
        "",
        "### Content",
        _bullet([str(item) for item in opportunities.get("content") or []]),
        "",
        "### Review",
        _bullet([str(item) for item in opportunities.get("review") or []]),
        "",
        "## Risiko / Perlu Dicek",
        _bullet([str(item) for item in payload.get("risks_or_checks") or []]),
        "",
        "## Suggested Next Action",
        f"- {(payload.get('suggested_next_action') or 'Run assistant context and diagnostics, then re-generate brief.').strip()}",
        "",
        "## Source Coverage",
    ]

    if source_artifacts:
        for name, meta in source_artifacts.items():
            if isinstance(meta, dict):
                status = "available" if meta.get("exists") else "missing"
                lines.append(
                    f"- `{name}`: {status}"
                    f" | path={meta.get('path') or '-'}"
                    f" | modified_at={meta.get('modified_at') or '-'}"
                )
    else:
        lines.append("- No source artifact metadata available.")

    warnings = [str(item) for item in payload.get("warnings") or []]
    if warnings:
        lines.extend(["", "Warnings:", _bullet(warnings)])

    return "\n".join(lines).strip() + "\n"


def build_output_paths(generated_at: str) -> tuple[Path, Path]:
    generated_date = date.fromisoformat(generated_at[:10])
    output_dir = OUTPUT_ROOT / generated_date.isoformat()
    return (
        output_dir / "assistant-brief.md",
        output_dir / "assistant-brief.json",
    )


def write_brief_outputs(payload: dict[str, Any]) -> tuple[Path, Path]:
    generated_at = payload["generated_at"]
    markdown_path, json_path = build_output_paths(generated_at)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return markdown_path, json_path
