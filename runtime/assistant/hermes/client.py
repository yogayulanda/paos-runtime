import json
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
    return _build_prompt_with_evidence(text=text, evidence_payload=None)


def _build_prompt_with_evidence(text: str, evidence_payload: dict | None) -> str:
    evidence_block = ""
    if evidence_payload:
        serialized = json.dumps(evidence_payload, ensure_ascii=False, separators=(",", ":"))
        evidence_block = (
            "\nPAOS_READ_EVIDENCE (authoritative, read-only):\n"
            f"{serialized[:2800]}\n"
        )

    return (
        "You are Hermes, reasoning/orchestration layer for PAOS Runtime Telegram free-text.\n"
        "PAOS Runtime is the control-plane, Telegram gateway, and deterministic fallback.\n"
        "Session context:\n"
        "- MCP server `paos` is connected and tools are discoverable in this runtime.\n"
        "- Phase 3 MCP read surfaces are implemented and available.\n"
        "- Writes are forbidden in this Telegram free-text flow.\n"
        "- If PAOS_READ_EVIDENCE is provided, treat it as authoritative runtime evidence.\n"
        "- Do not claim tool/context surface unavailable when evidence is present.\n"
        "- If evidence contains warnings/errors, report them honestly and give one next action.\n"
        "Respond in Indonesian by default, concise, and operationally grounded.\n"
        "Do not give generic product advice when PAOS state can be inspected.\n"
        "Do not claim tools are unavailable unless MCP/tool call actually fails in this run.\n"
        "For PAOS status/runtime/dashboard/context questions, prefer:\n"
        "- paos_runtime_status_get\n"
        "- paos_dashboard_get\n"
        "- paos_context_health_get\n"
        "For daily/focus questions, prefer:\n"
        "- paos_daily_get\n"
        "- paos_opportunities_get\n"
        "For handoff questions, prefer:\n"
        "- paos_handoff_get\n"
        "For draft/policy/next-implementation requests, prefer:\n"
        "- paos_action_policy_get\n"
        "- paos_action_draft_create\n"
        "For persistent action-loop requests, prefer:\n"
        "- paos_daily_action_generate\n"
        "- paos_action_list\n"
        "- paos_action_get\n"
        "- paos_action_event_list\n"
        "- paos_action_resolve\n"
        "- paos_action_state_transition\n"
        "For source/intelligence status questions, prefer:\n"
        "- paos_source_status_get\n"
        "Primitive read tools remain available:\n"
        "- paos_health\n"
        "- paos_context_get\n"
        "- paos_brief_get\n"
        "- paos_opportunities_get\n"
        "- paos_memory_recall\n"
        "Treat these as preferred evidence sources for Telegram free-text.\n"
        "Known roadmap priority:\n"
        "- Completed: provider activation, Telegram Hermes-first orchestration,\n"
        "  prompt/policy tuning, Phase 3 read surfaces, and Phase 4 draft boundary.\n"
        "- Current status: Phase 5 Persistent Action Loop local-state is active.\n"
        "- Main UX is conversational (e.g., 'pilih nomor 1', 'accept yang tadi').\n"
        "- Do not force slash commands for primary flow.\n"
        "Do not recommend Phase 3 as the next step unless user asks historical roadmap context.\n"
        "For 'next apa?' style questions, format answer as:\n"
        "1) Status saat ini\n"
        "2) Next step yang direkomendasikan (satu)\n"
        "3) Alasan\n"
        "4) Validasi/aksi konkret berikutnya\n"
        "Avoid endings like 'Kalau mau...' or 'Aku bisa...'.\n"
        "This flow is read-only:\n"
        "- Do not call paos_memory_write.\n"
        "- Do not apply controlled writes.\n"
        "- Do not mutate scheduler, GitHub, or repository state.\n"
        "- Mutation-like requests must be converted into draft output with clear no-apply notice.\n"
        "- Approval-required requests must include approval payload only, no execution path.\n"
        "- Blocked requests must refuse safely and must not include executable commands.\n"
        "- Action state transition is local persistence only (accepted != executed).\n"
        "- All state-changing outputs must include: 'No external action was applied.'\n"
        "- If execution is needed, propose steps instead of executing.\n\n"
        f"{evidence_block}"
        "User request:\n"
        f"{text.strip()}"
    )


def _detect_prefetch_tools(text: str) -> list[tuple[str, dict]]:
    normalized = str(text or "").strip().lower()
    picks: list[tuple[str, dict]] = []

    def has_any(*phrases: str) -> bool:
        return any(phrase in normalized for phrase in phrases)

    if has_any(
        "context sehat",
        "konteks sehat",
        "context saya sehat",
        "context saya sehat gak",
        "cek context",
        "cek konteks",
        "context health",
    ):
        picks.append(("paos_context_health_get", {}))

    if has_any("status paos", "kondisi paos", "ringkas kondisi", "paos sekarang", "status sekarang"):
        picks.append(("paos_runtime_status_get", {}))

    if has_any("dashboard", "dashboard paos"):
        picks.append(("paos_dashboard_get", {}))

    if has_any("hari ini fokus", "daily", "fokus hari ini"):
        picks.append(("paos_daily_get", {}))

    if has_any("handoff", "lanjut di codex", "lanjut di claude"):
        target = "generic"
        if "codex" in normalized:
            target = "codex"
        elif "claude" in normalized:
            target = "claude"
        elif "hermes" in normalized:
            target = "hermes"
        picks.append(("paos_handoff_get", {"target": target}))

    if has_any("draft", "rencana", "plan", "approval", "promosi memory"):
        picks.append(("paos_action_policy_get", {}))
        picks.append(("paos_action_draft_create", {"intent": normalized[:120]}))
    if has_any("buat action hari ini", "action pending", "accept yang tadi", "pilih nomor", "fokus saya sekarang"):
        picks.append(("paos_action_list", {"limit": 5}))
    if has_any("buat action hari ini", "daily action"):
        picks.append(("paos_daily_action_generate", {"category": "runtime", "persist": True}))

    if has_any("source status", "status source", "intelligence status"):
        picks.append(("paos_source_status_get", {}))

    # "next apa" type benefits from status + dashboard grounding.
    if has_any("next buat paos", "next apa", "selanjutnya apa"):
        if ("paos_runtime_status_get", {}) not in picks:
            picks.append(("paos_runtime_status_get", {}))
        if ("paos_dashboard_get", {}) not in picks:
            picks.append(("paos_dashboard_get", {}))

    return picks[:3]


def _prefetch_read_evidence(text: str) -> dict | None:
    requested = _detect_prefetch_tools(text)
    if not requested:
        return None
    payload: dict[str, object] = {"ok": True, "requested_tools": [], "errors": []}
    try:
        from assistant.mcp import server as mcp_server  # type: ignore
    except Exception as exc:
        payload["ok"] = False
        payload["errors"] = [f"prefetch import error: {exc}"]
        return payload

    tool_map = {
        "paos_context_health_get": getattr(mcp_server, "tool_paos_context_health_get", None),
        "paos_runtime_status_get": getattr(mcp_server, "tool_paos_runtime_status_get", None),
        "paos_dashboard_get": getattr(mcp_server, "tool_paos_dashboard_get", None),
        "paos_daily_get": getattr(mcp_server, "tool_paos_daily_get", None),
        "paos_handoff_get": getattr(mcp_server, "tool_paos_handoff_get", None),
        "paos_source_status_get": getattr(mcp_server, "tool_paos_source_status_get", None),
        "paos_action_policy_get": getattr(mcp_server, "tool_paos_action_policy_get", None),
        "paos_action_draft_create": getattr(mcp_server, "tool_paos_action_draft_create", None),
        "paos_action_list": getattr(mcp_server, "tool_paos_action_list", None),
        "paos_daily_action_generate": getattr(mcp_server, "tool_paos_daily_action_generate", None),
    }

    compact_results = []
    errors: list[str] = []
    for name, kwargs in requested:
        fn = tool_map.get(name)
        if not callable(fn):
            errors.append(f"{name}: not available")
            continue
        try:
            result = fn(**kwargs)
            compact_results.append(
                {
                    "tool": name,
                    "ok": bool((result or {}).get("ok")),
                    "generated_at": (result or {}).get("generated_at"),
                    "status": (result or {}).get("status"),
                    "summary": str((result or {}).get("summary") or "")[:240],
                    "warnings": (result or {}).get("warnings") or [],
                    "errors": (result or {}).get("errors") or [],
                    "sections": (result or {}).get("sections") or (result or {}).get("items") or {},
                }
            )
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    payload["requested_tools"] = compact_results
    payload["errors"] = errors
    payload["ok"] = len(errors) == 0
    return payload


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
    evidence_payload = _prefetch_read_evidence(text)
    prompt = _build_prompt_with_evidence(text=text, evidence_payload=evidence_payload)
    cmd = [
        "docker",
        "exec",
        "paos-hermes",
        "/workspace/paos-runtime/runtime/assistant/hermes/run_hermes.sh",
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
