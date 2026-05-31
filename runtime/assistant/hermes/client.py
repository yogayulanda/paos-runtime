import subprocess
import time
from dataclasses import dataclass


DEFAULT_HERMES_TIMEOUT_SECONDS = 45


@dataclass
class HermesQueryResult:
    available: bool
    used: bool
    response_text: str
    error: str | None
    duration_seconds: float


def _build_prompt(text: str) -> str:
    return (
        "You are Hermes orchestrating PAOS Runtime for a Telegram free-text request.\n"
        "Use PAOS MCP tools for context when needed.\n"
        "This flow is read-only:\n"
        "- Do not call paos_memory_write.\n"
        "- Do not apply controlled writes.\n"
        "- Do not mutate scheduler, GitHub, or repository state.\n"
        "- If execution is needed, propose steps instead of executing.\n\n"
        "User request:\n"
        f"{text.strip()}"
    )


def _clean_error(stderr: str, stdout: str) -> str:
    for raw in (stderr, stdout):
        text = str(raw or "").strip()
        if text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                return lines[-1][:600]
    return "hermes invocation failed"


def query_hermes(
    text: str,
    timeout_seconds: int = DEFAULT_HERMES_TIMEOUT_SECONDS,
) -> HermesQueryResult:
    started = time.monotonic()
    prompt = _build_prompt(text)
    cmd = [
        "docker",
        "exec",
        "paos-hermes",
        "/opt/hermes/.venv/bin/hermes",
        "--accept-hooks",
        "-z",
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - started
        return HermesQueryResult(
            available=False,
            used=False,
            response_text="",
            error=f"hermes timeout after {timeout_seconds}s",
            duration_seconds=duration,
        )
    except Exception as exc:
        duration = time.monotonic() - started
        return HermesQueryResult(
            available=False,
            used=False,
            response_text="",
            error=str(exc),
            duration_seconds=duration,
        )

    duration = time.monotonic() - started
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode == 0 and stdout:
        return HermesQueryResult(
            available=True,
            used=True,
            response_text=stdout[:3900],
            error=None,
            duration_seconds=duration,
        )

    return HermesQueryResult(
        available=False,
        used=False,
        response_text="",
        error=_clean_error(stderr, stdout),
        duration_seconds=duration,
    )
