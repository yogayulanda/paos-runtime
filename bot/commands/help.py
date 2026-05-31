async def handle_help(update):
    message = """
🤖 PAOS Runtime

Assistant OS:
/dashboard - PAOS home screen (fokus, state, opportunities, actions)
/daily - Daily action planner (priorities, defer, next action)
/context - Context health inspector (artifact status, freshness, warnings)
/memory - Read-only memory surface (progress, decisions, blockers, next)
/hermes - Hermes orchestration status (read-only observability)
/handoff - Generate handoff summary (use /handoff codex, /handoff claude, or /handoff hermes)
/promote-memory - Suggest durable memory promotions (no write)
/draft-context-update - Build controlled durable-context draft (no direct write)
/preview-context-update - Preview latest controlled write draft
/apply-context-update CONFIRM - Apply latest draft with explicit confirmation only
/draft - Draft-only action surface (/draft policy|next|daily|handoff codex|memory)

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
- /hermes = Hermes container/MCP/provider + orchestration toggle status
- /handoff = copy-paste handoff summary for next assistant
- /handoff codex = handoff tuned for Codex continuation
- /handoff claude = handoff tuned for Claude continuation
- /handoff hermes = handoff tuned for Hermes bridge consumer
- /promote-memory = suggest-only durable context promotion targets
- /draft-context-update = create draft artifact only (no durable file mutation)
- /preview-context-update = compact target/addition/risk preview from latest draft
- /apply-context-update CONFIRM = apply latest draft to allowlisted files only
- /draft = phase-4 bounded draft surface (no apply/mutation)
- /update = jalankan pipeline harian + tampilkan dashboard
- /insight = tampilkan dashboard insight terbaru
- /digest = tampilkan artifact digest terbaru
- /brief = tampilkan artifact assistant brief terbaru
- /opportunities = tampilkan artifact assistant opportunities terbaru
- /today = ringkasan fokus + top opportunities + next action
- /status = tampilkan status runtime/source/pipeline
- free-text = Hermes-first orchestration when enabled, fallback to rule-based router
- insight_relevance = personalized relevance summary from latest insight + assistant context
"""

    await update.message.reply_text(message)
