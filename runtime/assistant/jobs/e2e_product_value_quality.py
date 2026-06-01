from __future__ import annotations

import asyncio
import contextlib
import io
import os
import shutil
import sys
import tempfile
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


def _assert_no_internal_leak(response: str) -> None:
    lowered = response.lower()
    forbidden = ("paos_", "mcp", "tool_", "raw json", "evidence field", "runtime path")
    _assert(not any(x in lowered for x in forbidden), "internal leak detected")


async def _run() -> None:
    semantic_prompts = {
        "siapa saya?": "Kamu Yoga Yulanda, Technical Lead dan Senior Backend Engineer yang fokus di backend, distributed systems, dan financial systems.",
        "sipa saya?": "Kamu Yoga Yulanda, Technical Lead dan Senior Backend Engineer yang fokus di backend, distributed systems, dan financial systems.",
        "working style saya apa?": "Gaya kerja kamu cenderung rangkum dulu sebelum aksi, tanya seperlunya saat ambigu, dan lebih suka keputusan berbasis bukti daripada jawaban cepat yang generik.",
        "saya lagi bangun apa?": "Kamu lagi bangun PAOS Runtime sebagai asisten operasional pribadi lewat Telegram, dengan Hermes sebagai layer reasoning dan context/memory untuk grounding.",
        "saya mau training github copilot besok pagi, kira-kira materinya tentang apa?": "Kalau dibuat praktis, materi training GitHub Copilot besok bisa dibagi jadi dasar penggunaan, contoh workflow harian developer, prompt yang efektif, lalu best practice review hasil. Langkah pertama: susun agenda 3 blok supaya sesi paginya rapih.",
        "materi belajar GitHub Copilot apa saja?": "Materi belajar GitHub Copilot yang paling berguna biasanya: setup dan mode chat, cara memberi konteks repo, pola prompt untuk coding/testing/refactor, lalu cara ngecek hasilnya biar tidak asal terima.",
        "jelaskan cara pakai GitHub Copilot": "Cara pakai GitHub Copilot paling enak dimulai dari satu task kecil: kasih konteks file atau fungsi, minta draft solusi, lalu review dan koreksi hasilnya sebelum dipakai. Fokusnya jangan di autocomplete saja, tapi di alur kerja pairing dan verifikasi.",
        "aman americano dicampur apa?": "Kalau mau aman, coba sedikit susu dingin, madu, atau gula aren tipis. Kalau mau tetap clean, plain juga sudah enak.",
        "saya ada training pagi jam 8, enaknya bangun jam berapa?": "Kalau training jam 8 pagi, aman bangun sekitar jam 6 atau 6.30 supaya masih ada waktu siap tanpa buru-buru.",
    }

    def _semantic_success(text: str, timeout_seconds: int = 45) -> HermesQueryResult:
        return HermesQueryResult(True, True, semantic_prompts[text], None, 0.01)

    with patch("bot.commands.assistant_query.hermes_orchestration_enabled", return_value=True), patch(
        "bot.commands.assistant_query.query_hermes", side_effect=_semantic_success
    ):
        for idx, prompt in enumerate(semantic_prompts, start=1):
            response, trace = await _ask(prompt)
            where = (response + "\n" + trace).lower()
            _assert(response == semantic_prompts[prompt], f"semantic prompt did not use Hermes response: {prompt}")
            _assert("route=hermes_orchestration" in where and "route=hermes_response_used" in where, f"missing Hermes trace: {prompt}")
            _assert("tag inference strength" not in where, f"raw working-style dump leaked: {prompt}")
            _assert("2026-05-28: paos v3 setup selesai" not in where, f"stale setup note leaked: {prompt}")
            if prompt in {"siapa saya?", "sipa saya?"}:
                _assert("yoga" in response.lower(), "identity answer missing Yoga")
                _assert("belum punya identitas" not in response.lower(), "identity answer regressed to unknown")
            if prompt in {
                "saya mau training github copilot besok pagi, kira-kira materinya tentang apa?",
                "materi belajar GitHub Copilot apa saja?",
                "jelaskan cara pakai GitHub Copilot",
            }:
                lower_resp = response.lower()
                _assert("blocked by safety policy" not in lower_resp and "diblokir" not in lower_resp, "training/advice prompt must not be blocked")
                _assert("github copilot" in lower_resp or "copilot" in lower_resp, "training/advice answer missing topic grounding")
                _assert(any(token in lower_resp for token in ("materi", "workflow", "prompt", "best practice", "cara")), "training/advice answer not useful enough")
            if prompt in {"aman americano dicampur apa?", "saya ada training pagi jam 8, enaknya bangun jam berapa?"}:
                _assert("paos runtime" not in response.lower(), "casual answer should not inject PAOS")
            _assert_no_internal_leak(response)
            print(f"[PRODUCT VALUE {idx}] PASS")

    deterministic_checks = [
        ("buat handoff Codex", ("handoff dibuat", "no external action was applied.")),
        ("review hasil Codex ini: patch done, smoke pass", ("review hasil agent", "no external action was applied.")),
        ("simpan ini: saya mau jawaban singkat berbasis evidence", ("approval", "no external action was applied.")),
    ]
    for base_idx, (prompt, required) in enumerate(deterministic_checks, start=len(semantic_prompts) + 1):
        response, _trace = await _ask(prompt)
        lowered = response.lower()
        for token in required:
            _assert(token in lowered, f"missing deterministic token '{token}' for '{prompt}'")
        _assert_no_internal_leak(response)
        print(f"[PRODUCT VALUE {base_idx}] PASS")

    def _failure(_text: str, timeout_seconds: int = 45) -> HermesQueryResult:
        return HermesQueryResult(False, False, "", "simulated error", 0.01)

    with patch("bot.commands.assistant_query.hermes_orchestration_enabled", return_value=True), patch(
        "bot.commands.assistant_query.query_hermes", side_effect=_failure
    ):
        response, trace = await _ask("working style saya apa?")
        where = (response + "\n" + trace).lower()
        _assert(
            response == "Maaf, reasoning utama belum berhasil jawab barusan. Coba ulang sebentar lagi.",
            "unexpected technical fallback",
        )
        _assert("route=hermes_fallback_after_empty_or_error" in where, "missing Hermes failure trace")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="paos-product-value-e2e-"))
    try:
        os.environ["PAOS_ACTION_LOOP_DIR"] = str(tmp / "action-loop")
        os.environ["PAOS_AGENT_ORCH_DIR"] = str(tmp / "agent-orch")
        os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "true"
        asyncio.run(_run())
        print("e2e_product_value_quality: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_ACTION_LOOP_DIR", None)
        os.environ.pop("PAOS_AGENT_ORCH_DIR", None)
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
