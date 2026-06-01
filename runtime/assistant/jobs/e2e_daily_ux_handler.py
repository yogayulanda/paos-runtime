from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

from assistant.hermes.client import HermesQueryResult  # type: ignore
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
    return upd.message.sent[-1] if upd.message.sent else "", out.getvalue().strip()


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _assert_no_report_tone(response: str) -> None:
    lowered = response.lower()
    forbidden = (
        "root cause",
        "handler path",
        "validation result",
        "evidence field",
        "confidence label",
        "runtime path",
        "context priority",
        "identity grounding",
        "fallback path",
        "e2e",
        "no external action was applied.",
        "status utama",
        "confidence",
        "evidence ringkas",
        "draft aksi harian",
        "build opportunity",
        "regenerate brief",
        "saya belum kebaca jelas",
    )
    _assert(not any(token in lowered for token in forbidden), "report/program tone leaked")


def _assert_daily_answer_quality(response: str) -> None:
    lowered = response.lower()
    _assert(any(token in lowered for token in ("langkah", "fokus", "next", "lanjut", "prioritas")), "daily answer should contain a concrete direction")
    _assert(any(token in lowered for token in ("cek", "test", "validasi", "pilih", "rapikan", "pastikan")), "daily answer should contain a practical next step")
    _assert("review memory" not in lowered and "unresolved decision" not in lowered, "daily answer fell back to meta review")


async def _run() -> None:
    prompts = {
        "pagi": "Pagi. Dari konteks yang kebaca, kamu masih di PAOS Runtime. Yang belum jelas cuma fokus terbaru sesudah patch, jadi paling aman cek operating summary terbaru lalu pilih satu action kecil.",
        "apa next terbaik sekarang?": "Next terbaik sekarang: pastikan fokus terbarumu memang segar, lalu ambil satu langkah kecil yang bisa divalidasi cepat.",
        "terus sekarang saya ngapain?": "Sekarang lanjutkan dari fokus PAOS Runtime yang paling segar. Langkah pertama: cek satu validasi kecil, jangan pakai catatan setup lama sebagai patokan aksi.",
        "hari ini saya fokus ngapain?": "Fokus hari ini masih di stabilisasi PAOS Runtime. Langkah pertama: cek summary operasional terbaru, lalu pilih satu validasi kecil yang paling cepat menutup gap.",
        "hari fokus apa?": "Fokus yang paling masuk akal sekarang tetap sekitar PAOS Runtime. Mulai dari satu pengecekan kecil yang bisa langsung memastikan prioritas terbarunya.",
    }

    def _success(text: str, timeout_seconds: int = 45) -> HermesQueryResult:
        return HermesQueryResult(True, True, prompts[text], None, 0.01)

    with patch("bot.commands.assistant_query.hermes_orchestration_enabled", return_value=True), patch(
        "bot.commands.assistant_query.query_hermes", side_effect=_success
    ):
        for idx, (prompt, expected) in enumerate(prompts.items(), start=1):
            response, trace = await _ask(prompt)
            where = (response + "\n" + trace).lower()
            _assert(response == expected, f"daily prompt did not use Hermes response: {prompt}")
            _assert("route=hermes_orchestration" in where and "route=hermes_response_used" in where, f"missing Hermes traces: {prompt}")
            _assert("2026-05-28: paos v3 setup selesai" not in where, f"stale setup note leaked: {prompt}")
            _assert_no_report_tone(response)
            _assert_daily_answer_quality(response)
            print(f"[DAILY UX {idx}] PASS")

    def _failure(_text: str, timeout_seconds: int = 45) -> HermesQueryResult:
        return HermesQueryResult(False, False, "", "simulated error", 0.01)

    with patch("bot.commands.assistant_query.hermes_orchestration_enabled", return_value=True), patch(
        "bot.commands.assistant_query.query_hermes", side_effect=_failure
    ):
        response, trace = await _ask("apa next terbaik sekarang?")
        where = (response + "\n" + trace).lower()
        _assert(
            response == "Maaf, reasoning utama belum berhasil jawab barusan. Coba ulang sebentar lagi.",
            "unexpected retry-safe fallback",
        )
        _assert("route=hermes_fallback_after_empty_or_error" in where, "missing Hermes failure trace")


def main() -> int:
    os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "true"
    try:
        asyncio.run(_run())
        print("e2e_daily_ux_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)


if __name__ == "__main__":
    raise SystemExit(main())
