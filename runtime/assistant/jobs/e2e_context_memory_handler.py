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


async def _run() -> None:
    checks = [
        (
            "ingat ini: prefer saya adalah jawaban ringkas berbasis evidence",
            ("memory was written",),
            ("no external action was applied",),
        ),
        (
            "apa memory yang relevan untuk codex sekarang?",
            ("memory relevan",),
            (),
        ),
        (
            "kayaknya perlu diingat: saya sedang fokus stabilisasi runtime paos",
            ("memory candidate dibuat", "no external action was applied"),
            (),
        ),
        (
            "context kerja saya sekarang",
            ("working context saat ini", "focus:", "pending:", "no external action was applied"),
            (),
        ),
    ]

    for idx, (msg, must_have, must_not) in enumerate(checks, start=1):
        response, trace = await _ask(msg)
        where = (response + "\n" + trace).lower()
        for token in must_have:
            _assert(token in where, f"missing token '{token}' for '{msg}'")
        for token in must_not:
            _assert(token not in where, f"forbidden token '{token}' for '{msg}'")
        _assert("paos_" not in response.lower(), "internal tool leak")
        _assert("tool_" not in response.lower(), "internal tool leak")
        print(f"[CTX-MEM E2E {idx}] PASS")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="paos-context-memory-e2e-"))
    try:
        os.environ["PAOS_ACTION_LOOP_DIR"] = str(tmp / "action-loop")
        os.environ["PAOS_AGENT_ORCH_DIR"] = str(tmp / "agent-orch")
        os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "false"
        asyncio.run(_run())
        print("e2e_context_memory_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_ACTION_LOOP_DIR", None)
        os.environ.pop("PAOS_AGENT_ORCH_DIR", None)
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
