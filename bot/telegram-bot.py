import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from services.config import TELEGRAM_BOT_TOKEN
from bot.commands.ops import handle_ops
from bot.commands.profile import handle_profile
from bot.commands.digest import handle_digest
from bot.commands.help import handle_help


TOKEN = TELEGRAM_BOT_TOKEN


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.startswith("/ops"):
        await handle_ops(update)
        return

    if text.startswith("/profile"):
        await handle_profile(update)
        return

    if text.startswith("/digest"):
        await handle_digest(update)
        return

    if text.startswith("/help"):
        await handle_help(update)
        return

    await update.message.reply_text(
        "PAOS received your message. Natural language routing is not enabled yet.\n\nUse /help for commands."
    )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(
    MessageHandler(filters.TEXT, handle_message)
)

print("PAOS Telegram bot running...")

app.run_polling()