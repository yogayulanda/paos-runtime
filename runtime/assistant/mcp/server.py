import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from assistant.config import resolve_category
from assistant.diagnostics import run_diagnostics
from assistant.brief import resolve_latest_assistant_brief
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

    return server


def run_stdio_server() -> None:
    server = create_mcp_server()
    server.run(transport="stdio")
