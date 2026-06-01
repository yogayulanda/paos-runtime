import json
import re
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

def _classify_prefetch_profile(text: str) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return "general"

    def _has_phrase(*phrases: str) -> bool:
        return any(phrase in normalized for phrase in phrases)

    if _has_phrase("siapa saya", "sipa saya", "siapa gw", "siapa aku", "profil saya") or re.search(r"\bs[iy]a?p?a\s+saya\b", normalized):
        return "identity"
    if _has_phrase("working style", "gaya kerja", "cara kerja saya", "working style saya"):
        return "working_style"
    if _has_phrase("bangun apa", "lagi bangun", "saya bangun apa", "project saya", "proyek saya", "build apa"):
        return "current_build"
    if normalized in {"pagi", "selamat pagi"} or _has_phrase(
        "next terbaik",
        "terus sekarang saya ngapain",
        "hari ini saya fokus ngapain",
        "hari fokus apa",
        "fokus hari ini apa",
        "hari ini fokus apa",
        "sekarang saya ngapain",
    ):
        return "daily_focus"
    if any(x in normalized for x in ("review", "hasil", "handoff", "codex", "claude", "agent")):
        return "agent_review"
    if any(x in normalized for x in ("memory", "ingat", "simpan ini", "update memory")):
        return "memory"
    if any(x in normalized for x in ("paos", "runtime", "konteks", "context", "fokus", "aksi", "action")):
        return "daily_focus"
    return "general"

def _compact_context_pack(context_pack: dict | None) -> dict:
    pack = context_pack or {}
    return {
        "identity_summary": str(pack.get("identity_summary") or pack.get("user_profile_summary") or "")[:320],
        "working_style_summary": str(pack.get("working_style_summary") or "")[:420],
        "current_state_summary": str(pack.get("current_state_summary") or "")[:320],
        "current_build_summary": str(pack.get("current_build_summary") or "")[:320],
        "current_focus_summary": str(pack.get("current_focus_summary") or "")[:240],
        "runtime_focus_summary": str(pack.get("runtime_focus_summary") or "")[:240],
        "background_summary": str(pack.get("background_summary") or "")[:260],
        "stale_or_background_warnings": [str(x)[:180] for x in (pack.get("stale_or_background_warnings") or pack.get("stale_warnings") or [])[:3]],
        "source_refs": [str(x)[:180] for x in (pack.get("source_refs") or [])[:3]],
        "current_focus_confidence": str(pack.get("current_focus_confidence") or "")[:24],
        "current_focus_candidates": [str(x)[:180] for x in (pack.get("current_focus_candidates") or [])[:3]],
    }

def _compact_tool_result(name: str, result: dict) -> dict:
    compact: dict[str, object] = {
        "tool": name,
        "ok": bool((result or {}).get("ok")),
        "status": (result or {}).get("status"),
        "summary": str((result or {}).get("summary") or "")[:220],
        "warnings": [str(x)[:140] for x in ((result or {}).get("warnings") or [])[:2]],
        "errors": [str(x)[:140] for x in ((result or {}).get("errors") or [])[:2]],
    }
    if name == "paos_operating_summary_get":
        sections = (result or {}).get("sections") or {}
        focus = (sections.get("focus") or {}) if isinstance(sections, dict) else {}
        compact["focus"] = {
            "current_focus": str(focus.get("current_focus") or "")[:180],
            "focus_state": str(focus.get("focus_state") or "")[:60],
            "recommended_next_safe_step": str((sections.get("recommended_next_safe_step") or ""))[:180],
        }
    elif name == "paos_daily_get":
        items = (result or {}).get("items") or {}
        compact["daily"] = {
            "priorities": [str(x)[:140] for x in (items.get("priorities") or [])[:3]],
            "next_action": str(items.get("next_action") or "")[:180],
        }
    elif name in {"paos_memory_profile_get", "paos_memory_relevant_get"}:
        compact["items"] = [
            {
                "type": str(item.get("type") or "")[:40],
                "content": str(item.get("content") or "")[:180],
            }
            for item in ((result or {}).get("items") or [])[:3]
            if isinstance(item, dict)
        ]
    return compact

def _compact_evidence_payload(evidence_payload: dict | None) -> dict:
    payload = evidence_payload or {}
    context_pack = _compact_context_pack(payload.get("context_pack") if isinstance(payload, dict) else {})
    diagnostics = payload.get("diagnostics") if isinstance(payload, dict) else {}
    return {
        "ok": bool(payload.get("ok")),
        "query": str(payload.get("query") or "")[:220],
        "prefetch_profile": str(payload.get("prefetch_profile") or "general"),
        "diagnostics": diagnostics if isinstance(diagnostics, dict) else {},
        "context_pack": context_pack,
        "requested_tools": [item for item in (payload.get("requested_tools") or [])[:4] if isinstance(item, dict)],
        "errors": [str(x)[:180] for x in (payload.get("errors") or [])[:3]],
    }


def _build_prompt_with_evidence(text: str, evidence_payload: dict | None) -> str:
    evidence_block = ""
    if evidence_payload:
        serialized = json.dumps(_compact_evidence_payload(evidence_payload), ensure_ascii=False, separators=(",", ":"))
        evidence_block = (
            "\nPAOS_READ_EVIDENCE (authoritative, read-only):\n"
            f"{serialized[:5200]}\n"
        )

    return (
        "You are Hermes, the main natural-language reasoner for PAOS Runtime Telegram free-text.\n"
        "PAOS Runtime is control-plane, Telegram gateway, and deterministic safety/local-state fallback only.\n"
        "Orchestration contract:\n"
        "1) First classify user intent semantically.\n"
        "2) Decide whether PAOS/personal context is relevant.\n"
        "3) If relevant, use PAOS read evidence/surfaces to ground answer. The runtime supplies context packs and evidence, not prewritten final answers.\n"
        "4) If not relevant, answer as normal AI assistant.\n"
        "5) If PAOS context is useful but incomplete, answer with the best current interpretation and mention uncertainty briefly only if needed.\n"
        "6) Never expose MCP/internal tool names or tell user to call tools manually.\n"
        "7) Never end with 'no evidence attached in this turn' when PAOS read surfaces/evidence exist.\n"
        "8) For identity, working-style, current-build, daily/focus/next, and casual questions, you own the final wording and tone.\n"
        "Session context:\n"
        "- MCP server `paos` is connected and tools are discoverable in this runtime.\n"
        "- Phase 3 MCP read surfaces are implemented and available.\n"
        "- Writes are forbidden in this Telegram free-text flow.\n"
        "- If PAOS_READ_EVIDENCE is provided, treat it as authoritative runtime evidence.\n"
        "- Do not claim tool/context surface unavailable when evidence is present.\n"
        "- If evidence contains warnings/errors, report them honestly and give one next action.\n"
        "- If identity_summary exists, do not say the user identity is unknown.\n"
        "- If working_style_summary exists, answer from it instead of inferring only from runtime behavior.\n"
        "- If current_build_summary exists, answer from it instead of old setup/history notes.\n"
        "Respond in natural Indonesian by default, concise, useful, and operationally grounded.\n"
        "Do not give generic product advice when PAOS state can be inspected.\n"
        "Do not claim tools are unavailable unless MCP/tool call actually fails in this run.\n"
        "If PAOS_READ_EVIDENCE contains `context_pack`, treat these fields as the compact grounding contract when relevant: identity_summary, working_style_summary, current_build_summary, current_focus_summary, background_summary, runtime_focus_summary, current_focus_confidence, current_focus_candidates, stale_or_background_warnings, and source_refs. Use them as evidence only; do not mirror raw field names or file paths back to the user unless explicitly asked.\n"
        "UX rule for this channel:\n"
        "- In normal answers, respond directly to the user question only.\n"
        "- Do NOT append default PAOS menu/examples/command suggestions.\n"
        "- Do NOT add capability-advertising lines like 'kamu bisa tanya...' unless user explicitly asks for help.\n"
        "- Help/examples are allowed only for explicit help intent (e.g. '/help', 'bantuan', 'help me') or explicit greeting intent.\n"
        "- If this turn is not help/greeting, keep closing concise with no menu CTA.\n"
        "- For daily/focus/next questions, answer like a practical personal assistant: give one concrete focus or recommendation, say briefly why it matters, then give the first step.\n"
        "- Prefer active current project/work context over generic memory review, unresolved-decision review, digest/build boilerplate, or stale setup notes.\n"
        "- Mention uncertainty only briefly when it materially affects the recommendation; if current_focus_confidence is low, still give a best-effort practical recommendation from the strongest current project context instead of asking the user to restate the goal.\n"
        "- Avoid rigid labels, report formatting, and internal/runtime jargon in normal Telegram answers.\n"
        "- For identity/working-style/current-build questions, answer from the context pack or read evidence instead of inventing profile content.\n"
        "- For casual/general questions, answer normally as an AI assistant and do not inject PAOS/internal framing unless genuinely relevant.\n"
        "- Do not over-template answers and do not sound like a program report.\n"
        "- Avoid terms like root cause, handler path, validation result, evidence field, confidence label, runtime path, fallback path, E2E, release blocker, context priority, or identity grounding unless the user explicitly asks for technical/debug details.\n"
        "Treat PAOS evidence classes as read-only grounding sources:\n"
        "- daily/operating context\n"
        "- runtime/context health\n"
        "- current action/focus\n"
        "- source intelligence/opportunities\n"
        "- memory/profile/relevant personal context\n"
        "- agent handoff/review context\n"
        "Known runtime priority:\n"
        "- Use the latest runtime evidence and personal-context source of truth as the priority signal.\n"
        "- Prefer fresh current-state/focus evidence over stale working-context placeholders.\n"
        "- Context unification must improve answer grounding, not replace it with rigid templates.\n"
        "- Main UX is conversational (e.g., 'pilih nomor 1', 'accept yang tadi').\n"
        "- Do not force slash commands for primary flow.\n"
        "- Do not recommend command-heavy flows as primary UX.\n"
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
        "- If execution is needed, propose steps instead of executing.\n"
        "Tone contract for Telegram:\n"
        "- Natural Indonesian, concise, warm but not bubbly, direct, and decisive.\n"
        "- Preferred style: short assistant-like prose using phrasing such as 'Yang paling masuk akal sekarang...', 'Langkah pertama...', 'Kalau dibuat praktis...', or 'Dari konteks yang kebaca...'.\n"
        "- Avoid stiff report wording and raw diagnostics such as 'Status utama', 'Confidence', 'Evidence ringkas', 'handler path', or exact file paths unless explicitly asked.\n"
        "If you genuinely have enough evidence, answer directly. If evidence is irrelevant, answer normally.\n\n"
        f"{evidence_block}"
        "User request:\n"
        f"{text.strip()}"
    )


def _detect_prefetch_tools(text: str) -> list[tuple[str, dict]]:
    normalized = str(text or "").strip().lower()
    words = set(normalized.replace("?", " ").replace("!", " ").replace(",", " ").split())

    if not normalized:
        return []
    profile = _classify_prefetch_profile(text)
    buckets_by_profile: dict[str, list[str]] = {
        "identity": ["memory_profile"],
        "working_style": ["memory_profile"],
        "current_build": ["daily_operating", "memory_profile"],
        "daily_focus": ["daily_operating", "action_focus", "memory_profile"],
        "agent_review": ["agent_review"],
        "memory": ["memory_profile"],
        "general": [],
    }
    buckets = list(buckets_by_profile.get(profile, []))

    if not buckets and any(x in normalized for x in ("status paos", "runtime", "context sehat", "konteks sehat", "health")):
        buckets.append("runtime_health")
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
            ("paos_memory_profile_get", {"limit": 6}),
            ("paos_memory_relevant_get", {"query": normalized[:120], "limit": 4}),
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
    profile = _classify_prefetch_profile(text)
    payload: dict[str, object] = {"ok": True, "requested_tools": [], "errors": []}
    payload["evidence_mode"] = "semantic_buckets"
    payload["prefetch_profile"] = profile
    payload["query"] = str(text or "")[:300]
    try:
        from assistant.mcp import server as mcp_server  # type: ignore
        from assistant.memory import build_personal_context_pack, load_memory_provider  # type: ignore
    except Exception as exc:
        payload["ok"] = False
        payload["errors"] = [f"prefetch import error: {exc}"]
        return payload

    try:
        payload["context_pack"] = build_personal_context_pack(str(text or ""), relevant_limit=4)
    except Exception as exc:
        errs = payload.get("errors")
        if not isinstance(errs, list):
            errs = []
            payload["errors"] = errs
        errs.append(f"context_pack: {exc}")

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
        "paos_working_context_get": getattr(mcp_server, "tool_paos_working_context_get", None),
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
            compact_results.append(_compact_tool_result(name, result or {}))
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    payload["requested_tools"] = compact_results
    payload["errors"] = errors
    payload["ok"] = len(errors) == 0
    context_pack = payload.get("context_pack") if isinstance(payload.get("context_pack"), dict) else {}
    selection = load_memory_provider()
    payload["diagnostics"] = {
        "identity_summary_present": bool((context_pack or {}).get("identity_summary") or (context_pack or {}).get("user_profile_summary")),
        "working_style_summary_present": bool((context_pack or {}).get("working_style_summary")),
        "current_build_summary_present": bool((context_pack or {}).get("current_build_summary")),
        "current_focus_confidence": str((context_pack or {}).get("current_focus_confidence") or ""),
        "active_memory_provider": selection.active_provider,
        "context_source_refs": [str(x)[:180] for x in ((context_pack or {}).get("source_refs") or [])[:3]],
        "attached_tool_names": [str(item.get("tool") or "") for item in compact_results if isinstance(item, dict)],
    }
    print(
        "[paos-evidence] "
        f"profile={profile} "
        f"identity={payload['diagnostics']['identity_summary_present']} "
        f"working_style={payload['diagnostics']['working_style_summary_present']} "
        f"current_build={payload['diagnostics']['current_build_summary_present']} "
        f"provider={payload['diagnostics']['active_memory_provider']} "
        f"tools={','.join(payload['diagnostics']['attached_tool_names'])}",
        flush=True,
    )
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
