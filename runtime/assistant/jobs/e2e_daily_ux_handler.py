from __future__ import annotations

import asyncio
import contextlib
import io
import os
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
    return (upd.message.sent[-1] if upd.message.sent else "", out.getvalue().strip())


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _assert_common_contract(response: str, trace: str) -> None:
    lowered = (response + "\n" + trace).lower()
    _assert("no external action was applied." in lowered, "missing no-external-action boundary")
    _assert("paos_" not in response.lower(), "internal tool leakage")
    _assert("tool_" not in response.lower(), "internal tool leakage")
    _assert("/" not in response[:20], "looks like slash-command style output")

def _assert_quality_contract(response: str) -> None:
    lowered = response.lower()
    _assert("kenapa ini penting" in lowered or "kenapa penting" in lowered, "missing why/importance block")
    _assert("next action" in lowered or "rekomendasi keputusan" in lowered or "next safe step" in lowered, "missing next-action/decision block")
    _assert("confidence" in lowered, "missing confidence block")
    _assert("evidence" in lowered, "missing evidence block")


async def _run() -> None:
    checks = [
        ("pagi, hari ini fokus apa?", ("status paos hari ini", "fokus", "next action")),
        ("apa status PAOS hari ini?", ("status paos hari ini", "fokus", "pending action")),
        ("buat daily plan", ("daily plan hari ini", "prioritas utama")),
        ("apa yang menarik hari ini?", ("yang menarik hari ini",)),
        ("apa next terbaik sekarang?", ("next terbaik sekarang", "rekomendasi")),
        ("review action saya", ("review action saat ini", "focus terpilih")),
        ("review minggu ini", ("review minggu ini", "kenapa ini penting")),
    ]

    for idx, (msg, required_tokens) in enumerate(checks, start=1):
        response, trace = await _ask(msg)
        where = (response + "\n" + trace).lower()
        _assert_common_contract(response, trace)
        _assert_quality_contract(response)
        _assert(
            "route=hermes_unavailable:orchestration_disabled" in where
            or "route=hermes_fallback_after_empty_or_error" in where,
            "expected deterministic daily-ux fallback trace",
        )
        for token in required_tokens:
            _assert(token in where, f"missing token '{token}' for '{msg}'")
        print(f"[DAILY UX E2E {idx}] PASS")


def main() -> int:
    os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "false"
    try:
        asyncio.run(_run())
        print("e2e_daily_ux_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)


if __name__ == "__main__":
    raise SystemExit(main())
