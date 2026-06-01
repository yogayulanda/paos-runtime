from __future__ import annotations

import asyncio
import contextlib
import io
import os
import shutil
import sys
import tempfile
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


def _assert_no_internal_leak(response: str) -> None:
    lowered = response.lower()
    forbidden = ("paos_", "mcp", "tool_", "debug", "raw json")
    _assert(not any(x in lowered for x in forbidden), "internal leak detected")


def _assert_no_auto_menu(response: str) -> None:
    lowered = response.lower()
    forbidden = ("kamu bisa tanya", "coba contoh", "menu:", "contoh:", "/daily", "/dashboard")
    _assert(not any(x in lowered for x in forbidden), "automatic menu/examples detected")


def _assert_quality(response: str, require_confidence: bool = True) -> None:
    lowered = response.lower()
    _assert("kenapa" in lowered or "penting" in lowered or "impact" in lowered, "missing why/importance")
    _assert("next action" in lowered or "rekomendasi" in lowered or "keputusan" in lowered, "missing next action/decision")
    _assert("evidence" in lowered or "sumber" in lowered, "missing evidence")
    if require_confidence:
        _assert("confidence" in lowered, "missing confidence")


def _assert_state_boundary(response: str, should_have: bool) -> None:
    lowered = response.lower()
    has_boundary = "no external action was applied." in lowered
    if should_have:
        _assert(has_boundary, "missing no-external-action boundary")


async def _run() -> None:
    checks = [
        ("pagi", True, True),
        ("hari ini fokus apa?", True, True),
        ("apa yang menarik hari ini?", True, True),
        ("apa next terbaik sekarang?", True, True),
        ("buat daily plan", True, True),
        ("review action saya", True, True),
        ("context kerja saya sekarang", True, True),
        ("buat handoff Codex", False, True),
        ("review hasil Codex ini: patch done, smoke pass", True, True),
        ("simpan ini: saya mau jawaban singkat berbasis evidence", False, True),
    ]

    for idx, (msg, require_quality, expect_boundary) in enumerate(checks, start=1):
        response, _trace = await _ask(msg)
        _assert_no_internal_leak(response)
        _assert_no_auto_menu(response)
        _assert_state_boundary(response, expect_boundary)
        if require_quality:
            _assert_quality(response)
        print(f"[PRODUCT VALUE E2E {idx}] PASS")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="paos-product-value-e2e-"))
    try:
        os.environ["PAOS_ACTION_LOOP_DIR"] = str(tmp / "action-loop")
        os.environ["PAOS_AGENT_ORCH_DIR"] = str(tmp / "agent-orch")
        os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "false"
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
