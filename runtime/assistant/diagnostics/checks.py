from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import json

from assistant.artifacts import resolve_artifacts
from assistant.brief import resolve_latest_assistant_brief
from assistant.config import CONFIG_PATH, load_assistant_config
from assistant.context import resolve_latest_assistant_context
from assistant.memory import load_memory_provider
from assistant.opportunities import resolve_latest_assistant_opportunities


ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT / ".runtime" / "runs"
CONSUMPTION_COMMAND_PATH = ROOT / "runtime" / "assistant" / "jobs" / "print_assistant_context.py"
CONSUMPTION_CONTRACT_PATH = ROOT / "runtime" / "assistant" / "contracts" / "context-consumption.md"
CONSUMPTION_SUPPORTED_SECTIONS = ["all", "profile", "memory", "runtime", "intelligence"]
CONSUMPTION_SUPPORTED_FORMATS = ["markdown", "json"]
CONSUMPTION_DEFAULT_MAX_CHARS = 12000


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


def _context_consumption_diagnostics() -> dict:
    warnings: list[str] = []
    errors: list[str] = []

    command_exists = CONSUMPTION_COMMAND_PATH.exists() and CONSUMPTION_COMMAND_PATH.is_file()
    contract_exists = CONSUMPTION_CONTRACT_PATH.exists() and CONSUMPTION_CONTRACT_PATH.is_file()

    latest_context = resolve_latest_assistant_context()
    latest_json_path = latest_context.json.path
    latest_json_exists = latest_context.json.exists
    latest_context_date = latest_context.json.date or latest_context.markdown.date
    json_parseable = bool(latest_context.json.parseable) if latest_json_exists else False

    if not command_exists:
        errors.append(f"missing consumption command: {CONSUMPTION_COMMAND_PATH}")
    if not contract_exists:
        errors.append(f"missing context consumption contract: {CONSUMPTION_CONTRACT_PATH}")

    if not latest_json_exists:
        warnings.append("latest assistant context JSON artifact is missing")
    elif not json_parseable:
        warnings.append("latest assistant context JSON artifact is not parseable")
    else:
        try:
            _ = json.loads(Path(latest_json_path).read_text(encoding="utf-8"))
        except Exception as exc:
            json_parseable = False
            warnings.append(f"latest assistant context JSON parse failure: {exc}")

    warnings.extend(latest_context.warnings)

    status = "success"
    if errors:
        status = "failed"
    elif warnings:
        status = "warning"

    return {
        "status": status,
        "command_path": str(CONSUMPTION_COMMAND_PATH),
        "command_exists": command_exists,
        "contract_path": str(CONSUMPTION_CONTRACT_PATH),
        "contract_exists": contract_exists,
        "latest_context_path": latest_json_path,
        "latest_context_exists": latest_json_exists,
        "latest_context_date": latest_context_date,
        "json_parseable": json_parseable,
        "supported_sections": CONSUMPTION_SUPPORTED_SECTIONS,
        "supported_formats": CONSUMPTION_SUPPORTED_FORMATS,
        "default_max_chars": CONSUMPTION_DEFAULT_MAX_CHARS,
        "warnings": warnings,
        "errors": errors,
    }


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

    assistant_brief = resolve_latest_assistant_brief()
    brief_json = assistant_brief.json
    if assistant_brief.markdown.exists or brief_json.exists:
        checks.append(
            _ok(
                "assistant_brief_resolution",
                f"Resolved assistant brief markdown: {assistant_brief.markdown.path}; JSON: {brief_json.path}",
                required=False,
            )
        )
    else:
        msg = "No assistant brief artifact found."
        checks.append(_warn("assistant_brief_resolution", msg, required=False))
        warnings.append(f"assistant_brief_resolution: {msg}")

    today = datetime.now().astimezone().date().isoformat()
    if brief_json.exists:
        if brief_json.empty:
            warnings.append("assistant_brief: latest JSON brief is empty")
        if brief_json.parseable is False:
            warnings.append("assistant_brief: latest JSON brief is not parseable")
        if brief_json.date and brief_json.date < today:
            warnings.append(
                f"assistant_brief: latest brief is stale ({brief_json.date}); expected {today}"
            )
    warnings.extend(assistant_brief.warnings)

    assistant_opportunities = resolve_latest_assistant_opportunities()
    opportunities_json = assistant_opportunities.json
    if assistant_opportunities.markdown.exists or opportunities_json.exists:
        checks.append(
            _ok(
                "assistant_opportunities_resolution",
                f"Resolved assistant opportunities markdown: {assistant_opportunities.markdown.path}; JSON: {opportunities_json.path}",
                required=False,
            )
        )
    else:
        msg = "No assistant opportunities artifact found."
        checks.append(_warn("assistant_opportunities_resolution", msg, required=False))
        warnings.append(f"assistant_opportunities_resolution: {msg}")

    if opportunities_json.exists:
        if opportunities_json.empty:
            warnings.append("assistant_opportunities: latest JSON opportunities artifact is empty")
        if opportunities_json.parseable is False:
            warnings.append("assistant_opportunities: latest JSON opportunities artifact is not parseable")
        if opportunities_json.date and opportunities_json.date < today:
            warnings.append(
                f"assistant_opportunities: latest opportunities are stale ({opportunities_json.date}); expected {today}"
            )
    warnings.extend(assistant_opportunities.warnings)

    context_consumption = _context_consumption_diagnostics()
    if context_consumption["status"] == "failed":
        errors.extend([f"context_consumption: {item}" for item in context_consumption["errors"]])
    elif context_consumption["status"] == "warning":
        warnings.extend([f"context_consumption: {item}" for item in context_consumption["warnings"]])

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
        "assistant_brief": assistant_brief.to_dict(),
        "assistant_opportunities": assistant_opportunities.to_dict(),
        "context_consumption": context_consumption,
        "resolved_artifacts": artifacts.to_dict(),
    }
