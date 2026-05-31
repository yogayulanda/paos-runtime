from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = ROOT / "logs" / "telegram-bot.log"
LOCK_PATH = Path("/tmp/paos-telegram-e2e.lock")


def _require_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"missing required env: {name}")
    return value


def _bot_processes() -> list[str]:
    cmd = "ps -ef | awk '/python -u? bot\\/telegram-bot.py/ && !/awk/ {print $0}'"
    out = subprocess.check_output(["bash", "-lc", cmd], text=True)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines


def _read_log_tail() -> str:
    if not LOG_PATH.exists():
        return ""
    text = LOG_PATH.read_text(encoding="utf-8", errors="ignore")
    return "\n".join(text.splitlines()[-400:])


def _send_telegram(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}, ensure_ascii=False)
    proc = subprocess.run(
        ["curl", "-sS", "-X", "POST", url, "-H", "content-type: application/json", "-d", payload],
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sendMessage failed: {proc.stderr.strip()}")
    data = json.loads(proc.stdout or "{}")
    if not data.get("ok"):
        raise RuntimeError(f"sendMessage error: {data}")
    return data


def _wait_trace(marker: str, timeout_sec: int = 30) -> bool:
    started = time.time()
    while time.time() - started < timeout_sec:
        tail = _read_log_tail()
        if marker in tail:
            return True
        time.sleep(1)
    return False


def main() -> int:
    if str(os.getenv("PAOS_E2E_LIVE_TELEGRAM") or "") != "1":
        print("e2e_telegram_live: SKIP (PAOS_E2E_LIVE_TELEGRAM!=1)")
        return 0

    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_E2E_CHAT_ID")

    if LOCK_PATH.exists():
        raise RuntimeError("live e2e lock exists: /tmp/paos-telegram-e2e.lock")
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")

    try:
        procs = _bot_processes()
        if len(procs) != 1:
            raise RuntimeError(f"expected exactly one live bot process, found={len(procs)}")

        checks: list[tuple[str, str]] = [
            ("buat action hari ini", "phase5_action_loop:create_daily"),
            ("apa action pending saya?", "phase5_action_loop:list_pending"),
            ("1", "phase5_action_loop:transition:ordinal_numeric"),
            ("apa fokus saya sekarang?", "phase5_action_loop:focus"),
            ("nyalakan Hermes gateway", "blocked_gateway_request"),
        ]

        for text, marker in checks:
            unique = f" [e2e-live:{int(time.time())}]"
            _send_telegram(token, chat_id, text + unique)
            if not _wait_trace(marker, timeout_sec=35):
                raise RuntimeError(f"trace marker not found for '{text}': {marker}")

        tail = _read_log_tail()
        if "No external action was applied." not in tail:
            print("e2e_telegram_live: WARN no explicit no-apply text in recent bot log tail")

        print("e2e_telegram_live: PASS")
        return 0
    finally:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
