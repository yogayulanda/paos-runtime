from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from assistant.config import load_assistant_config

from .renderer import write_context_outputs
from .sources import (
    ArtifactSource,
    MemorySource,
    RepoContextSectionSource,
    RuntimeStatusSource,
    load_latest_artifact_sources,
    load_memory_sources,
    load_repo_context_sources,
    load_runtime_status_sources,
)


@dataclass(frozen=True)
class AssistantContextBuildResult:
    status: str
    category: str
    generated_at: str
    markdown_path: Path
    json_path: Path
    payload: dict[str, Any]
    warnings: list[str]
    errors: list[str]


def _section_map(sections: list[RepoContextSectionSource]) -> dict[str, str]:
    return {section.name: section.content for section in sections}


def _summarize_runtime_state(statuses: list[RuntimeStatusSource]) -> list[str]:
    summaries: list[str] = []
    for status in statuses:
        summary = status.summary
        if status.generated_at:
            summary = f"{summary} @ {status.generated_at}"
        summaries.append(summary)
    return summaries


def _guidance(
    category: str,
    warnings: list[str],
    memory_source: MemorySource,
    artifact_sources: dict[str, ArtifactSource],
) -> list[str]:
    guidance = [
        "Prefer durable repo context for identity, working style, and active projects.",
        "Use the latest digest and insight as bounded intelligence summaries, not source of truth.",
        "Treat temporary memory as short-lived context only.",
        "Keep output concise and cite file paths or artifact metadata when useful.",
        "Do not start GitHub source collection, Opportunity Engine work, or Telegram UX changes in this phase.",
    ]

    if warnings:
        guidance.append("Surface missing-source warnings explicitly when relevant.")

    if not memory_source.items:
        guidance.append("No temporary memory items were available; rely on repo context and runtime state.")
    elif memory_source.provider.get("fallback_used"):
        guidance.append(
            f"Memory provider fallback is active ({memory_source.provider.get('active_provider')}); "
            "treat recalled memory as advisory."
        )

    digest = artifact_sources.get("digest")
    insight = artifact_sources.get("insight")
    if not getattr(digest, "exists", False) or not getattr(insight, "exists", False):
        guidance.append("Missing intelligence artifacts should be treated as warnings, not blockers, if context can still be formed.")

    if category:
        guidance.append(f"Keep category focus aligned to `{category}`.")

    return guidance


def _latest_intelligence_payload(artifact_sources: dict[str, ArtifactSource]) -> dict[str, Any]:
    return {
        "digest": artifact_sources["digest"].to_dict() if "digest" in artifact_sources else {},
        "insight": artifact_sources["insight"].to_dict() if "insight" in artifact_sources else {},
    }


def build_assistant_context(category: str) -> AssistantContextBuildResult:
    config = load_assistant_config()
    generated_at = datetime.now().astimezone().isoformat()
    warnings: list[str] = []
    errors: list[str] = []

    repo_context_sections, repo_warnings = load_repo_context_sources()
    warnings.extend(repo_warnings)

    artifact_sources, artifact_warnings = load_latest_artifact_sources(category)
    warnings.extend(artifact_warnings)

    runtime_statuses, runtime_warnings = load_runtime_status_sources(config.context.max_runtime_statuses)
    warnings.extend(runtime_warnings)

    memory_source, memory_warnings = load_memory_sources(category, config.context.max_memory_items)
    warnings.extend(memory_warnings)

    section_content = _section_map(repo_context_sections)
    context_payload = {
        "identity": section_content.get("identity") or "No repository context available.",
        "working_style": section_content.get("working_style") or "No repository context available.",
        "active_projects": section_content.get("active_projects") or "No repository context available.",
        "runtime_state": _summarize_runtime_state(runtime_statuses),
        "latest_intelligence": _latest_intelligence_payload(artifact_sources),
        "temporary_memory": memory_source.items,
        "assistant_guidance": _guidance(category, warnings, memory_source, artifact_sources),
    }

    payload = {
        "generated_at": generated_at,
        "category": category,
        "sources": {
            "repo_context": [section.to_dict() for section in repo_context_sections],
            "runtime_state": [status.to_dict() for status in runtime_statuses],
            "artifacts": {
                name: source.to_dict() for name, source in artifact_sources.items()
            },
            "memory": memory_source.to_dict(),
        },
        "context": context_payload,
        "diagnostics": {
            "status": "success",
            "warnings": warnings,
            "errors": errors,
        },
    }

    if errors:
        payload["diagnostics"]["status"] = "failed"
    elif warnings:
        payload["diagnostics"]["status"] = "success_with_warnings"

    markdown_path, json_path = write_context_outputs(payload)

    return AssistantContextBuildResult(
        status=payload["diagnostics"]["status"],
        category=category,
        generated_at=generated_at,
        markdown_path=markdown_path,
        json_path=json_path,
        payload=payload,
        warnings=warnings,
        errors=errors,
    )
