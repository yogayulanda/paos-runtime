from __future__ import annotations

import asyncio
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from bot.commands.assistant_query import handle_free_text_query  # type: ignore


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.sent: list[str] = []

    async def reply_text(self, body: str):
        self.sent.append(str(body))


class _Update:
    def __init__(self, text: str):
        self.message = _Msg(text)


async def _ask(text: str) -> tuple[str, str]:
    upd = _Update(text)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        await handle_free_text_query(upd, None)
    route_trace = out.getvalue().strip()
    response = upd.message.sent[-1] if upd.message.sent else ""
    return response, route_trace


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


async def _run() -> None:
    checks: list[tuple[str, list[str]]] = [
        ("ingat ini: PAOS command harus fallback saja", ["approval", "No external action was applied."]),
        ("apa yang kamu ingat soal PAOS command?", ["Memory relevan", "PAOS command"]),
        ("update memory tentang PAOS command: natural language adalah UX utama", ["approval", "No external action was applied."]),
        ("ada memory baru yang perlu disimpan?", ["Balas natural|No memory was written yet"]),
        ("tolak memory itu", ["No memory was written yet"]),
        ("memory PAOS saya sehat gak?", ["provider=", "No memory was written yet"]),
        ("apa memory yang relevan untuk Codex sekarang?", ["Memory relevan"]),
    ]

    for idx, (user_msg, must_have) in enumerate(checks, start=1):
        bot_response, route_trace = await _ask(user_msg)
        print(f"[MEM E2E {idx}] User: {user_msg}")
        print(f"[MEM E2E {idx}] Route: {route_trace or 'n/a'}")
        print(f"[MEM E2E {idx}] Bot:\n{bot_response}")
        where = (bot_response + "\n" + route_trace).lower()
        for token in must_have:
            choices = [part.strip().lower() for part in token.split("|") if part.strip()]
            _assert(any(choice in where for choice in choices), f"missing token '{token}' for prompt '{user_msg}'")
        print("-" * 80)


def main() -> int:
    asyncio.run(_run())
    print("e2e_memory_handler: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
