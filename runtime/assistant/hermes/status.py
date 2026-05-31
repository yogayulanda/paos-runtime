import os
import subprocess

from .client import query_hermes

TRUE_VALUES = {"1", "true", "yes", "on"}


def _load_file_env() -> dict[str, str]:
    try:
        from context.loader import load_env

        return load_env()
    except Exception:
        return {}


def _get_env_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None:
        return value
    file_env = _load_file_env()
    return file_env.get(name, default)


def hermes_orchestration_enabled() -> bool:
    raw = str(_get_env_value("PAOS_HERMES_ORCHESTRATION_ENABLED", "false") or "").strip().lower()
    return raw in TRUE_VALUES


def hermes_timeout_seconds(default: int = 45) -> int:
    raw = str(_get_env_value("PAOS_HERMES_TIMEOUT_SECONDS", str(default)) or "").strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(5, min(value, 120))


def hermes_available(timeout_seconds: int = 20) -> tuple[bool, str | None]:
    probe = query_hermes("Reply with exactly one word: READY", timeout_seconds=timeout_seconds)
    if probe.used and probe.response_text:
        return True, None
    return False, probe.error


def hermes_container_status(timeout_seconds: int = 4) -> str:
    cmd = [
        "docker",
        "ps",
        "--filter",
        "name=^/paos-hermes$",
        "--format",
        "{{.Status}}",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
    except Exception:
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    status = (proc.stdout or "").strip()
    if not status:
        return "not running"
    return status


def hermes_mcp_paos_status(timeout_seconds: int = 12) -> str:
    cmd = [
        "docker",
        "exec",
        "paos-hermes",
        "/workspace/paos-runtime/runtime/assistant/hermes/run_hermes.sh",
        "mcp",
        "test",
        "paos",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(3, int(timeout_seconds)),
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "unknown"
    output = f"{proc.stdout}\n{proc.stderr}".lower()
    if proc.returncode == 0 and "connected" in output:
        return "connected"
    if "connection failed" in output:
        return "connection failed"
    return "unknown"


def hermes_provider_status(timeout_seconds: int = 12) -> str:
    probe = query_hermes("Reply with exactly one word: READY", timeout_seconds=timeout_seconds)
    if probe.used and probe.response_text:
        return "configured"
    err = (probe.error or "").lower()
    if "no inference provider configured" in err:
        return "not configured"
    if "timeout" in err:
        return "timeout"
    if err:
        return "unknown"
    return "unknown"
