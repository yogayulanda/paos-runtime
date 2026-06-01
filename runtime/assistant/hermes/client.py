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
        "You are Hermes, the main reasoning orchestrator for PAOS Runtime Telegram free-text.\n"
        "PAOS Runtime is control-plane, Telegram gateway, and deterministic safety/local-state fallback only.\n"
        "Orchestration contract:\n"
        "1) First classify user intent semantically.\n"
        "2) Decide whether PAOS/personal context is relevant.\n"
        "3) If relevant, use PAOS read evidence/surfaces to ground answer.\n"
        "4) If not relevant, answer as normal AI assistant.\n"
        "5) If PAOS context is needed but incomplete, request/derive additional PAOS read context and explain naturally.\n"
        "6) Never expose MCP/internal tool names or tell user to call tools manually.\n"
        "7) Never end with 'no evidence attached in this turn' when PAOS read surfaces/evidence exist.\n"
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
        "UX rule for this channel:\n"
        "- In normal answers, respond directly to the user question only.\n"
        "- Do NOT append default PAOS menu/examples/command suggestions.\n"
        "- Do NOT add capability-advertising lines like 'kamu bisa tanya...' unless user explicitly asks for help.\n"
        "- Help/examples are allowed only for explicit help intent (e.g. '/help', 'bantuan', 'help me') or explicit greeting intent.\n"
        "- If this turn is not help/greeting, keep closing concise with no menu CTA.\n"
        "Treat PAOS evidence classes as read-only grounding sources:\n"
        "- daily/operating context\n"
        "- runtime/context health\n"
        "- current action/focus\n"
        "- source intelligence/opportunities\n"
        "- memory/profile/relevant personal context\n"
        "- agent handoff/review context\n"
        "Known roadmap priority:\n"
        "- Completed: provider activation, Telegram Hermes-first orchestration,\n"
        "  prompt/policy tuning, Phase 3 read surfaces, Phase 4 draft boundary,\n"
        "  and Phase 5 persistent action loop.\n"
        "- Current status: Phase 9 runtime-stable external agent orchestration active.\n"
        "- Main UX is conversational (e.g., 'pilih nomor 1', 'accept yang tadi').\n"
        "- Do not force slash commands for primary flow.\n"
        "- Do not recommend command-heavy flows as primary UX.\n"
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
    words = set(normalized.replace("?", " ").replace("!", " ").replace(",", " ").split())
    buckets: list[str] = []

    if not normalized:
        return []

    paosish_signal = any(x in normalized for x in ("paos", "fokus", "action", "aksi", "insight", "opportunity", "runtime", "context", "konteks", "memory", "handoff", "codex", "claude"))
    daily_signal = any(x in normalized for x in ("hari ini", "today", "menarik", "status", "ringkas", "overview"))

    if paosish_signal or daily_signal:
        buckets.append("daily_operating")

    if any(x in normalized for x in ("status paos", "runtime", "context sehat", "konteks sehat", "health")):
        buckets.append("runtime_health")
    if any(x in normalized for x in ("fokus", "action", "aksi", "pending", "nomor", "accept", "reject", "defer", "tunda", "tolak")):
        buckets.append("action_focus")
    if any(x in normalized for x in ("insight", "opportunity", "peluang", "source", "intel", "intelligence")):
        buckets.append("source_intelligence")
    if any(x in normalized for x in ("memory", "ingat", "profil", "preferensi", "cara kerja", "personal")):
        buckets.append("memory_profile")
    if any(x in normalized for x in ("review", "hasil", "handoff", "codex", "claude", "agent")):
        buckets.append("agent_review")

    if not buckets and any(x in words for x in ("apa", "bagaimana", "kenapa")) and ("hari" in words or "ini" in words):
        buckets.append("daily_operating")

    toolsets: dict[str, list[tuple[str, dict]]] = {
        "daily_operating": [
            ("paos_operating_summary_get", {"category": "ai"}),
            ("paos_daily_get", {}),
        ],
        "runtime_health": [
            ("paos_runtime_status_get", {}),
            ("paos_context_health_get", {}),
        ],
        "action_focus": [
            ("paos_action_list", {"limit": 5}),
            ("paos_daily_get", {}),
        ],
        "source_intelligence": [
            ("paos_source_status_get", {}),
            ("paos_source_insight_get", {"category": "ai", "limit": 5}),
            ("paos_source_recommendation_get", {"category": "ai"}),
        ],
        "memory_profile": [
            ("paos_memory_profile_get", {"limit": 8}),
            ("paos_memory_relevant_get", {"query": normalized[:120], "limit": 5}),
            ("paos_memory_health_get", {}),
        ],
        "agent_review": [
            ("paos_agent_handoff_list", {"limit": 5}),
            ("paos_action_list", {"limit": 5}),
        ],
    }

    picks: list[tuple[str, dict]] = []
    for bucket in buckets[:3]:
        for item in toolsets.get(bucket, []):
            if item not in picks:
                picks.append(item)

    return picks[:5]


def _prefetch_read_evidence(text: str) -> dict | None:
    requested = _detect_prefetch_tools(text)
    if not requested:
        return None
    payload: dict[str, object] = {"ok": True, "requested_tools": [], "errors": []}
    payload["evidence_mode"] = "semantic_buckets"
    payload["query"] = str(text or "")[:300]
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
