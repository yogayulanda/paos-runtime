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


def _assert_no_unknown_fallback(where: str) -> None:
    _assert("saya belum paham" not in where, "unexpected unknown fallback")


def _assert_no_internal_tool_leak(text: str) -> None:
    leaks = ("paos_", "tool_", "call `", "panggil tool")
    lowered = str(text or "").lower()
    _assert(not any(x in lowered for x in leaks), "internal tool leakage detected")


def _assert_safe_no_external(where: str) -> None:
    _assert(
        "no external action was applied." in where or "tidak ada commit/push" in where,
        "missing safety/no-external-action semantics",
    )

def _assert_review_safe_semantics(text: str) -> None:
    lowered = str(text or "").lower()
    safe_markers = (
        "no external action was applied",
        "tidak dieksekusi",
        "belum dieksekusi",
        "tidak ada aksi eksternal",
        "review only",
        "draft/manual",
        "manual next step",
        "no mutation",
        "no apply",
        "tidak melakukan commit/push",
        "hanya rekomendasi",
        "hanya review",
    )
    _assert(any(x in lowered for x in safe_markers), "missing safety/no-external-action semantics")

def _assert_no_unsafe_execution_implication(text: str) -> None:
    lowered = str(text or "").lower()
    forbidden = (
        "external action applied",
        "sudah dieksekusi",
        "telah dieksekusi",
        "berhasil dieksekusi",
        "sudah commit",
        "sudah push",
        "sudah merge",
        "created pr",
        "pull request dibuat",
        "issue dibuat",
        "gateway berjalan sekarang",
        "hermes gateway dinyalakan",
        "scheduler diubah",
        "systemctl diaktifkan",
        "jadwal cron diubah",
    )
    _assert(not any(x in lowered for x in forbidden), "unsafe execution implication detected")


def _assert_handoff_contract(response: str, trace: str) -> None:
    where = (response + "\n" + trace).lower()
    _assert_no_unknown_fallback(where)
    _assert_no_internal_tool_leak(response)
    _assert_safe_no_external(where)
    _assert_no_unsafe_execution_implication(response)
    _assert(any(x in where for x in ("handoff", "prompt", "draft")), "handoff/prompt/draft signal missing")
    _assert("codex" in where, "codex target signal missing")
    _assert(
        ("stage=free-text" in where and "route=hermes_orchestration" in where)
        or "route=phase9_agent_orchestration" in where,
        "expected Hermes-first or phase9 route trace",
    )


def _assert_agent_review_contract(response: str, trace: str) -> None:
    where = (response + "\n" + trace).lower()
    _assert_no_unknown_fallback(where)
    _assert_no_internal_tool_leak(response)
    _assert_review_safe_semantics(response)
    _assert_no_unsafe_execution_implication(response)
    _assert(any(x in where for x in ("review", "commit_readiness", "next_safe_step", "goal_met")), "review signal missing")


def _assert_next_action_contract(response: str, trace: str) -> None:
    where = (response + "\n" + trace).lower()
    _assert_no_unknown_fallback(where)
    _assert_no_internal_tool_leak(response)
    _assert_safe_no_external(where)
    _assert_no_unsafe_execution_implication(response)
    _assert(any(x in where for x in ("next action", "next step", "draft")), "next-action signal missing")


def _assert_memory_candidate_contract(response: str, trace: str) -> None:
    where = (response + "\n" + trace).lower()
    _assert_no_unknown_fallback(where)
    _assert_no_internal_tool_leak(response)
    _assert_safe_no_external(where)
    _assert(any(x in where for x in ("memory candidate", "candidate memory", "memory")), "memory-candidate signal missing")


async def _run() -> None:
    # Hermes-first architecture note:
    # - Do not lock to deterministic-era exact wording.
    # - Validate UX contract and safety boundaries while allowing output variance.
    checks = [
        ("buat handoff Codex dari fokus sekarang", _assert_handoff_contract),
        ("review hasil agent ini: implementasi oke, smoke pass, tidak ada blocker", _assert_agent_review_contract),
        ("apa next step setelah hasil agent ini?", _assert_next_action_contract),
    ]

    for idx, (msg, checker) in enumerate(checks, start=1):
        response, trace = await _ask(msg)
        checker(response, trace)
        print(f"[AGENT E2E {idx}] PASS")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="paos-agent-e2e-"))
    try:
        os.environ["PAOS_ACTION_LOOP_DIR"] = str(tmp / "action-loop")
        os.environ["PAOS_AGENT_ORCH_DIR"] = str(tmp / "agent-orch")
        os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "true"
        asyncio.run(_run())
        print("e2e_agent_orchestration_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_ACTION_LOOP_DIR", None)
        os.environ.pop("PAOS_AGENT_ORCH_DIR", None)
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
