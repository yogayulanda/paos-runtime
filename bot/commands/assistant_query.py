import sys
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT_DIR / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.query import route_intent  # type: ignore
from assistant.hermes import query_hermes  # type: ignore
from assistant.hermes import hermes_orchestration_enabled  # type: ignore
from assistant.hermes import hermes_timeout_seconds  # type: ignore
from assistant.action_loop import (  # type: ignore
    accept_action,
    create_daily_action,
    defer_action,
    list_actions as action_loop_list_actions,
    reject_action,
    render_action_detail,
    render_action_list,
    render_action_update_result,
    render_conversational_next_steps,
    resolve_action_reference,
)
from assistant.source_intelligence import (  # type: ignore
    create_action_from_latest_insight,
    get_source_insights,
    get_source_recommendation,
    get_source_status,
)
from bot.commands.assistant_surface import (
    _build_handoff_message,
    _build_memory_surface_message,
    _build_promotion_message,
    handle_context,
    handle_daily,
    handle_dashboard,
    handle_insight_relevance,
    handle_opportunities,
)
from bot.commands.intelligence import handle_status


def _trace_route(stage: str, text: str, route: str) -> None:
    compact = " ".join(str(text or "").split())[:180]
    print(f"[paos-route] stage={stage} route={route} text='{compact}'", flush=True)


def _resolve_handoff_target(text: str) -> str:
    lowered = text.lower()
    if "codex" in lowered:
        return "codex"
    if "claude" in lowered:
        return "claude"
    return "generic"


def _render_unknown_message() -> str:
    return (
        "Saya belum paham maksudnya.\n"
        "Coba contoh: 'hari ini saya harus ngapain', 'context saya sehat gak', "
        "'bikin handoff buat codex', atau 'ada opportunity apa hari ini'."
    )


def _normalize_text(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _is_action_loop_text(text: str) -> bool:
    lowered = _normalize_text(text)
    if lowered.isdigit():
        return True
    intent_patterns = (
        r"\bbuat action hari ini\b",
        r"\bapa action pending saya\b",
        r"\bapa fokus saya sekarang\b",
        r"\bpilih nomor \d+\b",
        r"\baccept yang tadi\b",
        r"\btunda yang tadi\b",
        r"\btolak yang scheduler\b",
        r"\bbuat handoff codex dari accepted action\b",
        r"\baccept\b",
        r"\breject\b",
        r"\bdefer\b",
    )
    if any(re.search(pattern, lowered) for pattern in intent_patterns):
        return True
    lowered = str(text or "").lower()
    keys = (
        "action", "pending", "accept", "reject", "defer", "tunda", "tolak",
        "nomor", "yang tadi", "fokus", "handoff codex", "buat action hari ini",
    )
    return any(k in lowered for k in keys)


def _is_forbidden_gateway_request(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(
        phrase in lowered
        for phrase in (
            "nyalakan hermes gateway",
            "enable hermes gateway",
            "start hermes gateway",
            "hidupkan hermes gateway",
        )
    )


async def _handle_action_loop(update, text: str) -> bool:
    lowered = _normalize_text(text)
    if lowered.isdigit():
        _trace_route("action-loop", text, "phase5_action_loop:transition:ordinal_numeric")
        action = resolve_action_reference(reference=f"nomor {lowered}", ordinal=int(lowered))
        if not action:
            await update.message.reply_text("Referensi belum jelas. Maksud Anda nomor berapa dari daftar terakhir?")
            return True
        result = accept_action(action.action_id, actor="telegram", note=f"ordinal {lowered}")
        if result.ok and result.action:
            await update.message.reply_text(
                (
                    f"Action '{result.action.title}' berubah: {action.state} -> {result.action.state}.\n"
                    "Accepted berarti arah/fokus dipilih, bukan dieksekusi.\n"
                    "No external action was applied."
                )[:3900]
            )
        else:
            await update.message.reply_text(render_action_update_result(result))
        return True
    if "buat action hari ini" in lowered or ("daily action" in lowered and "buat" in lowered):
        _trace_route("action-loop", text, "phase5_action_loop:create_daily")
        result = create_daily_action(category="runtime", persist=True, actor="telegram")
        if not result.ok or not result.action:
            await update.message.reply_text("Gagal membuat action harian. No external action was applied.")
            return True
        message = (
            "Action harian dibuat.\n"
            f"1. {result.action.title}\n"
            f"   id: {result.action.action_id}\n"
            f"   state: {result.action.state}\n"
            "Balas natural: accept / reject / defer / lihat detail / pilih nomor 1.\n"
            "No external action was applied."
        )
        await update.message.reply_text(message[:3900])
        return True

    if "pending" in lowered or "action saya" in lowered or "list action" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:list_pending")
        actions = action_loop_list_actions(limit=30, remember_list=False)
        pending = [
            a for a in actions
            if a.state in {"proposed", "deferred"} and not str(a.source).lower().startswith("e2e")
        ][:5]
        try:
            from assistant.action_loop.store import load_index, save_index  # type: ignore

            idx = load_index()
            idx["latest_listed_action_ids"] = [a.action_id for a in pending]
            save_index(idx)
        except Exception:
            pass
        if not pending:
            await update.message.reply_text("Pending Actions kosong. No external action was applied.")
            return True
        await update.message.reply_text(render_action_list(pending, title="Pending Actions"))
        return True

    if "apa yang harus saya kerjakan sekarang" in lowered or "apa fokus saya sekarang" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:focus")
        accepted = action_loop_list_actions(state="accepted", limit=1, remember_list=False)
        if accepted:
            await update.message.reply_text(render_conversational_next_steps(accepted[0]))
            return True
        proposed = action_loop_list_actions(state="proposed", limit=1, remember_list=False)
        if proposed:
            top = proposed[0]
            await update.message.reply_text(
                (
                    f"Belum ada accepted action.\n"
                    f"Usulan teratas: 1. {top.title} ({top.action_id}) [proposed]\n"
                    "Balas natural: pilih nomor 1 / tunda yang tadi / tolak yang tadi.\n"
                    "No external action was applied."
                )[:3900]
            )
            return True
        await update.message.reply_text(render_conversational_next_steps(None))
        return True

    if "lihat detail" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:detail")
        action = resolve_action_reference(reference=lowered)
        if not action:
            await update.message.reply_text("Saya belum bisa resolve referensinya. Sebut 'nomor 1' dari list terbaru.")
            return True
        await update.message.reply_text(render_action_detail(action))
        return True

    if "handoff codex" in lowered and "accepted" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:handoff_codex")
        accepted = action_loop_list_actions(state="accepted", limit=1, remember_list=False)
        if not accepted:
            await update.message.reply_text("Belum ada accepted action. No external action was applied.")
            return True
        action = accepted[0]
        handoff = (
            "Codex Handoff Draft\n"
            f"Action: {action.title}\n"
            f"Summary: {action.summary}\n"
            "Steps:\n" + "\n".join([f"{i}. {s}" for i, s in enumerate(action.steps[:5], start=1)]) +
            "\nNo external action was applied."
        )
        await update.message.reply_text(handoff[:3900])
        return True

    for trigger, fn in (("accept", accept_action), ("jadikan", accept_action), ("pilih", accept_action), ("reject", reject_action), ("tolak", reject_action), ("defer", defer_action), ("tunda", defer_action)):
        if trigger in lowered:
            _trace_route("action-loop", text, f"phase5_action_loop:transition:{trigger}")
            ordinal_match = re.search(r"nomor\s+(\d+)", lowered)
            ordinal = int(ordinal_match.group(1)) if ordinal_match else None
            action = resolve_action_reference(reference=lowered, ordinal=ordinal)
            if not action:
                await update.message.reply_text("Referensi belum jelas. Maksud Anda nomor berapa dari daftar terakhir?")
                return True
            result = fn(action.action_id, actor="telegram", note=lowered)
            if result.ok and result.action:
                previous_state = action.state
                await update.message.reply_text(
                    (
                        f"Action '{result.action.title}' berubah: {previous_state} -> {result.action.state}.\n"
                        "Accepted berarti arah/fokus dipilih, bukan dieksekusi.\n"
                        "No external action was applied."
                    )[:3900]
                )
            else:
                await update.message.reply_text(render_action_update_result(result))
            return True
    return False


async def _handle_source_intelligence(update, text: str) -> bool:
    lowered = _normalize_text(text)
    if any(k in lowered for k in ("source intelligence saya sehat", "source intelligence sehat", "status source", "source status")):
        _trace_route("source-intel", text, "phase6_source_status")
        payload = get_source_status(category="ai").payload
        await update.message.reply_text(
            (
                f"{payload.get('summary')}\n"
                f"Rekomendasi: {payload.get('recommended_next_maintenance_action')}\n"
                "No external action was applied."
            )[:3900]
        )
        return True
    if any(k in lowered for k in ("insight ai yang penting", "insight hari ini", "insight dari github", "insight dari threads")):
        _trace_route("source-intel", text, "phase6_source_insight")
        payload = get_source_insights(category="ai", limit=3)
        items = payload.get("items") or []
        if not items:
            await update.message.reply_text("Belum ada insight terbaru. Coba jalankan pipeline intelligence dulu.")
            return True
        lines = []
        for i, item in enumerate(items[:3], start=1):
            lines.append(f"{i}. {item.get('title', '-')}")
            lines.append(f"   alasan: {str(item.get('reason') or '-')[:180]}")
            lines.append(f"   source: {item.get('source_ref') or item.get('source_refs') or '-'}")
        await update.message.reply_text(("\n".join(lines))[:3900])
        return True
    if any(k in lowered for k in ("source paling berguna", "rekomendasi source", "keyword yang perlu saya ubah")):
        _trace_route("source-intel", text, "phase6_source_recommendation")
        payload = get_source_recommendation(category="ai")
        msg = "Rekomendasi source/keyword:\n" + "\n".join(f"- {x}" for x in (payload.get("items") or [])[:5])
        await update.message.reply_text(msg[:3900])
        return True
    if any(k in lowered for k in ("buat action dari insight terbaru", "source intelligence terbaru", "jadikan insight terbaru sebagai proposed action")):
        _trace_route("source-intel", text, "phase6_source_action_from_insight")
        payload = create_action_from_latest_insight(category="ai")
        if not payload.get("ok"):
            await update.message.reply_text("Gagal membuat proposed action dari insight terbaru.")
            return True
        action = (payload.get("action") or {})
        await update.message.reply_text(
            (
                "Proposed action dibuat dari insight terbaru.\n"
                f"- title: {action.get('title')}\n"
                f"- state: {action.get('state')}\n"
                "No external action was applied."
            )[:3900]
        )
        return True
    return False


async def handle_free_text_query(update, context):
    text = str(update.message.text or "").strip()
    if _is_forbidden_gateway_request(text):
        _trace_route("free-text", text, "blocked_gateway_request")
        await update.message.reply_text(
            "Permintaan ditolak oleh policy: Hermes gateway tidak boleh dinyalakan dari Telegram. "
            "No external action was applied."
        )
        return
    if _is_action_loop_text(text):
        _trace_route("free-text", text, "phase5_action_loop:intent_match")
        if await _handle_action_loop(update, text):
            return
    if await _handle_source_intelligence(update, text):
        return
    if hermes_orchestration_enabled():
        _trace_route("free-text", text, "hermes_orchestration")
        hermes_result = query_hermes(text, timeout_seconds=hermes_timeout_seconds())
        if hermes_result.used and hermes_result.response_text.strip():
            _trace_route("free-text", text, "hermes_response_used")
            await update.message.reply_text(hermes_result.response_text.strip())
            return

    intent = route_intent(text)
    _trace_route("free-text", text, f"deterministic_fallback:{intent}")

    if intent == "daily":
        await handle_daily(update)
        return
    if intent == "dashboard":
        await handle_dashboard(update)
        return
    if intent == "memory":
        await update.message.reply_text(_build_memory_surface_message())
        return
    if intent == "handoff":
        await update.message.reply_text(_build_handoff_message(_resolve_handoff_target(text)))
        return
    if intent == "context_update":
        await update.message.reply_text(_build_promotion_message())
        return
    if intent == "context_health":
        await handle_context(update)
        return
    if intent == "opportunities":
        await handle_opportunities(update)
        return
    if intent == "insight_relevance":
        await handle_insight_relevance(update)
        return
    if intent == "status":
        await handle_status(update)
        return

    await update.message.reply_text(_render_unknown_message())
