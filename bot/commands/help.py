async def handle_help(update):
    message = """
🤖 PAOS Runtime

Main Commands:
/profile - Show personal context summary
/insight - Lihat dashboard harian PAOS
/update - Ambil data terbaru lalu tampilkan dashboard
/status - Status runtime/source/pipeline terbaru
/digest - Lihat digest AI terbaru
/ops - Show VPS/runtime status
/help - Show this help

Natural Language:
You can chat normally later for:
- save memory
- ask questions
- review context
- analyze topic
- plan next step

Command semantics:
- /update = jalankan pipeline harian + tampilkan dashboard
- /insight = tampilkan dashboard insight terbaru
- /digest = tampilkan artifact digest terbaru
- /status = tampilkan status runtime/source/pipeline
"""

    await update.message.reply_text(message)
