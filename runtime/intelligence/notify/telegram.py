import os
import sys
from pathlib import Path

import requests


TELEGRAM_MESSAGE_LIMIT = 4000
TELEGRAM_SAFE_LIMIT = 3900
ROOT = Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context.loader import load_env


def split_telegram_message(text: str, limit: int = TELEGRAM_SAFE_LIMIT) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= limit:
        return [normalized]

    chunks = []
    current = ""

    for line in normalized.splitlines():
        line = line.rstrip() or ""
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
            current = ""
        while len(line) > limit:
            chunks.append(line[:limit].strip())
            line = line[limit:]
        current = line

    if current:
        chunks.append(current.strip())

    return [chunk for chunk in chunks if chunk]


def telegram_credentials() -> tuple[str, str]:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if bot_token and chat_id:
        return bot_token, chat_id

    try:
        env = load_env(str(ROOT / ".env"))
    except Exception:
        env = {}

    bot_token = bot_token or str(env.get("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = chat_id or str(env.get("TELEGRAM_CHAT_ID", "")).strip()
    return bot_token, chat_id


def send_telegram_message(text: str) -> bool:
    bot_token, chat_id = telegram_credentials()

    if not bot_token or not chat_id:
        print("Telegram notification skipped: missing env")
        return False

    try:
        chunks = split_telegram_message(text, limit=TELEGRAM_SAFE_LIMIT)
        if not chunks:
            return False
        for chunk in chunks:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": chunk[:TELEGRAM_MESSAGE_LIMIT],
                },
                timeout=15,
            )
            response.raise_for_status()
        return True
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")
        return False
