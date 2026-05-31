async def handle_help(update):
    message = """
🤖 PAOS Runtime

Assistant OS:
/dashboard - PAOS home screen (fokus, state, opportunities, actions)
/daily - Daily action planner (priorities, defer, next action)
/context - Context health inspector (artifact status, freshness, warnings)
/memory - Read-only memory surface (progress, decisions, blockers, next)
/handoff - Generate handoff summary (use /handoff codex or /handoff claude)
/promote-memory - Suggest durable memory promotions (no write)

Intelligence:
/today - Ringkasan harian assistant + opportunities
/brief - Lihat assistant brief terbaru
/opportunities - Lihat assistant opportunities terbaru
/insight - Lihat dashboard harian PAOS (intelligence)
/digest - Lihat digest AI terbaru

Operations:
/update - Ambil data terbaru lalu tampilkan dashboard
/status - Status runtime/source/pipeline terbaru
/ops - Show VPS/runtime status
/profile - Show personal context summary
/help - Show this help

Natural Language:
MVP free-text query tersedia untuk intent umum:
- daily/dashboard
- insight relevance
- memory/handoff/context update
- context health/opportunities/status

Command semantics:
- /dashboard = assistant OS home screen (combined view)
- /daily = compact daily action planner
- /context = context health and artifact freshness
- /memory = read-only memory surface + fallback status
- /handoff = copy-paste handoff summary for next assistant
- /handoff codex = handoff tuned for Codex continuation
- /handoff claude = handoff tuned for Claude continuation
- /promote-memory = suggest-only durable context promotion targets
- /update = jalankan pipeline harian + tampilkan dashboard
- /insight = tampilkan dashboard insight terbaru
- /digest = tampilkan artifact digest terbaru
- /brief = tampilkan artifact assistant brief terbaru
- /opportunities = tampilkan artifact assistant opportunities terbaru
- /today = ringkasan fokus + top opportunities + next action
- /status = tampilkan status runtime/source/pipeline
- free-text = route intent read-only (rule-based, no LLM call)
- insight_relevance = personalized relevance summary from latest insight + assistant context
"""

    await update.message.reply_text(message)
