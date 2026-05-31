import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT_DIR / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.query import route_intent  # type: ignore
from assistant.hermes import query_hermes  # type: ignore
from assistant.hermes import hermes_orchestration_enabled  # type: ignore
from assistant.hermes import hermes_timeout_seconds  # type: ignore
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


async def handle_free_text_query(update, context):
    text = str(update.message.text or "").strip()
    if hermes_orchestration_enabled():
        hermes_result = query_hermes(text, timeout_seconds=hermes_timeout_seconds())
        if hermes_result.used and hermes_result.response_text.strip():
            await update.message.reply_text(hermes_result.response_text.strip())
            return

    intent = route_intent(text)

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
