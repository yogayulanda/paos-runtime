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

from assistant.hermes.client import HermesQueryResult, _prefetch_read_evidence  # type: ignore
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


def _assert_no_bad_output(text: str) -> None:
    lowered = str(text or "").lower()
    forbidden = (
        "saya belum kebaca jelas",
        "coba tulis tujuanmu",
        "2026-05-28: paos v3 setup selesai",
        "tag inference strength",
        "daily action draft",
        "draft aksi harian",
        "build opportunity",
        "regenerate the brief",
        "status utama",
        "confidence",
        "evidence ringkas",
    )
    _assert(not any(token in lowered for token in forbidden), f"forbidden output leak: {text}")
    _assert("/home/ubuntu/paos/" not in text, f"file path leaked: {text}")


def _fake_response(prompt: str) -> str:
    mapping = {
        "pagi": "Pagi. Fokusmu masih di PAOS Runtime, tapi fokus terbaru sesudah patch belum benar-benar kebaca. Langkah paling aman: cek operating summary terbaru lalu pilih satu action kecil.",
        "apa next terbaik sekarang?": "Next terbaik sekarang: rapikan sumber context yang paling segar dulu, lalu pilih satu langkah kecil yang bisa divalidasi cepat.",
        "terus sekarang saya ngapain?": "Sekarang paling aman lanjut dari fokus PAOS Runtime yang paling segar. Langkah pertama: validasi satu next action kecil sebelum melebar.",
        "hari ini saya fokus ngapain?": "Fokus hari ini masih sekitar PAOS Runtime. Langkah pertama: cross-check summary yang paling baru, lalu pilih satu validasi kecil yang paling cepat.",
        "hari fokus apa?": "Fokus yang paling masuk akal saat ini tetap di stabilisasi PAOS Runtime. Mulai dari satu pengecekan kecil supaya prioritasnya langsung kebaca.",
        "sipa saya ?": "Kamu Yoga Yulanda, Tech Lead dan Senior Backend Engineer yang fokus di backend, distributed systems, dan fintech.",
        "siapa saya?": "Kamu Yoga Yulanda, Tech Lead dan Senior Backend Engineer yang fokus di backend, distributed systems, dan fintech.",
        "working style saya apa?": "Gaya kerja kamu cenderung rangkum dulu sebelum aksi, tanya seperlunya kalau ambigu, dan lebih suka keputusan yang berbasis bukti daripada jawaban cepat yang generik.",
        "saya lagi bangun apa?": "Kamu lagi bangun PAOS Runtime sebagai asisten operasional pribadi lewat Telegram, dengan Hermes sebagai reasoning layer dan context/memory untuk grounding.",
        "aman americano dicampur apa?": "Kalau mau aman, Americano biasanya paling enak dicampur sedikit susu dingin, madu, atau gula aren tipis sesuai selera.",
        "saya ada training pagi jam 8, enaknya bangun jam berapa?": "Kalau training jam 8 pagi, aman mulai bangun sekitar jam 6 atau 6.30 supaya masih ada waktu siap-siap tanpa buru-buru.",
    }
    return mapping[prompt]


async def _run() -> None:
    prompts = [
        "pagi",
        "apa next terbaik sekarang?",
        "terus sekarang saya ngapain?",
        "hari ini saya fokus ngapain?",
        "hari fokus apa?",
        "sipa saya ?",
        "siapa saya?",
        "working style saya apa?",
        "saya lagi bangun apa?",
        "aman americano dicampur apa?",
        "saya ada training pagi jam 8, enaknya bangun jam berapa?",
    ]
    paos_prompts = set(prompts[:-2])
    captured: dict[str, dict | None] = {}

    def _fake_query(text: str, timeout_seconds: int = 45) -> HermesQueryResult:
        captured[text] = _prefetch_read_evidence(text)
        return HermesQueryResult(True, True, _fake_response(text), None, 0.01)

    with patch("bot.commands.assistant_query.hermes_orchestration_enabled", return_value=True), patch(
        "bot.commands.assistant_query.query_hermes", side_effect=_fake_query
    ):
        for idx, prompt in enumerate(prompts, start=1):
            response, trace = await _ask(prompt)
            where = (response + "\n" + trace).lower()
            _assert(response == _fake_response(prompt), f"handler did not use Hermes response: {prompt}")
            _assert("route=hermes_orchestration" in where, f"missing Hermes route: {prompt}")
            _assert("route=hermes_response_used" in where, f"missing Hermes used route: {prompt}")
            _assert_no_bad_output(response)
            if prompt in {"pagi", "apa next terbaik sekarang?", "terus sekarang saya ngapain?", "hari ini saya fokus ngapain?", "hari fokus apa?"}:
                lowered = response.lower()
                _assert(any(token in lowered for token in ("langkah", "fokus", "next", "lanjut", "prioritas")), f"daily answer too abstract: {prompt}")
                _assert(any(token in lowered for token in ("cek", "test", "validasi", "pilih", "rapikan", "pastikan")), f"daily answer missing next step: {prompt}")
                _assert("review memory" not in lowered and "unresolved decision" not in lowered, f"daily answer fell back to meta review: {prompt}")
            if prompt in paos_prompts:
                evidence = captured.get(prompt) or {}
                pack = evidence.get("context_pack") or {}
                _assert(bool(evidence), f"missing evidence: {prompt}")
                _assert(bool(pack), f"missing context pack: {prompt}")
                _assert(bool(pack.get("source_refs")), f"missing source refs: {prompt}")
                _assert("2026-05-28" not in str(pack), f"stale raw note leaked into context pack: {prompt}")
                diagnostics = evidence.get("diagnostics") or {}
                if prompt in {"sipa saya ?", "siapa saya?"}:
                    identity = str(pack.get("identity_summary") or pack.get("user_profile_summary") or "").lower()
                    _assert("yoga" in identity, "identity summary missing Yoga")
                    _assert(bool(diagnostics.get("identity_summary_present")), "identity diagnostics missing")
                if prompt == "working style saya apa?":
                    style = str(pack.get("working_style_summary") or "").lower()
                    _assert("rangkum" in style or "bukti" in style, "working style not naturalized")
                    _assert("tag inference strength" not in style, "raw working style dump leaked")
                    _assert(bool(diagnostics.get("working_style_summary_present")), "working-style diagnostics missing")
                if prompt == "saya lagi bangun apa?":
                    build = str(pack.get("current_build_summary") or pack.get("current_state_summary") or "").lower()
                    _assert("paos runtime" in build, "build summary missing PAOS Runtime")
                    _assert(bool(diagnostics.get("current_build_summary_present")), "current-build diagnostics missing")
            else:
                _assert(not captured.get(prompt), f"casual prompt should not prefetch PAOS evidence: {prompt}")
            print(f"[CTX-UNIFY {idx}] PASS")

    def _failure(_text: str, timeout_seconds: int = 45) -> HermesQueryResult:
        return HermesQueryResult(False, False, "", "simulated error", 0.01)

    with patch("bot.commands.assistant_query.hermes_orchestration_enabled", return_value=True), patch(
        "bot.commands.assistant_query.query_hermes", side_effect=_failure
    ):
        response, trace = await _ask("pagi")
        where = (response + "\n" + trace).lower()
        _assert(
            response == "Maaf, reasoning utama belum berhasil jawab barusan. Coba ulang sebentar lagi.",
            "unexpected Hermes fallback",
        )
        _assert("route=hermes_fallback_after_empty_or_error" in where, "missing Hermes fallback trace")
        _assert_no_bad_output(response)


def main() -> int:
    os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "true"
    try:
        asyncio.run(_run())
        print("e2e_context_unification_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)


if __name__ == "__main__":
    raise SystemExit(main())
