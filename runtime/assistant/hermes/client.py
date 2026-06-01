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
        "For source/intelligence questions, prefer:\n"
        "- paos_source_status_get\n"
        "- paos_source_digest_get\n"
        "- paos_source_insight_get\n"
        "- paos_source_candidates_get\n"
        "- paos_source_recommendation_get\n"
        "- paos_source_action_draft_create\n"
        "Primitive read tools remain available:\n"
        "- paos_health\n"
        "- paos_context_get\n"
        "- paos_brief_get\n"
        "- paos_opportunities_get\n"
        "- paos_memory_recall\n"
        "- paos_memory_profile_get\n"
        "- paos_memory_relevant_get\n"
        "- paos_memory_candidate_list\n"
        "- paos_memory_health_get\n"
        "Treat these as preferred evidence sources for Telegram free-text.\n"
        "Known roadmap priority:\n"
        "- Completed: provider activation, Telegram Hermes-first orchestration,\n"
        "  prompt/policy tuning, Phase 3 read surfaces, Phase 4 draft boundary,\n"
        "  and Phase 5 persistent action loop.\n"
        "- Current status: Phase 9 runtime-stable external agent orchestration active.\n"
        "- Main UX is conversational (e.g., 'pilih nomor 1', 'accept yang tadi').\n"
        "- Do not force slash commands for primary flow.\n"
        "- Do not recommend command-heavy flows as primary UX.\n"
        "For broad daily status/focus/next-step questions, prefer composed summary:\n"
        "- paos_operating_summary_get\n"
        "For daily plan request, prefer:\n"
        "- paos_daily_plan_get\n"
        "For external-agent handoff/review prompts, prefer:\n"
        "- paos_agent_handoff_create\n"
        "- paos_agent_handoff_get\n"
        "- paos_agent_handoff_list\n"
        "- paos_agent_result_review\n"
        "- paos_agent_next_action_draft\n"
        "- paos_agent_memory_candidate_create\n"
        "For 'next apa?' style questions, format answer as:\n"
        "1) Status saat ini\n"
        "2) Next step yang direkomendasikan (satu)\n"
        "3) Alasan\n"
        "4) Validasi/aksi konkret berikutnya\n"
        "Avoid endings like 'Kalau mau...' or 'Aku bisa...'.\n"
        "This flow is approval-safe:\n"
        "- Never call paos_memory_write directly for free-text writes.\n"
        "- Use paos_memory_approved_write only for explicit user intent ('ingat/simpan/update memory') with source and dedupe checks.\n"
        "- Inferred memory must use paos_memory_candidate_create and ask approval first.\n"
        "- Do not apply controlled writes.\n"
        "- Do not mutate scheduler, GitHub, or repository state.\n"
        "- Do not enable/start Hermes gateway.\n"
        "- Gateway must remain stopped.\n"
        "- Mutation-like requests must be converted into draft output with clear no-apply notice.\n"
        "- Approval-required requests must include approval payload only, no execution path.\n"
        "- Blocked requests must refuse safely and must not include executable commands.\n"
        "- Action state transition is local persistence only (accepted != executed).\n"
        "- Agent handoff is planning context only (handoff != execution).\n"
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
        picks.append(("paos_operating_summary_get", {"category": "ai"}))

    if has_any("apa status paos hari ini", "operating summary", "daily operating summary"):
        picks.append(("paos_operating_summary_get", {"category": "ai"}))

    if has_any("daily plan", "buat daily plan", "context memory source"):
        picks.append(("paos_daily_plan_get", {"category": "ai"}))

    if has_any("dashboard", "dashboard paos"):
        picks.append(("paos_dashboard_get", {}))

    if has_any("hari ini fokus", "daily", "fokus hari ini"):
        picks.append(("paos_daily_get", {}))

    if has_any("handoff", "lanjut di codex", "lanjut di claude", "buat prompt codex", "buat prompt claude"):
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
    if has_any("apa yang kamu ingat", "memory relevan", "cara kerja saya", "ingat soal"):
        picks.append(("paos_memory_profile_get", {"limit": 8}))
    if has_any("memory sehat", "memory paos saya sehat"):
        picks.append(("paos_memory_health_get", {}))
    if has_any("memory baru", "perlu disimpan", "candidate memory"):
        picks.append(("paos_memory_candidate_list", {"status": "candidate", "limit": 5}))
    if has_any("buat action hari ini", "action pending", "accept yang tadi", "pilih nomor", "fokus saya sekarang"):
        picks.append(("paos_action_list", {"limit": 5}))
    if has_any("buat action hari ini", "daily action"):
        picks.append(("paos_daily_action_generate", {"category": "runtime", "persist": True}))

    if has_any(
        "source status",
        "status source",
        "intelligence status",
        "source intelligence sehat",
        "source intelligence saya sehat",
    ):
        picks.append(("paos_source_status_get", {}))
    if has_any("insight ai yang penting", "insight hari ini", "insight dari github", "insight dari threads"):
        picks.append(("paos_source_insight_get", {"category": "ai", "limit": 5}))
    if has_any("sinyal bagus", "candidate source", "candidate terbaru"):
        picks.append(("paos_source_candidates_get", {"category": "ai", "limit": 5}))
    if has_any("source paling berguna", "rekomendasi source", "keyword yang perlu saya ubah"):
        picks.append(("paos_source_recommendation_get", {"category": "ai"}))
    if has_any("buat action dari insight terbaru", "jadikan insight terbaru sebagai proposed action"):
        picks.append(("paos_source_action_draft_create", {"category": "ai"}))

    # "next apa" type benefits from status + dashboard grounding.
    if has_any("next buat paos", "next apa", "selanjutnya apa"):
        if ("paos_operating_summary_get", {"category": "ai"}) not in picks:
            picks.append(("paos_operating_summary_get", {"category": "ai"}))
        if ("paos_dashboard_get", {}) not in picks:
            picks.append(("paos_dashboard_get", {}))

    if has_any("review hasil codex", "review hasil claude", "hasil agent", "sudah sesuai"):
        picks.append(("paos_agent_result_review", {"content": normalized[:500]}))
    if has_any("buat handoff codex", "buat handoff claude", "buat handoff agent", "buat prompt cowork"):
        picks.append(("paos_agent_handoff_create", {"target_agent": "codex" if "codex" in normalized else ("claude_code" if "claude" in normalized else "claude_cowork" if "cowork" in normalized else "generic")}))
    if has_any("memory candidate dari hasil", "memory dari hasil agent"):
        picks.append(("paos_agent_memory_candidate_create", {"content": normalized[:400]}))

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
        "paos_operating_summary_get": getattr(mcp_server, "tool_paos_operating_summary_get", None),
        "paos_daily_plan_get": getattr(mcp_server, "tool_paos_daily_plan_get", None),
        "paos_dashboard_get": getattr(mcp_server, "tool_paos_dashboard_get", None),
        "paos_daily_get": getattr(mcp_server, "tool_paos_daily_get", None),
        "paos_handoff_get": getattr(mcp_server, "tool_paos_handoff_get", None),
        "paos_source_status_get": getattr(mcp_server, "tool_paos_source_status_get", None),
        "paos_source_digest_get": getattr(mcp_server, "tool_paos_source_digest_get", None),
        "paos_source_insight_get": getattr(mcp_server, "tool_paos_source_insight_get", None),
        "paos_source_candidates_get": getattr(mcp_server, "tool_paos_source_candidates_get", None),
        "paos_source_recommendation_get": getattr(mcp_server, "tool_paos_source_recommendation_get", None),
        "paos_source_action_draft_create": getattr(mcp_server, "tool_paos_source_action_draft_create", None),
        "paos_action_policy_get": getattr(mcp_server, "tool_paos_action_policy_get", None),
        "paos_action_draft_create": getattr(mcp_server, "tool_paos_action_draft_create", None),
        "paos_action_list": getattr(mcp_server, "tool_paos_action_list", None),
        "paos_daily_action_generate": getattr(mcp_server, "tool_paos_daily_action_generate", None),
        "paos_memory_profile_get": getattr(mcp_server, "tool_paos_memory_profile_get", None),
        "paos_memory_health_get": getattr(mcp_server, "tool_paos_memory_health_get", None),
        "paos_memory_candidate_list": getattr(mcp_server, "tool_paos_memory_candidate_list", None),
        "paos_agent_handoff_create": getattr(mcp_server, "tool_paos_agent_handoff_create", None),
        "paos_agent_handoff_get": getattr(mcp_server, "tool_paos_agent_handoff_get", None),
        "paos_agent_handoff_list": getattr(mcp_server, "tool_paos_agent_handoff_list", None),
        "paos_agent_result_review": getattr(mcp_server, "tool_paos_agent_result_review", None),
        "paos_agent_next_action_draft": getattr(mcp_server, "tool_paos_agent_next_action_draft", None),
        "paos_agent_memory_candidate_create": getattr(mcp_server, "tool_paos_agent_memory_candidate_create", None),
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
