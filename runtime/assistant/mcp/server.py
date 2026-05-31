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
from assistant.memory import MemoryQuery, MemoryWrite, load_memory_provider

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

        priorities: list[str] = []
        next_action = ""
        if isinstance(brief_payload, dict):
            focus = str(brief_payload.get("focus_today") or "").strip()
            if focus:
                priorities.append(focus)
            next_action = str(brief_payload.get("suggested_next_action") or "").strip()

        if isinstance(opportunities_payload, dict):
            for item in opportunities_payload.get("opportunities") or []:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if title and title not in priorities:
                    priorities.append(title)
                if len(priorities) >= 3:
                    break
                candidate_next = str(item.get("next_action") or "").strip()
                if not next_action and candidate_next:
                    next_action = candidate_next

        if not priorities:
            priorities = ["Belum ada prioritas; generate brief dan opportunities."]
        if not next_action:
            next_action = "Mulai dari prioritas nomor 1."

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


def tool_paos_source_status_get() -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        runtime_dir = _runtime_dir()
        statuses = _runtime_statuses(runtime_dir)
        artifacts = _artifacts_meta(runtime_dir)
        source_jobs = [
            item
            for item in statuses
            if str(item.get("job") or "").lower() in {"assistant-brief", "assistant-opportunities", "assistant-context"}
        ]
        if not source_jobs:
            warnings.append("no source pipeline statuses found in .runtime/runs")
        summary = (
            f"Source status: jobs={len(source_jobs)}, "
            f"digest={'yes' if artifacts['digest']['exists'] else 'no'}, "
            f"insight={'yes' if artifacts['insight']['exists'] else 'no'}."
        )
        return {
            "ok": True,
            "generated_at": _now_iso(),
            "source": "paos.mcp.source-status",
            "status": "ready" if source_jobs else "minimal",
            "summary": summary,
            "items": source_jobs[:10],
            "freshness": {
                "digest_date": artifacts["digest"]["date"],
                "insight_date": artifacts["insight"]["date"],
                "brief_date": artifacts["brief"]["date"],
                "opportunities_date": artifacts["opportunities"]["date"],
                "context_date": artifacts["context"]["date"],
            },
            "warnings": warnings,
            "errors": errors,
        }
    except Exception as exc:
        return _error_payload(
            warnings=warnings,
            errors=[str(exc)],
            generated_at=_now_iso(),
            source="paos.mcp.source-status",
            summary="failed to build source status",
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

    @server.tool(name="paos_source_status_get")
    def paos_source_status_get() -> dict[str, Any]:
        try:
            return tool_paos_source_status_get()
        except Exception as exc:
            return _error_payload(errors=[f"unexpected error: {exc}"])

    return server


def run_stdio_server() -> None:
    server = create_mcp_server()
    server.run(transport="stdio")
