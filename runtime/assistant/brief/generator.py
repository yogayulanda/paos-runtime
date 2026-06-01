from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from assistant.artifacts import resolve_artifacts
from assistant.config import load_assistant_config
from assistant.context import resolve_latest_assistant_context
from assistant.context.sources import load_memory_sources, load_runtime_status_sources

from .renderer import write_brief_outputs


@dataclass(frozen=True)
class AssistantBriefBuildResult:
    status: str
    category: str
    generated_at: str
    markdown_path: Path
    json_path: Path
    payload: dict[str, Any]
    warnings: list[str]
    errors: list[str]


def _runtime_summary(runtime_statuses: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    opportunities: list[str] = []
    risks: list[str] = []
    if not runtime_statuses:
        risks.append("No runtime status snapshots found under .runtime/runs.")
        return opportunities, risks

    failed_jobs: list[str] = []
    warning_jobs: list[str] = []
    for item in runtime_statuses:
        job = item.get("job") or "unknown-job"
        status = (item.get("status") or "unknown").lower()
        if status in {"failed", "error"}:
            failed_jobs.append(job)
        elif "warning" in status:
            warning_jobs.append(job)

    if failed_jobs:
        risks.append(f"Runtime jobs failed: {', '.join(sorted(set(failed_jobs)))}.")
        opportunities.append("Stabilize failed runtime jobs before starting new feature work.")
    if warning_jobs:
        risks.append(f"Runtime jobs with warnings: {', '.join(sorted(set(warning_jobs)))}.")

    if not failed_jobs and not warning_jobs:
        opportunities.append("Runtime pipeline looks healthy; prioritize incremental delivery.")

    return opportunities, risks


def _artifact_summary(artifacts: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    focus_bits: list[str] = []
    build_ops: list[str] = []
    risks: list[str] = []

    digest = artifacts.get("digest") or {}
    insight = artifacts.get("insight") or {}

    if digest.get("exists"):
        focus_bits.append("Use latest digest as execution anchor.")
        build_ops.append("Apply one concrete task from the latest digest.")
    else:
        risks.append("Latest digest artifact is missing.")

    if insight.get("exists"):
        focus_bits.append("Translate latest insight into a small, testable change.")
        build_ops.append("Validate current implementation against latest insight assumptions.")
    else:
        risks.append("Latest insight artifact is missing.")

    return focus_bits, build_ops, risks


def _memory_summary(memory_items: list[dict[str, Any]], memory_provider: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    learn: list[str] = []
    review: list[str] = []
    risks: list[str] = []

    if memory_provider.get("fallback_used"):
        risks.append(
            "Memory provider fallback is active; treat memory items as advisory, not source of truth."
        )

    if memory_items:
        newest = memory_items[0].get("content") or "recent memory item"
        learn.append("Review recent memory notes for unresolved decisions.")
        review.append(f"Sanity-check memory note relevance: {newest[:140]}")
    else:
        learn.append("No memory items found; rely on context and runtime artifacts for priorities.")

    return learn, review, risks


def _context_summary(context_payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    content_ops: list[str] = []
    review_ops: list[str] = []
    context_data = context_payload.get("context") or {}
    guidance = context_data.get("assistant_guidance") or []
    runtime_state = context_data.get("runtime_state") or []

    if guidance:
        content_ops.append("Capture today decision log from assistant guidance into concise notes.")
    else:
        content_ops.append("Regenerate assistant context to refresh guidance before deep work.")

    if runtime_state:
        review_ops.append("Review latest runtime state summaries before choosing next implementation target.")
    else:
        review_ops.append("Run diagnostics to populate runtime state coverage.")

    return content_ops, review_ops


def build_assistant_brief(category: str) -> AssistantBriefBuildResult:
    _ = load_assistant_config()
    generated_at = datetime.now().astimezone().isoformat()
    warnings: list[str] = []
    errors: list[str] = []

    artifacts = resolve_artifacts(category=category).to_dict()

    assistant_context = resolve_latest_assistant_context().to_dict()
    warnings.extend([str(item) for item in assistant_context.get("warnings") or []])

    runtime_sources, runtime_warnings = load_runtime_status_sources(limit=8)
    warnings.extend(runtime_warnings)

    memory_source, memory_warnings = load_memory_sources(category=category, limit=5)
    warnings.extend(memory_warnings)

    usable_sources = 0
    if (artifacts.get("digest") or {}).get("exists"):
        usable_sources += 1
    if (artifacts.get("insight") or {}).get("exists"):
        usable_sources += 1
    if assistant_context.get("json", {}).get("exists") or assistant_context.get("markdown", {}).get("exists"):
        usable_sources += 1
    if runtime_sources:
        usable_sources += 1
    if memory_source.items:
        usable_sources += 1

    if usable_sources == 0:
        errors.append("No usable source artifacts found for assistant brief generation.")

    runtime_dicts = [item.to_dict() for item in runtime_sources]
    runtime_build_ops, runtime_risks = _runtime_summary(runtime_dicts)
    focus_bits, artifact_build_ops, artifact_risks = _artifact_summary(artifacts)
    memory_learn_ops, memory_review_ops, memory_risks = _memory_summary(
        memory_source.items, memory_source.provider
    )

    context_payload = {}
    context_json_path = assistant_context.get("json", {}).get("path")
    if context_json_path and assistant_context.get("json", {}).get("parseable"):
        try:
            import json

            context_payload = json.loads(Path(context_json_path).read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"failed reading assistant context JSON payload: {exc}")

    content_ops, context_review_ops = _context_summary(context_payload)

    risks_or_checks = runtime_risks + artifact_risks + memory_risks
    if not risks_or_checks:
        risks_or_checks.append("No critical risks detected from current artifacts.")

    focus_today = " ".join(focus_bits).strip()
    if not focus_today:
        focus_today = "Rebuild assistant context baseline and resolve missing intelligence artifacts."

    suggested_next_action = "Cek operating summary terbaru lalu pilih satu langkah kecil yang sudah tervalidasi."
    if errors:
        suggested_next_action = "Restore at least one assistant source artifact, then rerun assistant brief generation."
    elif runtime_risks:
        suggested_next_action = "Perbaiki source atau artifact yang gagal dulu, lalu bangun ulang brief setelah statusnya sehat."
    elif artifact_risks or memory_risks or warnings:
        suggested_next_action = "Review freshness context dan artifact utama, lalu pilih satu perbaikan kecil yang paling jelas dampaknya."
    elif artifact_build_ops or runtime_build_ops:
        suggested_next_action = "Review opportunity atau focus yang paling current, lalu pilih satu aksi kecil untuk dieksekusi."

    payload = {
        "date": generated_at[:10],
        "category": category,
        "generated_at": generated_at,
        "focus_today": focus_today,
        "opportunities": {
            "build": (artifact_build_ops + runtime_build_ops)[:3],
            "learn": memory_learn_ops[:3],
            "content": content_ops[:3],
            "review": (memory_review_ops + context_review_ops)[:3],
        },
        "risks_or_checks": risks_or_checks[:6],
        "suggested_next_action": suggested_next_action,
        "source_artifacts": {
            "digest": artifacts.get("digest") or {},
            "insight": artifacts.get("insight") or {},
            "assistant_context_json": assistant_context.get("json") or {},
            "assistant_context_markdown": assistant_context.get("markdown") or {},
            "runtime_statuses": {
                "count": len(runtime_dicts),
                "latest_paths": [item.get("path") for item in runtime_dicts[:5]],
                "exists": len(runtime_dicts) > 0,
                "modified_at": runtime_dicts[0].get("modified_at") if runtime_dicts else None,
                "path": runtime_dicts[0].get("path") if runtime_dicts else None,
            },
            "memory_provider": memory_source.provider,
        },
        "warnings": warnings,
        "diagnostics": {
            "status": "failed" if errors else ("success_with_warnings" if warnings else "success"),
            "errors": errors,
            "warnings": warnings,
        },
    }

    markdown_path, json_path = write_brief_outputs(payload)

    return AssistantBriefBuildResult(
        status=payload["diagnostics"]["status"],
        category=category,
        generated_at=generated_at,
        markdown_path=markdown_path,
        json_path=json_path,
        payload=payload,
        warnings=warnings,
        errors=errors,
    )
