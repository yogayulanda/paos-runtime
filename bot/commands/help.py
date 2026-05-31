async def handle_help(update):
    message = """
🤖 PAOS Runtime

Assistant OS:
/dashboard - PAOS home screen (fokus, state, opportunities, actions)
/daily - Daily action planner (priorities, defer, next action)
/context - Context health inspector (artifact status, freshness, warnings)

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
You can chat normally later for:
- save memory
- ask questions
- review context
- analyze topic
- plan next step

Command semantics:
- /dashboard = assistant OS home screen (combined view)
- /daily = compact daily action planner
- /context = context health and artifact freshness
- /update = jalankan pipeline harian + tampilkan dashboard
- /insight = tampilkan dashboard insight terbaru
- /digest = tampilkan artifact digest terbaru
- /brief = tampilkan artifact assistant brief terbaru
- /opportunities = tampilkan artifact assistant opportunities terbaru
- /today = ringkasan fokus + top opportunities + next action
- /status = tampilkan status runtime/source/pipeline
"""

    await update.message.reply_text(message)
