from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from assistant.artifacts import resolve_artifacts
from assistant.config import CONFIG_PATH, load_assistant_config
from assistant.context import resolve_latest_assistant_context
from assistant.memory import load_memory_provider


ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT / ".runtime" / "runs"


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    message: str
    required: bool


def _ok(name: str, message: str, required: bool = True) -> DiagnosticCheck:
    return DiagnosticCheck(name=name, status="ok", message=message, required=required)


def _warn(name: str, message: str, required: bool = False) -> DiagnosticCheck:
    return DiagnosticCheck(name=name, status="warning", message=message, required=required)


def _error(name: str, message: str, required: bool = True) -> DiagnosticCheck:
    return DiagnosticCheck(name=name, status="error", message=message, required=required)


def run_diagnostics(category: str) -> dict:
    checks: list[DiagnosticCheck] = []
    warnings: list[str] = []
    errors: list[str] = []

    try:
        config = load_assistant_config()
        checks.append(
            _ok(
                "assistant_config_readable",
                f"Loaded assistant config with categories: {', '.join(config.categories)}",
            )
        )
    except Exception as exc:
        checks.append(_error("assistant_config_readable", str(exc)))
        errors.append(f"assistant_config_readable: {exc}")

    if CONFIG_PATH.exists() and CONFIG_PATH.is_file():
        checks.append(_ok("assistant_config_file_exists", f"Config path: {CONFIG_PATH}"))
    else:
        checks.append(_error("assistant_config_file_exists", f"Missing config path: {CONFIG_PATH}"))
        errors.append(f"assistant_config_file_exists: missing {CONFIG_PATH}")

    artifacts = resolve_artifacts(category=category)

    if artifacts.digest.exists:
        checks.append(_ok("latest_digest_resolution", f"Resolved digest: {artifacts.digest.path}"))
    else:
        msg = "No digest markdown resolved for category."
        checks.append(_warn("latest_digest_resolution", msg, required=False))
        warnings.append(f"latest_digest_resolution: {msg}")

    if artifacts.insight.exists:
        checks.append(_ok("latest_insight_resolution", f"Resolved insight: {artifacts.insight.path}"))
    else:
        msg = "No insight markdown resolved for category."
        checks.append(_warn("latest_insight_resolution", msg, required=False))
        warnings.append(f"latest_insight_resolution: {msg}")

    if RUNS_DIR.exists() and RUNS_DIR.is_dir():
        try:
            _ = list(RUNS_DIR.iterdir())
            checks.append(_ok("runtime_status_dir_readable", f"Runs directory: {RUNS_DIR}"))
        except OSError as exc:
            msg = f"Runtime status directory is not readable: {RUNS_DIR} ({exc})"
            checks.append(_error("runtime_status_dir_readable", msg))
            errors.append(f"runtime_status_dir_readable: {msg}")
    else:
        msg = f"Runtime status directory is missing or not readable: {RUNS_DIR}"
        checks.append(_error("runtime_status_dir_readable", msg))
        errors.append(f"runtime_status_dir_readable: {msg}")

    assistant_context = resolve_latest_assistant_context()
    if assistant_context.markdown.exists or assistant_context.json.exists:
        checks.append(
            _ok(
                "assistant_context_resolution",
                f"Resolved assistant context markdown: {assistant_context.markdown.path}; JSON: {assistant_context.json.path}",
            )
        )
    else:
        msg = "No assistant context artifact found."
        checks.append(_warn("assistant_context_resolution", msg, required=False))
        warnings.append(f"assistant_context_resolution: {msg}")

    warnings.extend(assistant_context.warnings)

    memory_selection = load_memory_provider()
    configured_health = memory_selection.configured_health
    active_health = memory_selection.active_health

    if not configured_health.healthy or configured_health.warning:
        warnings.append(
            "memory_provider_configured: "
            f"{memory_selection.configured_provider} - {configured_health.message}"
        )

    if memory_selection.fallback_used:
        warnings.append(
            "memory_provider: configured provider "
            f"{memory_selection.configured_provider} unavailable; "
            f"fallback {memory_selection.active_provider} is active"
        )

    if active_health.healthy:
        if active_health.warning:
            checks.append(
                _warn(
                    "memory_provider_health",
                    f"{memory_selection.active_provider}: {active_health.message}",
                )
            )
            warnings.append(f"memory_provider_health: {active_health.message}")
        else:
            checks.append(
                _ok(
                    "memory_provider_health",
                    f"{memory_selection.active_provider}: {active_health.message}",
                )
            )
    else:
        message = (
            f"{memory_selection.active_provider}: {active_health.message}"
            if active_health.message
            else f"Memory provider {memory_selection.active_provider} is unavailable."
        )
        checks.append(_error("memory_provider_health", message))
        errors.append(f"memory_provider_health: {message}")

    status = "success"
    if errors:
        status = "failed"
    elif warnings:
        status = "success_with_warnings"

    return {
        "status": status,
        "category": category,
        "generated_at": datetime.now().astimezone().isoformat(),
        "checks": [asdict(check) for check in checks],
        "warnings": warnings,
        "errors": errors,
        "memory_provider": memory_selection.to_dict(),
        "assistant_context": assistant_context.to_dict(),
        "resolved_artifacts": artifacts.to_dict(),
    }
