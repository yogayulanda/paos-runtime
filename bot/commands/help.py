def _help_message() -> str:
    return (
        "🤖 PAOS Runtime\n\n"
        "PAOS dirancang natural-language dulu. Cukup chat biasa.\n\n"
        "Contoh yang disarankan:\n"
        "1. apa fokus saya sekarang?\n"
        "2. buat action hari ini\n"
        "3. apa action pending saya?\n"
        "4. pilih nomor 1\n"
        "5. cek context saya sehat gak?\n"
        "6. dashboard PAOS saya gimana?\n"
        "7. buat handoff codex dari accepted action\n"
        "8. source intelligence sehat gak?\n\n"
        "Fallback/Admin (jika perlu):\n"
        "- /help\n"
        "- /hermes\n"
        "- /dashboard\n"
        "- /context\n"
        "- /actions\n\n"
        "Batas keamanan aktif: tidak ada external apply/write.\n"
        "No external action was applied."
    )


async def handle_help(update):
    await update.message.reply_text(_help_message())


async def handle_start(update):
    await update.message.reply_text(_help_message())
