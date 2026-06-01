import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from assistant.config import resolve_category
from assistant.diagnostics import run_diagnostics
from assistant.brief import resolve_latest_assistant_brief
from assistant.opportunities import resolve_latest_assistant_opportunities
from assistant.memory import (
    MemoryQuery,
    MemoryWrite,
    build_personal_context_pack,
    create_candidate,
    direct_approved_write,
    list_candidates,
    load_memory_provider,
    memory_health_get,
    memory_profile_get,
    memory_relevant_get,
    working_context_get,
    transition_candidate,
)
from assistant.actions import create_action_draft, get_action_policy
from assistant.source_intelligence import (
    create_action_from_latest_insight,
    get_source_candidates,
    get_source_digest,
    get_source_insights,
    get_source_recommendation,
    get_source_status,
)
from assistant.agent_orchestration import (
    create_handoff as agent_handoff_create,
    create_memory_candidate_from_result as agent_memory_candidate_create,
    draft_next_action_from_result as agent_next_action_draft,
    get_handoff as agent_handoff_get,
    handoff_prompt as agent_handoff_prompt,
    list_handoffs as agent_handoff_list,
    review_result as agent_result_review,
)
from assistant.approval import (
    apply_approval,
    create_approval,
    decide_approval,
    get_approval,
    list_approvals,
    list_audit_events as approval_list_audit_events,
)
from assistant.action_loop import (
    accept_action,
    create_daily_action,
    defer_action,
    get_action as action_loop_get_action,
    list_actions as action_loop_list_actions,
    list_events as action_loop_list_events,
    reject_action,
    render_action_detail,
    render_action_list,
    resolve_action_reference,
)

from .schemas import (
    DEFAULT_CONTEXT_MAX_CHARS,
    DEFAULT_RECALL_LIMIT,
    MAX_RECALL_LIMIT,
    clamp_int,
    normalize_context_params,
    validate_content,
    validate_metadata,
)

ROOT = Path(__file__).resolve().parents[3]
CONTEXT_JOB = ROOT / "runtime" / "assistant" / "jobs" / "print_assistant_context.py"


class McpDependencyError(RuntimeError):
    pass


def _error_payload(
    *,
    category: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "category": category,
        "warnings": warnings or [],
        "errors": errors or ["unknown error"],
    }
    payload.update(extra)
    return payload


def _resolve_category(value: str | None) -> tuple[str, str]:
    resolved = resolve_category(value)
    return resolved.value, resolved.source


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None

def _age_days(value: Any) -> int | None:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 86400))

def _is_stale_daily_string(value: Any) -> bool:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return False
    stale_markers = (
        "paos v3 setup selesai",
        "setup selesai",
        "fully operational",
        "auto-sync",
        "daily action draft",
        "draft aksi harian",
        "build opportunity",
        "regenerate brief",
        "use latest digest",
        "latest digest",
        "execute today focus",
        "validate current implementation against latest insight assumptions",
        "latest digest as execution anchor",
        "runtime pipeline looks healthy",
        "apply one concrete task from the latest digest",
    )
    return any(marker in lowered for marker in stale_markers)


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _runtime_dir() -> Path:
    runtime_path = ROOT / "runtime"
    env_file = ROOT / ".env"
    if env_file.exists():
        try:
            for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "PAOS_RUNTIME_PATH":
                    candidate = Path(value.strip().strip('"').strip("'"))
                    if candidate.exists():
                        return candidate
        except Exception:
            pass
    return runtime_path


def _resolve_latest_file(root_dir: Path, filename: str) -> Path | None:
    if not root_dir.exists() or not root_dir.is_dir():
        return None
    candidates = sorted(
        [path for path in root_dir.glob(f"*/{filename}") if path.is_file()],
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _artifacts_meta(runtime_dir: Path) -> dict[str, dict[str, Any]]:
    brief = _resolve_latest_file(runtime_dir / "assistant" / "briefs", "assistant-brief.json")
    opportunities = _resolve_latest_file(runtime_dir / "assistant" / "opportunities", "opportunities.json")
    context = _resolve_latest_file(runtime_dir / "assistant" / "context", "assistant-context.json")
    digest = _resolve_latest_file(runtime_dir / "intelligence" / "digests", "ai.md")
    insight = _resolve_latest_file(runtime_dir / "intelligence" / "insights", "ai.md")

    def _meta(path: Path | None) -> dict[str, Any]:
        return {
            "exists": bool(path),
            "date": path.parent.name if path else None,
            "path": str(path) if path else None,
        }

    return {
        "brief": _meta(brief),
        "opportunities": _meta(opportunities),
        "context": _meta(context),
        "digest": _meta(digest),
        "insight": _meta(insight),
    }


def _runtime_statuses(runtime_dir: Path) -> list[dict[str, Any]]:
    runs_dir = runtime_dir / ".runtime" / "runs"
    statuses: list[dict[str, Any]] = []
    if not runs_dir.exists() or not runs_dir.is_dir():
        return statuses
    for status_path in sorted(runs_dir.glob("*/latest.json")):
        payload = _read_json_file(status_path)
        if not payload:
            continue
        statuses.append(
            {
                "job": payload.get("job") or status_path.parent.name,
                "status": payload.get("status") or "unknown",
                "finished_at": payload.get("finished_at"),
                "path": str(status_path),
            }
        )
    return statuses


def _load_hermes_env() -> dict[str, str]:
    env_path = Path("/opt/data/.env")
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _load_paos_env() -> dict[str, str]:
    env_path = ROOT / ".env"
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _safe_memory_provider_dict(selection) -> dict[str, Any]:
    # Provider selection has no secrets; keep this explicit boundary.
    return selection.to_dict()


def tool_paos_health(category: str | None = None, include_diagnostics: bool = True) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
    except Exception as exc:
        return _error_payload(errors=[f"category resolution failed: {exc}"])

    selection = load_memory_provider()
    provider_payload = _safe_memory_provider_dict(selection)

    diagnostics_status = "skipped"
    if include_diagnostics:
        try:
            diagnostics = run_diagnostics(resolved_category)
            diagnostics_status = str(diagnostics.get("status") or "unknown")
            warnings.extend([str(item) for item in diagnostics.get("warnings") or []])
            errors.extend([str(item) for item in diagnostics.get("errors") or []])
        except Exception as exc:
            errors.append(f"diagnostics failed: {exc}")
            diagnostics_status = "failed"

    ok = not errors
    return {
        "ok": ok,
        "category": resolved_category,
        "category_source": category_source,
        "memory_provider": provider_payload,
        "diagnostics_status": diagnostics_status,
        "warnings": warnings,
        "errors": errors,
    }


def tool_paos_memory_write(
    content: str,
    scope: str | None = None,
    category: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        body = validate_content(content)
        safe_metadata = validate_metadata(metadata)
        write_scope = scope if scope is not None else resolved_category

        selection = load_memory_provider()
        result = selection.provider.write(
            MemoryWrite(content=body, scope=write_scope, metadata=safe_metadata)
        )

        if result.warning:
            warnings.append(str(result.warning))
        if not result.ok:
            errors.append("memory write failed")

        return {
            "ok": not errors,
            "category": resolved_category,
            "category_source": category_source,
            "memory_provider": _safe_memory_provider_dict(selection),
            "result": result.to_dict(),
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(category=category, warnings=warnings, errors=[str(exc)])


def tool_paos_memory_recall(
    query: str = "",
    scope: str | None = None,
    category: str | None = None,
    limit: int = DEFAULT_RECALL_LIMIT,
) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        selection = load_memory_provider()
        bounded_limit = clamp_int(limit, 1, MAX_RECALL_LIMIT)
        recall_scope = scope if scope is not None else resolved_category
        items = selection.provider.recall(
            MemoryQuery(text=str(query or ""), scope=recall_scope, limit=bounded_limit)
        )

        return {
            "ok": True,
            "category": resolved_category,
            "category_source": category_source,
            "memory_provider": _safe_memory_provider_dict(selection),
            "items": [item.to_dict() for item in items],
            "warnings": warnings,
            "errors": [],
        }
    except Exception as exc:
        return _error_payload(category=category, warnings=warnings, errors=[str(exc)], items=[])


def tool_paos_memory_profile_get(
    scope: str | None = None,
    category: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    try:
        return memory_profile_get(scope=scope, category=category, limit=limit)
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])


def tool_paos_memory_relevant_get(
    query: str = "",
    category: str | None = None,
    scope: str | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    try:
        return memory_relevant_get(query=query, category=category, scope=scope, limit=limit)
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)], items=[])


def tool_paos_working_context_get(category: str | None = None) -> dict[str, Any]:
    try:
        resolved_category, category_source = _resolve_category(category)
        payload = working_context_get(category=resolved_category)
        payload["category"] = resolved_category
        payload["category_source"] = category_source
        return payload
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])


def tool_paos_memory_candidate_create(
    content: str,
    type: str | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    evidence_summary: str | None = None,
    confidence: float = 0.7,
) -> dict[str, Any]:
    try:
        return create_candidate(
            content,
            memory_type=type,
            source_type=source_type,
            source_ref=source_ref,
            evidence_summary=evidence_summary,
            confidence=confidence,
        )
    except Exception as exc:
        return _error_payload(errors=[str(exc)])


def tool_paos_memory_candidate_list(status: str | None = None, limit: int = 10) -> dict[str, Any]:
    try:
        return list_candidates(status=status, limit=limit)
    except Exception as exc:
        return _error_payload(errors=[str(exc)], items=[])


def tool_paos_memory_candidate_transition(candidate_id: str, transition: str) -> dict[str, Any]:
    return _error_payload(
        errors=["direct_memory_candidate_transition_blocked_use_approval"],
        source="paos.mcp.memory-candidate.transition",
        summary="Blocked in v1.5a: explicit approval + apply required.",
    )


def tool_paos_memory_approved_write(
    content: str,
    type: str | None,
    source_type: str,
    source_ref: str,
    evidence_summary: str,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return _error_payload(
        errors=["direct_memory_write_blocked_use_approval"],
        source="paos.mcp.memory-approved-write",
        summary="Blocked in v1.5a: explicit approval + apply required.",
    )


def tool_paos_approval_propose(
    source: str,
    requested_by: str,
    proposed_operation: str,
    operation_type: str,
    evidence_refs: list[str] | None = None,
    payload_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return create_approval(
            source=source,
            requested_by=requested_by,
            proposed_operation=proposed_operation,
            operation_type=operation_type,
            evidence_refs=evidence_refs,
            payload_preview=payload_preview,
        )
    except Exception as exc:
        return _error_payload(errors=[str(exc)])


def tool_paos_approval_list(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    try:
        return list_approvals(status=status, limit=limit)
    except Exception as exc:
        return _error_payload(errors=[str(exc)], items=[])


def tool_paos_approval_get(approval_id: str) -> dict[str, Any]:
    try:
        return get_approval(approval_id)
    except Exception as exc:
        return _error_payload(errors=[str(exc)])


def tool_paos_approval_decide(approval_id: str, decision: str, actor: str = "mcp") -> dict[str, Any]:
    try:
        return decide_approval(approval_id=approval_id, decision=decision, actor=actor)
    except Exception as exc:
        return _error_payload(errors=[str(exc)])


def tool_paos_approval_apply(approval_id: str, actor: str = "mcp") -> dict[str, Any]:
    try:
        return apply_approval(approval_id=approval_id, actor=actor)
    except Exception as exc:
        return _error_payload(errors=[str(exc)])


def tool_paos_approval_audit_list(approval_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    try:
        return approval_list_audit_events(approval_id=approval_id, limit=limit)
    except Exception as exc:
        return _error_payload(errors=[str(exc)], items=[])


def tool_paos_memory_health_get() -> dict[str, Any]:
    try:
        return memory_health_get()
    except Exception as exc:
        return _error_payload(errors=[str(exc)])


def tool_paos_context_get(
    category: str | None = None,
    format: str = "json",
    section: str = "all",
    max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        out_format, out_section, bounded_chars = normalize_context_params(format, section, max_chars)

        cmd = [
            sys.executable,
            str(CONTEXT_JOB),
            "--category",
            resolved_category,
            "--format",
            out_format,
            "--section",
            out_section,
            "--max-chars",
            str(bounded_chars),
        ]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip() or (proc.stdout or "").strip()
            errors.append(f"context command failed: {stderr}")
            return _error_payload(
                category=resolved_category,
                warnings=warnings,
                errors=errors,
                format=out_format,
                section=out_section,
            )

        raw = proc.stdout
        if out_format == "json":
            try:
                content = json.loads(raw)
            except Exception as exc:
                errors.append(f"context output is not valid JSON: {exc}")
                return _error_payload(
                    category=resolved_category,
                    warnings=warnings,
                    errors=errors,
                    format=out_format,
                    section=out_section,
                )
        else:
            content = raw

        return {
            "ok": True,
            "category": resolved_category,
            "category_source": category_source,
            "format": out_format,
            "section": out_section,
            "max_chars": bounded_chars,
            "content": content,
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(category=category, warnings=warnings, errors=[str(exc)])


def tool_paos_brief_get(category: str | None = None, format: str = "json") -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        out_format = str(format or "json").strip().lower()
        if out_format not in {"json", "markdown"}:
            raise ValueError(f"invalid format: {out_format}")

        resolution = resolve_latest_assistant_brief()
        warnings.extend([str(item) for item in resolution.warnings])
        artifact = resolution.json if out_format == "json" else resolution.markdown
        if not artifact.exists or not artifact.path:
            errors.append(f"assistant brief {out_format} artifact is missing")
            return _error_payload(
                category=resolved_category,
                warnings=warnings,
                errors=errors,
                format=out_format,
                content=None,
                brief=resolution.to_dict(),
            )

        path = Path(artifact.path)
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if out_format == "json":
            try:
                content = json.loads(raw)
            except Exception as exc:
                errors.append(f"assistant brief JSON parse failure: {exc}")
                return _error_payload(
                    category=resolved_category,
                    warnings=warnings,
                    errors=errors,
                    format=out_format,
                    content=None,
                    brief=resolution.to_dict(),
                )
        else:
            content = raw

        return {
            "ok": True,
            "category": resolved_category,
            "category_source": category_source,
            "format": out_format,
            "content": content,
            "brief": resolution.to_dict(),
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(category=category, warnings=warnings, errors=[str(exc)])


def tool_paos_opportunities_get(category: str | None = None, format: str = "json") -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        out_format = str(format or "json").strip().lower()
        if out_format not in {"json", "markdown"}:
            raise ValueError(f"invalid format: {out_format}")

        resolution = resolve_latest_assistant_opportunities()
        warnings.extend([str(item) for item in resolution.warnings])
        artifact = resolution.json if out_format == "json" else resolution.markdown
        if not artifact.exists or not artifact.path:
            errors.append(f"assistant opportunities {out_format} artifact is missing")
            return _error_payload(
                category=resolved_category,
                warnings=warnings,
                errors=errors,
                format=out_format,
                content=None,
                opportunities=resolution.to_dict(),
            )

        path = Path(artifact.path)
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if out_format == "json":
            try:
                content = json.loads(raw)
            except Exception as exc:
                errors.append(f"assistant opportunities JSON parse failure: {exc}")
                return _error_payload(
                    category=resolved_category,
                    warnings=warnings,
                    errors=errors,
                    format=out_format,
                    content=None,
                    opportunities=resolution.to_dict(),
                )
        else:
            content = raw

        return {
            "ok": True,
            "category": resolved_category,
            "category_source": category_source,
            "format": out_format,
            "content": content,
            "opportunities": resolution.to_dict(),
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(category=category, warnings=warnings, errors=[str(exc)])


def tool_paos_dashboard_get(category: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        runtime_dir = _runtime_dir()
        artifacts = _artifacts_meta(runtime_dir)
        statuses = _runtime_statuses(runtime_dir)
        brief_payload = _read_json_file(Path(artifacts["brief"]["path"])) if artifacts["brief"]["path"] else {}
        opportunities_payload = (
            _read_json_file(Path(artifacts["opportunities"]["path"])) if artifacts["opportunities"]["path"] else {}
        )

        focus = ""
        if isinstance(brief_payload, dict):
            focus = str(brief_payload.get("focus_today") or "").strip()
        top_opportunities: list[str] = []
        if isinstance(opportunities_payload, dict):
            for item in opportunities_payload.get("opportunities") or []:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if title:
                    top_opportunities.append(title)
                if len(top_opportunities) >= 3:
                    break

        loaded_count = sum(1 for item in artifacts.values() if item.get("exists"))
        summary = (
            f"Dashboard PAOS: {loaded_count}/5 artifact loaded; "
            f"focus='{focus or 'belum ada'}'; "
            f"top opportunities={len(top_opportunities)}."
        )
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.dashboard",
            "category": resolved_category,
            "category_source": category_source,
            "freshness": {k: v.get("date") for k, v in artifacts.items()},
            "summary": summary,
            "sections": {
                "focus_today": focus or None,
                "top_opportunities": top_opportunities,
                "artifacts": artifacts,
                "runtime_jobs": statuses[:10],
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.dashboard",
            summary="failed to build dashboard",
        )


def tool_paos_daily_get(category: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        runtime_dir = _runtime_dir()
        artifacts = _artifacts_meta(runtime_dir)
        brief_payload = _read_json_file(Path(artifacts["brief"]["path"])) if artifacts["brief"]["path"] else {}
        opportunities_payload = (
            _read_json_file(Path(artifacts["opportunities"]["path"])) if artifacts["opportunities"]["path"] else {}
        )
        operating = tool_paos_operating_summary_get(category=resolved_category)
        context_pack = build_personal_context_pack("daily focus summary", relevant_limit=3)

        priorities: list[str] = []
        next_action = ""
        if isinstance(brief_payload, dict):
            focus = str(brief_payload.get("focus_today") or "").strip()
            if focus and not _is_stale_daily_string(focus):
                priorities.append(focus)
            next_action = str(brief_payload.get("suggested_next_action") or "").strip()
            if _is_stale_daily_string(next_action):
                next_action = ""

        if isinstance(opportunities_payload, dict):
            for item in opportunities_payload.get("opportunities") or []:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if title and not _is_stale_daily_string(title) and title not in priorities:
                    priorities.append(title)
                if len(priorities) >= 3:
                    break
                candidate_next = str(item.get("next_action") or "").strip()
                if not next_action and candidate_next and not _is_stale_daily_string(candidate_next):
                    next_action = candidate_next

        operating_focus = str((((operating.get("sections") or {}).get("focus") or {}).get("current_focus") or "")).strip()
        context_focus = str(context_pack.get("current_focus_summary") or "").strip()
        if operating_focus and not _is_stale_daily_string(operating_focus) and operating_focus not in priorities:
            priorities.insert(0, operating_focus)
        elif context_focus and not _is_stale_daily_string(context_focus) and context_focus not in priorities:
            priorities.insert(0, context_focus)

        operating_next = str(((operating.get("sections") or {}).get("recommended_next_safe_step") or "")).strip()
        if not next_action and operating_next and not _is_stale_daily_string(operating_next):
            next_action = operating_next

        if not priorities:
            priorities = ["Belum ada prioritas yang benar-benar segar; cek operating summary terbaru lalu pilih satu aksi kecil."]
        if not next_action:
            next_action = "Cek operating summary terbaru lalu pilih satu next action kecil yang paling aman divalidasi."

        summary = (
            f"Daily PAOS: {len(priorities[:3])} prioritas aktif; "
            f"next action='{next_action[:120]}'."
        )
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.daily",
            "category": resolved_category,
            "category_source": category_source,
            "freshness": {k: v.get("date") for k, v in artifacts.items()},
            "summary": summary,
            "items": {"priorities": priorities[:3], "next_action": next_action},
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.daily",
            summary="failed to build daily",
        )


def tool_paos_context_health_get(category: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        runtime_dir = _runtime_dir()
        artifacts = _artifacts_meta(runtime_dir)
        context_payload = _read_json_file(Path(artifacts["context"]["path"])) if artifacts["context"]["path"] else {}
        statuses = _runtime_statuses(runtime_dir)
        failed_jobs = [item for item in statuses if str(item.get("status") or "").lower() in {"failed", "error"}]

        diagnostics = context_payload.get("diagnostics") if isinstance(context_payload, dict) else {}
        if isinstance(diagnostics, dict):
            warnings.extend([str(item) for item in diagnostics.get("warnings") or []][:8])

        loaded = {
            "context": bool(artifacts["context"]["exists"]),
            "brief": bool(artifacts["brief"]["exists"]),
            "opportunities": bool(artifacts["opportunities"]["exists"]),
        }
        health_status = "healthy" if all(loaded.values()) and not failed_jobs else "degraded"
        summary = (
            f"Context health {health_status}; "
            f"context={loaded['context']}, brief={loaded['brief']}, opportunities={loaded['opportunities']}, "
            f"failed_jobs={len(failed_jobs)}."
        )
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.context-health",
            "category": resolved_category,
            "category_source": category_source,
            "status": health_status,
            "freshness": {k: v.get("date") for k, v in artifacts.items()},
            "summary": summary,
            "sections": {
                "artifact_status": loaded,
                "failed_runtime_jobs": failed_jobs[:5],
                "warning_count": len(warnings),
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.context-health",
            summary="failed to build context health",
        )


def tool_paos_handoff_get(target: str = "generic", category: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        runtime_dir = _runtime_dir()
        artifacts = _artifacts_meta(runtime_dir)
        brief_payload = _read_json_file(Path(artifacts["brief"]["path"])) if artifacts["brief"]["path"] else {}
        opportunities_payload = (
            _read_json_file(Path(artifacts["opportunities"]["path"])) if artifacts["opportunities"]["path"] else {}
        )
        context_payload = _read_json_file(Path(artifacts["context"]["path"])) if artifacts["context"]["path"] else {}

        handoff_target = str(target or "generic").strip().lower()
        if handoff_target not in {"generic", "codex", "claude", "hermes"}:
            handoff_target = "generic"

        focus = str(brief_payload.get("focus_today") or "").strip() if isinstance(brief_payload, dict) else ""
        next_action = (
            str(brief_payload.get("suggested_next_action") or "").strip() if isinstance(brief_payload, dict) else ""
        )
        top_opportunities: list[str] = []
        if isinstance(opportunities_payload, dict):
            for item in opportunities_payload.get("opportunities") or []:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if title:
                    top_opportunities.append(title)
                if len(top_opportunities) >= 3:
                    break

        sections = context_payload.get("sections") if isinstance(context_payload, dict) else {}
        decisions = sections.get("decisions") if isinstance(sections, dict) else []
        blockers = sections.get("blockers") if isinstance(sections, dict) else []
        decisions = [str(x).strip() for x in (decisions or []) if str(x).strip()][:3]
        blockers = [str(x).strip() for x in (blockers or []) if str(x).strip()][:3]

        summary = (
            f"Handoff {handoff_target}: "
            f"focus='{focus or 'n/a'}', next_action='{(next_action or 'n/a')[:100]}', "
            f"top_opportunities={len(top_opportunities)}."
        )
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.handoff",
            "category": resolved_category,
            "category_source": category_source,
            "status": "ready",
            "summary": summary,
            "sections": {
                "target": handoff_target,
                "task_summary": focus or "Lanjutkan prioritas assistant terbaru.",
                "next_action": next_action or "Eksekusi top opportunity terbaru.",
                "top_opportunities": top_opportunities,
                "decisions": decisions,
                "blockers": blockers,
                "artifacts": artifacts,
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.handoff",
            summary="failed to build handoff",
        )


def tool_paos_runtime_status_get() -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        hermes_env = _load_hermes_env()
        paos_env = _load_paos_env()
        orchestration_config_enabled = _parse_bool(paos_env.get("PAOS_HERMES_ORCHESTRATION_ENABLED"))
        telegram_orchestration_env = "unknown"
        # This tool is served through PAOS MCP itself; if invoked successfully, MCP link is connected.
        mcp_health = "connected"
        paos_telegram_bot_status = "unknown"

        gateway_running = False
        wrapper_path = Path("/workspace/paos-runtime/runtime/assistant/hermes/run_hermes.sh")
        cmd: list[str] | None = None
        if wrapper_path.exists():
            cmd = [str(wrapper_path), "gateway", "status"]
        elif shutil.which("docker"):
            cmd = [
                "docker",
                "exec",
                "paos-hermes",
                "sh",
                "-lc",
                "/workspace/paos-runtime/runtime/assistant/hermes/run_hermes.sh gateway status || true",
            ]

        if cmd is None:
            warnings.append("gateway status probe unavailable: no local wrapper path and docker not available")
        else:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                output = f"{proc.stdout}\n{proc.stderr}".lower()
                gateway_running = "gateway is running" in output
            except Exception as exc:
                warnings.append(f"gateway status probe failed: {exc}")

        provider_reachable = "unknown"
        base = hermes_env.get("HERMES_LLM_BASE_URL")
        key = hermes_env.get("HERMES_LLM_API_KEY")
        if base and key:
            try:
                req = Request(
                    base.rstrip("/") + "/models",
                    headers={"Authorization": f"Bearer {key}"},
                    method="GET",
                )
                with urlopen(req, timeout=8) as resp:
                    provider_reachable = "yes" if int(resp.status) == 200 else "no"
            except HTTPError as exc:
                provider_reachable = "no"
                warnings.append(f"provider probe http_error={exc.code}")
            except Exception as exc:
                provider_reachable = "no"
                warnings.append(f"provider probe failed: {exc}")

        hermes_gateway_status = "running" if gateway_running else "stopped_expected"
        orchestration_label = (
            str(orchestration_config_enabled).lower() if orchestration_config_enabled is not None else "unknown"
        )
        summary = (
            f"Runtime status: orchestration_config_enabled={orchestration_label}, "
            f"telegram_orchestration_env={telegram_orchestration_env}, fallback_enabled=true, "
            f"mcp_paos={mcp_health}, provider_reachable={provider_reachable}, "
            f"hermes_gateway_status={hermes_gateway_status}, paos_telegram_bot_status={paos_telegram_bot_status}."
        )
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.runtime-status",
            "status": "ready",
            "summary": summary,
            "sections": {
                "orchestration_config_enabled": orchestration_config_enabled,
                "hermes_orchestration_enabled": orchestration_config_enabled,
                "telegram_orchestration_env": telegram_orchestration_env,
                "fallback_enabled": True,
                "mcp_paos_health": mcp_health,
                "provider_reachable": provider_reachable,
                "hermes_gateway_status": hermes_gateway_status,
                "paos_telegram_bot_status": paos_telegram_bot_status,
                "gateway_running": gateway_running,
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.runtime-status",
            summary="failed to build runtime status",
        )


def tool_paos_agent_handoff_create(
    target_agent: str | None = None,
    source: str | None = None,
    action_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    payload = agent_handoff_prompt(target_agent=target_agent, source=source, action_id=action_id, category=category)
    return {
        "ok": bool(payload.get("ok")),
        "generated_at": _now_iso(),
        "source": "paos.mcp.agent-handoff.create",
        "status": "ready",
        "summary": str(payload.get("summary") or "Handoff dibuat sebagai draft/manual prompt."),
        "sections": {
            "handoff": payload.get("handoff"),
            "prompt": payload.get("prompt"),
            "notice": "No external action was applied.",
        },
        "warnings": [],
        "errors": [],
    }


def tool_paos_agent_handoff_get(handoff_id: str | None = None) -> dict[str, Any]:
    payload = agent_handoff_get(handoff_id=handoff_id)
    return {
        "ok": bool(payload.get("ok")),
        "generated_at": _now_iso(),
        "source": "paos.mcp.agent-handoff.get",
        "status": "ready" if payload.get("ok") else "degraded",
        "summary": "Handoff detail loaded." if payload.get("ok") else "handoff not found",
        "sections": {"handoff": payload.get("handoff"), "notice": "No external action was applied."},
        "warnings": [],
        "errors": payload.get("errors") or [],
    }


def tool_paos_agent_handoff_list(status: str | None = None, limit: int = 10) -> dict[str, Any]:
    payload = agent_handoff_list(status=status, limit=limit)
    return {
        "ok": bool(payload.get("ok")),
        "generated_at": _now_iso(),
        "source": "paos.mcp.agent-handoff.list",
        "status": "ready",
        "summary": f"Listed {len(payload.get('items') or [])} handoff(s).",
        "sections": {"handoffs": payload.get("items") or [], "notice": "No external action was applied."},
        "warnings": [],
        "errors": [],
    }


def tool_paos_agent_result_review(content: str, target_agent: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
    payload = agent_result_review(content=content, target_agent=target_agent, handoff_id=handoff_id)
    return {
        "ok": bool(payload.get("ok")),
        "generated_at": _now_iso(),
        "source": "paos.mcp.agent-result.review",
        "status": "ready",
        "summary": str(payload.get("summary") or "Agent result direview secara lokal."),
        "sections": {"review": payload.get("review"), "notice": "No external action was applied."},
        "warnings": [],
        "errors": payload.get("errors") or [],
    }


def tool_paos_agent_next_action_draft(content: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
    payload = agent_next_action_draft(content=content, handoff_id=handoff_id)
    return {
        "ok": bool(payload.get("ok")),
        "generated_at": _now_iso(),
        "source": "paos.mcp.agent-result.next-action-draft",
        "status": "ready",
        "summary": str(payload.get("summary") or "Draft next action dibuat (local-only)."),
        "sections": {"draft": payload.get("draft"), "notice": "No external action was applied."},
        "warnings": [],
        "errors": payload.get("errors") or [],
    }


def tool_paos_agent_memory_candidate_create(
    content: str | None = None,
    handoff_id: str | None = None,
    target_agent: str | None = None,
) -> dict[str, Any]:
    payload = agent_memory_candidate_create(content=content, handoff_id=handoff_id, target_agent=target_agent)
    return {
        "ok": bool(payload.get("ok")),
        "generated_at": _now_iso(),
        "source": "paos.mcp.agent-result.memory-candidate",
        "status": "ready" if payload.get("ok") else "degraded",
        "summary": str(payload.get("summary") or "Memory candidate dibuat dari hasil agent."),
        "sections": {"candidate": payload.get("candidate"), "notice": "No external action was applied."},
        "warnings": [],
        "errors": payload.get("errors") or [],
    }


def tool_paos_source_status_get() -> dict[str, Any]:
    try:
        return get_source_status(category="ai").payload
    except Exception as exc:
        return _error_payload(
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.source-status",
            summary="failed to build source status",
        )


def tool_paos_source_digest_get(category: str | None = None, limit: int = 8) -> dict[str, Any]:
    try:
        resolved_category, category_source = _resolve_category(category)
        payload = get_source_digest(category=resolved_category, limit=limit)
        payload["category_source"] = category_source
        return payload
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])


def tool_paos_source_insight_get(category: str | None = None, limit: int = 5) -> dict[str, Any]:
    try:
        resolved_category, category_source = _resolve_category(category)
        payload = get_source_insights(category=resolved_category, limit=limit)
        payload["category_source"] = category_source
        return payload
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])


def tool_paos_source_candidates_get(
    category: str | None = None,
    source: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    try:
        resolved_category, category_source = _resolve_category(category)
        payload = get_source_candidates(category=resolved_category, source=source, limit=limit)
        payload["category_source"] = category_source
        return payload
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])


def tool_paos_source_recommendation_get(category: str | None = None) -> dict[str, Any]:
    try:
        resolved_category, category_source = _resolve_category(category)
        payload = get_source_recommendation(category=resolved_category)
        payload["category_source"] = category_source
        return payload
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])

def tool_paos_operating_summary_get(category: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        runtime = tool_paos_runtime_status_get()
        source = tool_paos_source_status_get()
        memory = tool_paos_memory_health_get()
        actions = tool_paos_action_list(limit=40)
        context_pack = build_personal_context_pack("pagi fokus sekarang", relevant_limit=3)

        accepted = [a for a in (actions.get("sections", {}).get("actions") or []) if a.get("state") == "accepted"]
        proposed = [a for a in (actions.get("sections", {}).get("actions") or []) if a.get("state") == "proposed"]
        deferred = [a for a in (actions.get("sections", {}).get("actions") or []) if a.get("state") == "deferred"]

        current_focus = (accepted[0] if accepted else (proposed[0] if proposed else None)) or {}
        current_focus_title = str(current_focus.get("title") or "Belum ada accepted action")
        stale_focus_markers = (
            "phase 9",
            "runtime-stable external agent orchestration",
            "daily action draft",
            "draft aksi harian",
            "build opportunity",
            "regenerate brief",
        )
        current_focus_stale = any(marker in current_focus_title.lower() for marker in stale_focus_markers)
        focus_state = str(current_focus.get("state") or "none")
        context_focus_summary = str(context_pack.get("current_focus_summary") or "").strip()
        background_summary = str(context_pack.get("background_summary") or "").strip()
        if current_focus_stale or not current_focus.get("title"):
            if context_focus_summary:
                current_focus_title = context_focus_summary
            else:
                current_focus_title = "Belum ada fokus aktif yang cukup segar; perlu cross-check summary terbaru."
            if current_focus_stale:
                focus_state = "background"

        latest_insight = "Belum ada insight terbaru."
        insight_payload = tool_paos_source_insight_get(category=resolved_category, limit=1)
        if insight_payload.get("ok") and (insight_payload.get("items") or []):
            top = (insight_payload.get("items") or [])[0]
            latest_insight = str(top.get("title") or top.get("summary") or "Insight terbaru tersedia")[:180]

        source_candidate_count = int(source.get("candidate_count") or 0)
        memory_candidate_count = int(memory.get("candidate_count") or 0)
        gateway_running = bool((runtime.get("sections") or {}).get("gateway_running"))

        stale_signals: list[str] = []
        oldest_proposed_days = None
        oldest_deferred_days = None
        for row in proposed:
            age = _age_days(row.get("updated_at") or row.get("created_at"))
            if age is not None:
                oldest_proposed_days = age if oldest_proposed_days is None else max(oldest_proposed_days, age)
        for row in deferred:
            age = _age_days(row.get("updated_at") or row.get("created_at"))
            if age is not None:
                oldest_deferred_days = age if oldest_deferred_days is None else max(oldest_deferred_days, age)

        source_artifacts = source.get("artifacts") if isinstance(source.get("artifacts"), dict) else {}
        source_digest_date = (source_artifacts.get("digest") or {}).get("date") if source_artifacts else None
        source_insight_date = (source_artifacts.get("insight") or {}).get("date") if source_artifacts else None

        if oldest_proposed_days is not None and oldest_proposed_days >= 3:
            stale_signals.append(f"Ada proposed action lama (~{oldest_proposed_days} hari).")
        if oldest_deferred_days is not None and oldest_deferred_days >= 7:
            stale_signals.append(f"Ada deferred action lama (~{oldest_deferred_days} hari).")
        if source_candidate_count == 0:
            stale_signals.append("Candidate source kosong; cek collector/candidate pool.")
        if current_focus_stale:
            stale_signals.append("Current focus yang terpilih masih terlalu generik; cross-check dengan current-state atau evidence terbaru.")
        stale_signals.extend([str(x) for x in context_pack.get("stale_or_background_warnings") or []][:3])
        if memory_candidate_count >= 5:
            stale_signals.append(f"Candidate memory pending {memory_candidate_count}; review approval/reject.")
        if gateway_running:
            stale_signals.append("Gateway Hermes terdeteksi running; seharusnya stopped.")
        if not source_digest_date or not source_insight_date:
            stale_signals.append("Artifact source digest/insight belum lengkap.")

        warnings.extend([str(x) for x in runtime.get("warnings") or []][:4])
        warnings.extend([str(x) for x in source.get("warnings") or []][:4])
        warnings.extend([str(x) for x in memory.get("warnings") or []][:4])

        blockers = [x for x in stale_signals if "running" in x.lower() or "kosong" in x.lower()]
        if runtime.get("errors"):
            errors.extend([str(x) for x in runtime.get("errors") or []][:4])
        if source.get("errors"):
            errors.extend([str(x) for x in source.get("errors") or []][:4])
        if memory.get("errors"):
            errors.extend([str(x) for x in memory.get("errors") or []][:4])

        recommended_next_step = "Cross-check focus aktif dengan current-state dan evidence terbaru, lalu pilih satu langkah yang paling aman untuk divalidasi."
        if gateway_running:
            recommended_next_step = "Pastikan Hermes gateway tetap stopped, lalu cek runtime status ulang."
        elif source_candidate_count == 0:
            recommended_next_step = "Jalankan ulang collector + candidate pool agar insight/source tidak kosong."
        elif focus_state != "accepted":
            recommended_next_step = "Tetapkan satu accepted action yang paling segar agar fokus harian tidak melebar."
        elif context_focus_summary and focus_state == "background":
            recommended_next_step = "Fokus action saat ini masih terlalu generik; cek operating summary terbaru lalu pilih satu next action kecil yang tervalidasi."

        summary = (
            f"PAOS hari ini: runtime={runtime.get('status', 'unknown')}, gateway={((runtime.get('sections') or {}).get('hermes_gateway_status') or 'unknown')}, "
            f"focus='{current_focus_title[:90]}', pending={len(proposed) + len(deferred)}, "
            f"source_candidates={source_candidate_count}, memory_candidates={memory_candidate_count}."
        )

        return {
            "ok": len(errors) == 0,
            "generated_at": _now_iso(),
            "source": "paos.mcp.operating-summary",
            "category": resolved_category,
            "category_source": category_source,
            "status": "ready" if not errors else "degraded",
            "summary": summary,
            "sections": {
                "runtime_health": {
                    "status": runtime.get("status"),
                    "summary": runtime.get("summary"),
                },
                "hermes": {
                    "mcp_paos_health": ((runtime.get("sections") or {}).get("mcp_paos_health")),
                    "hermes_gateway_status": ((runtime.get("sections") or {}).get("hermes_gateway_status")),
                    "gateway_running": gateway_running,
                },
                "focus": {
                    "current_focus": current_focus_title,
                    "focus_state": focus_state,
                    "background_summary": background_summary,
                    "latest_accepted_action": accepted[0] if accepted else None,
                    "pending_action_count": len(proposed) + len(deferred),
                },
                "source_intelligence": {
                    "status": source.get("status"),
                    "summary": source.get("summary"),
                    "latest_insight_summary": latest_insight,
                    "candidate_count": source_candidate_count,
                },
                "memory_health": {
                    "summary": memory.get("summary"),
                    "active_count": memory.get("active_count"),
                    "pending_candidate_count": memory_candidate_count,
                },
                "staleness_signals": stale_signals,
                "warnings_blockers": blockers,
                "recommended_next_safe_step": recommended_next_step,
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.operating-summary",
            summary="failed to build operating summary",
        )

def tool_paos_daily_plan_get(category: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        resolved_category, category_source = _resolve_category(category)
        operating = tool_paos_operating_summary_get(category=resolved_category)
        actions = tool_paos_action_list(limit=20)
        memory = tool_paos_memory_relevant_get(query="fokus harian prioritas kerja", category=resolved_category, limit=4)
        insight = tool_paos_source_insight_get(category=resolved_category, limit=1)

        accepted = [a for a in (actions.get("sections", {}).get("actions") or []) if a.get("state") == "accepted"]
        proposed = [a for a in (actions.get("sections", {}).get("actions") or []) if a.get("state") == "proposed"]
        focus = accepted[0] if accepted else (proposed[0] if proposed else None)

        plan_items: list[str] = []
        if focus:
            plan_items.append(f"Eksekusi fokus utama: {str(focus.get('title') or '')[:140]} (tetap local tracking).")
        else:
            plan_items.append("Belum ada fokus accepted; pilih satu proposed action paling relevan.")

        insight_item = (insight.get("items") or [None])[0]
        if isinstance(insight_item, dict):
            insight_title = str(insight_item.get("title") or insight_item.get("summary") or "Insight terbaru")[:140]
            plan_items.append(f"Gunakan insight terbaru: {insight_title} untuk validasi prioritas hari ini.")
        else:
            plan_items.append("Insight terbaru belum tersedia; lakukan cek source status dan candidates.")

        mem_items = memory.get("items") or []
        if mem_items:
            top_mem = str(mem_items[0].get("content") or "")[:120]
            plan_items.append(f"Selaraskan eksekusi dengan memory aktif: {top_mem}.")
        else:
            plan_items.append("Memory relevan minim; gunakan memory profile ringkas untuk alignment kerja.")

        plan_items.append("Tutup loop hari ini: review pending action + candidate memory, lalu tetapkan next step aman.")

        proposed_local_action = {
            "title": "Review operating summary + finalize next safe step",
            "summary": "Rangkum status runtime/action/source/memory dan pilih satu langkah aman berikutnya.",
            "steps": [
                "Cek warning/blocker pada operating summary.",
                "Pilih satu pending action untuk accept/defer/reject.",
                "Konfirmasi next step operasional paling aman untuk hari ini.",
            ],
            "apply_mechanism_available": False,
            "notice": "No external action was applied.",
        }

        evidence = {
            "operating_summary": str(operating.get("summary") or "")[:200],
            "focus": str((focus or {}).get("title") or "belum ada")[:120],
            "memory_points": [str(item.get("content") or "")[:100] for item in mem_items[:2]],
            "insight": str((insight_item or {}).get("title") or (insight_item or {}).get("summary") or "")[:120],
        }

        summary = "Daily plan tersusun dari context + action loop + memory + source. No external action was applied."
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.daily-plan",
            "category": resolved_category,
            "category_source": category_source,
            "status": "ready",
            "summary": summary,
            "sections": {
                "daily_plan": plan_items,
                "proposed_local_action": proposed_local_action,
                "evidence_summary": evidence,
                "recommended_next_safe_step": (operating.get("sections") or {}).get("recommended_next_safe_step"),
                "notice": "No external action was applied.",
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.daily-plan",
            summary="failed to build daily plan",
        )


def tool_paos_source_action_draft_create(
    reference: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    try:
        resolved_category, category_source = _resolve_category(category)
        payload = create_action_from_latest_insight(category=resolved_category, reference=reference)
        payload["category"] = resolved_category
        payload["category_source"] = category_source
        return payload
    except Exception as exc:
        return _error_payload(category=category, errors=[str(exc)])


def tool_paos_action_policy_get() -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.action-policy",
            "status": "ready",
            "summary": "Phase 4 draft-only action policy.",
            "sections": {"policy": get_action_policy()},
            "warnings": [],
            "errors": [],
        }
    except Exception as exc:
        return _error_payload(
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.action-policy",
            summary="failed to load action policy",
        )


def tool_paos_action_draft_create(
    intent: str,
    target: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.action-draft",
            "status": "ready",
            "summary": "Draft generated with approval boundary. No action was applied.",
            "sections": {"draft": create_action_draft(intent=intent, target=target, category=category)},
            "warnings": [],
            "errors": [],
        }
    except Exception as exc:
        return _error_payload(
            category=category,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.action-draft",
            summary="failed to generate action draft",
        )


def tool_paos_action_list(state: str | None = None, limit: int = 20) -> dict[str, Any]:
    actions = action_loop_list_actions(state=state, limit=limit)
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "source": "paos.mcp.action-loop.list",
        "summary": f"Listed {len(actions)} actions.",
        "sections": {
            "actions": [item.to_dict() for item in actions],
            "rendered": render_action_list(actions, title="PAOS Action Inbox"),
        },
        "warnings": [],
        "errors": [],
    }


def tool_paos_action_get(action_id: str) -> dict[str, Any]:
    action = action_loop_get_action(action_id)
    if not action:
        return _error_payload(
            errors=["action_not_found"],
            generated_at=_now_iso(),
            source="paos.mcp.action-loop.get",
            summary="action not found",
        )
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "source": "paos.mcp.action-loop.get",
        "summary": "Action detail loaded.",
        "sections": {"action": action.to_dict(), "rendered": render_action_detail(action)},
        "warnings": [],
        "errors": [],
    }


def tool_paos_action_event_list(action_id: str | None = None, limit: int = 30) -> dict[str, Any]:
    events = action_loop_list_events(action_id=action_id, limit=limit)
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "source": "paos.mcp.action-loop.events",
        "summary": f"Listed {len(events)} events.",
        "sections": {"events": [item.to_dict() for item in events]},
        "warnings": [],
        "errors": [],
    }


def tool_paos_daily_action_generate(category: str = "runtime", persist: bool = True) -> dict[str, Any]:
    result = create_daily_action(category=category, persist=persist, actor="mcp")
    return {
        "ok": result.ok,
        "generated_at": _now_iso(),
        "source": "paos.mcp.action-loop.daily-generate",
        "summary": result.message,
        "sections": result.to_dict(),
        "warnings": result.warnings,
        "errors": result.errors,
    }


def tool_paos_action_resolve(
    reference: str | None = None,
    ordinal: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    action = resolve_action_reference(reference=reference or "", ordinal=ordinal, query=query)
    if not action:
        return _error_payload(
            errors=["reference_not_resolved"],
            generated_at=_now_iso(),
            source="paos.mcp.action-loop.resolve",
            summary="reference unresolved",
        )
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "source": "paos.mcp.action-loop.resolve",
        "summary": "Reference resolved.",
        "sections": {"action": action.to_dict(), "rendered": render_action_detail(action)},
        "warnings": [],
        "errors": [],
    }


def tool_paos_action_state_transition(action_id: str, transition: str, note: str | None = None) -> dict[str, Any]:
    return _error_payload(
        errors=["direct_action_transition_blocked_use_approval"],
        generated_at=_now_iso(),
        source="paos.mcp.action-loop.transition",
        summary="Blocked in v1.5a: explicit approval + apply required.",
    )


def _load_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise McpDependencyError(
            "MCP dependency is missing. Install with: venv/bin/pip install mcp"
        ) from exc
    return FastMCP


def create_mcp_server():
    FastMCP = _load_fastmcp()
    server = FastMCP("paos-mcp")

    @server.tool(name="paos_health")
    def paos_health(category: str | None = None, include_diagnostics: bool = True) -> dict[str, Any]:
        try:
            return tool_paos_health(category=category, include_diagnostics=include_diagnostics)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_memory_write")
    def paos_memory_write(
        content: str,
        scope: str | None = None,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Safety-sensitive memory mutation tool. Forbidden in normal Telegram/Hermes free-text flow."""
        try:
            return tool_paos_memory_write(
                content=content,
                scope=scope,
                category=category,
                metadata=metadata,
            )
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_memory_recall")
    def paos_memory_recall(
        query: str = "",
        scope: str | None = None,
        category: str | None = None,
        limit: int = DEFAULT_RECALL_LIMIT,
    ) -> dict[str, Any]:
        try:
            return tool_paos_memory_recall(query=query, scope=scope, category=category, limit=limit)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"], items=[])

    @server.tool(name="paos_memory_profile_get")
    def paos_memory_profile_get(
        scope: str | None = None,
        category: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        return tool_paos_memory_profile_get(scope=scope, category=category, limit=limit)

    @server.tool(name="paos_memory_relevant_get")
    def paos_memory_relevant_get(
        query: str = "",
        category: str | None = None,
        scope: str | None = None,
        limit: int = 6,
    ) -> dict[str, Any]:
        return tool_paos_memory_relevant_get(query=query, category=category, scope=scope, limit=limit)

    @server.tool(name="paos_working_context_get")
    def paos_working_context_get(category: str | None = None) -> dict[str, Any]:
        return tool_paos_working_context_get(category=category)

    @server.tool(name="paos_memory_candidate_create")
    def paos_memory_candidate_create(
        content: str,
        type: str | None = None,
        source_type: str | None = None,
        source_ref: str | None = None,
        evidence_summary: str | None = None,
        confidence: float = 0.7,
    ) -> dict[str, Any]:
        return tool_paos_memory_candidate_create(
            content=content,
            type=type,
            source_type=source_type,
            source_ref=source_ref,
            evidence_summary=evidence_summary,
            confidence=confidence,
        )

    @server.tool(name="paos_memory_candidate_list")
    def paos_memory_candidate_list(status: str | None = None, limit: int = 10) -> dict[str, Any]:
        return tool_paos_memory_candidate_list(status=status, limit=limit)

    @server.tool(name="paos_memory_candidate_transition")
    def paos_memory_candidate_transition(candidate_id: str, transition: str) -> dict[str, Any]:
        return tool_paos_memory_candidate_transition(candidate_id=candidate_id, transition=transition)

    @server.tool(name="paos_memory_approved_write")
    def paos_memory_approved_write(
        content: str,
        type: str | None,
        source_type: str,
        source_ref: str,
        evidence_summary: str,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        """Approval-safe memory write entrypoint for normal orchestration flows."""
        return tool_paos_memory_approved_write(
            content=content,
            type=type,
            source_type=source_type,
            source_ref=source_ref,
            evidence_summary=evidence_summary,
            confidence=confidence,
        )

    @server.tool(name="paos_memory_health_get")
    def paos_memory_health_get() -> dict[str, Any]:
        return tool_paos_memory_health_get()

    @server.tool(name="paos_approval_propose")
    def paos_approval_propose(
        source: str,
        requested_by: str,
        proposed_operation: str,
        operation_type: str,
        evidence_refs: list[str] | None = None,
        payload_preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return tool_paos_approval_propose(
            source=source,
            requested_by=requested_by,
            proposed_operation=proposed_operation,
            operation_type=operation_type,
            evidence_refs=evidence_refs,
            payload_preview=payload_preview,
        )

    @server.tool(name="paos_approval_list")
    def paos_approval_list(status: str | None = None, limit: int = 20) -> dict[str, Any]:
        return tool_paos_approval_list(status=status, limit=limit)

    @server.tool(name="paos_approval_get")
    def paos_approval_get(approval_id: str) -> dict[str, Any]:
        return tool_paos_approval_get(approval_id=approval_id)

    @server.tool(name="paos_approval_decide")
    def paos_approval_decide(approval_id: str, decision: str, actor: str = "mcp") -> dict[str, Any]:
        return tool_paos_approval_decide(approval_id=approval_id, decision=decision, actor=actor)

    @server.tool(name="paos_approval_apply")
    def paos_approval_apply(approval_id: str, actor: str = "mcp") -> dict[str, Any]:
        return tool_paos_approval_apply(approval_id=approval_id, actor=actor)

    @server.tool(name="paos_approval_audit_list")
    def paos_approval_audit_list(approval_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        return tool_paos_approval_audit_list(approval_id=approval_id, limit=limit)

    @server.tool(name="paos_context_get")
    def paos_context_get(
        category: str | None = None,
        format: str = "json",
        section: str = "all",
        max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
    ) -> dict[str, Any]:
        try:
            return tool_paos_context_get(
                category=category,
                format=format,
                section=section,
                max_chars=max_chars,
            )
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_brief_get")
    def paos_brief_get(category: str | None = None, format: str = "json") -> dict[str, Any]:
        try:
            return tool_paos_brief_get(category=category, format=format)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_opportunities_get")
    def paos_opportunities_get(category: str | None = None, format: str = "json") -> dict[str, Any]:
        try:
            return tool_paos_opportunities_get(category=category, format=format)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_dashboard_get")
    def paos_dashboard_get(category: str | None = None) -> dict[str, Any]:
        try:
            return tool_paos_dashboard_get(category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_daily_get")
    def paos_daily_get(category: str | None = None) -> dict[str, Any]:
        try:
            return tool_paos_daily_get(category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_context_health_get")
    def paos_context_health_get(category: str | None = None) -> dict[str, Any]:
        try:
            return tool_paos_context_health_get(category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_handoff_get")
    def paos_handoff_get(target: str = "generic", category: str | None = None) -> dict[str, Any]:
        try:
            return tool_paos_handoff_get(target=target, category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_runtime_status_get")
    def paos_runtime_status_get() -> dict[str, Any]:
        try:
            return tool_paos_runtime_status_get()
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_agent_handoff_create")
    def paos_agent_handoff_create(
        target_agent: str | None = None,
        source: str | None = None,
        action_id: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        return tool_paos_agent_handoff_create(
            target_agent=target_agent,
            source=source,
            action_id=action_id,
            category=category,
        )

    @server.tool(name="paos_agent_handoff_get")
    def paos_agent_handoff_get(handoff_id: str | None = None) -> dict[str, Any]:
        return tool_paos_agent_handoff_get(handoff_id=handoff_id)

    @server.tool(name="paos_agent_handoff_list")
    def paos_agent_handoff_list(status: str | None = None, limit: int = 10) -> dict[str, Any]:
        return tool_paos_agent_handoff_list(status=status, limit=limit)

    @server.tool(name="paos_agent_result_review")
    def paos_agent_result_review(content: str, target_agent: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
        return tool_paos_agent_result_review(content=content, target_agent=target_agent, handoff_id=handoff_id)

    @server.tool(name="paos_agent_next_action_draft")
    def paos_agent_next_action_draft(content: str | None = None, handoff_id: str | None = None) -> dict[str, Any]:
        return tool_paos_agent_next_action_draft(content=content, handoff_id=handoff_id)

    @server.tool(name="paos_agent_memory_candidate_create")
    def paos_agent_memory_candidate_create(
        content: str | None = None,
        handoff_id: str | None = None,
        target_agent: str | None = None,
    ) -> dict[str, Any]:
        return tool_paos_agent_memory_candidate_create(content=content, handoff_id=handoff_id, target_agent=target_agent)

    @server.tool(name="paos_operating_summary_get")
    def paos_operating_summary_get(category: str | None = None) -> dict[str, Any]:
        """Compact daily operating summary across runtime, action loop, source intelligence, and memory health."""
        try:
            return tool_paos_operating_summary_get(category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_daily_plan_get")
    def paos_daily_plan_get(category: str | None = None) -> dict[str, Any]:
        """Draft-only daily plan from context, memory, source intelligence, and local action loop."""
        try:
            return tool_paos_daily_plan_get(category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_action_policy_get")
    def paos_action_policy_get() -> dict[str, Any]:
        try:
            payload = tool_paos_action_policy_get()
            payload["policy"] = payload.get("sections", {}).get("policy")
            return payload
        except Exception as exc:
            return _error_payload(
                errors=[str(exc)],
                generated_at=_now_iso(),
                source="paos.mcp.action-policy",
                summary="failed to load action policy",
            )

    @server.tool(name="paos_action_draft_create")
    def paos_action_draft_create(intent: str, target: str | None = None, category: str | None = None) -> dict[str, Any]:
        try:
            payload = tool_paos_action_draft_create(intent=intent, target=target, category=category)
            payload["draft"] = payload.get("sections", {}).get("draft")
            return payload
        except Exception as exc:
            return _error_payload(
                category=category,
                errors=[str(exc)],
                generated_at=_now_iso(),
                source="paos.mcp.action-draft",
                summary="failed to generate action draft",
            )

    @server.tool(name="paos_source_status_get")
    def paos_source_status_get() -> dict[str, Any]:
        try:
            return tool_paos_source_status_get()
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_source_digest_get")
    def paos_source_digest_get(category: str | None = None, limit: int = 8) -> dict[str, Any]:
        try:
            return tool_paos_source_digest_get(category=category, limit=limit)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_source_insight_get")
    def paos_source_insight_get(category: str | None = None, limit: int = 5) -> dict[str, Any]:
        try:
            return tool_paos_source_insight_get(category=category, limit=limit)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_source_candidates_get")
    def paos_source_candidates_get(
        category: str | None = None,
        source: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        try:
            return tool_paos_source_candidates_get(category=category, source=source, limit=limit)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_source_recommendation_get")
    def paos_source_recommendation_get(category: str | None = None) -> dict[str, Any]:
        try:
            return tool_paos_source_recommendation_get(category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_source_action_draft_create")
    def paos_source_action_draft_create(
        reference: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Create local proposed action from latest source insight. Draft-only and no external apply."""
        try:
            return tool_paos_source_action_draft_create(reference=reference, category=category)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_action_list")
    def paos_action_list(state: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List local action-loop items (read-only). Use for pending/accepted inbox views."""
        try:
            return tool_paos_action_list(state=state, limit=limit)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_action_get")
    def paos_action_get(action_id: str) -> dict[str, Any]:
        """Get one local action detail by id (read-only)."""
        try:
            return tool_paos_action_get(action_id=action_id)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_action_event_list")
    def paos_action_event_list(action_id: str | None = None, limit: int = 30) -> dict[str, Any]:
        """List local action-loop events (append-only history read)."""
        try:
            return tool_paos_action_event_list(action_id=action_id, limit=limit)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_daily_action_generate")
    def paos_daily_action_generate(category: str = "runtime", persist: bool = True) -> dict[str, Any]:
        """Generate daily action draft and optionally persist as local proposed action. No external apply."""
        try:
            return tool_paos_daily_action_generate(category=category, persist=persist)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_action_resolve")
    def paos_action_resolve(
        reference: str | None = None,
        ordinal: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Resolve natural references like 'nomor 1' or 'yang tadi' to a local action id."""
        try:
            return tool_paos_action_resolve(reference=reference, ordinal=ordinal, query=query)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    @server.tool(name="paos_action_state_transition")
    def paos_action_state_transition(action_id: str, transition: str, note: str | None = None) -> dict[str, Any]:
        """Transition local action-loop state only (accepted/rejected/deferred). Never executes external actions."""
        try:
            return tool_paos_action_state_transition(action_id=action_id, transition=transition, note=note)
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    return server


def run_stdio_server() -> None:
    server = create_mcp_server()
    server.run(transport="stdio")
