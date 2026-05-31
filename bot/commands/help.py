async def handle_help(update):
    message = """
🤖 PAOS Runtime

Main Commands:
/profile - Show personal context summary
/insight - Lihat dashboard harian
/update - Ambil data terbaru lalu tampilkan dashboard
/status - Cek apakah pipeline terakhir sukses
/digest - Legacy digest command
/ops - Show VPS/runtime status
/help - Show this help

Natural Language:
You can chat normally later for:
- save memory
- ask questions
- review context
- analyze topic
- plan next step

Legacy commands may still exist during migration.
"""

    await update.message.reply_text(message)
