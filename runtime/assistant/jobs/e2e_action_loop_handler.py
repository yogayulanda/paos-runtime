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
from assistant.mcp import server as mcp_server  # type: ignore


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.sent: list[str] = []

    async def reply_text(self, body: str):
        self.sent.append(str(body))


class _Update:
    def __init__(self, text: str):
        self.message = _Msg(text)


async def _ask(text: str) -> str:
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
    checks: list[tuple[str, list[str], list[str]]] = [
        (
            "buat action hari ini",
            ["state: proposed", "No external action was applied.", "phase5_action_loop:create_daily"],
            [],
        ),
        (
            "apa action pending saya?",
            ["Pending Actions", "phase5_action_loop:list_pending"],
            ["paos_daily_get", "slash"],
        ),
        (
            "1",
            ["dibuat sebagai approval", "No external action was applied.", "phase5_action_loop:transition:ordinal_numeric"],
            [],
        ),
        (
            "nyalakan Hermes gateway",
            ["ditolak", "No external action was applied.", "blocked_gateway_request"],
            [],
        ),
    ]

    for idx, (user_msg, must_have, must_not_have) in enumerate(checks, start=1):
        bot_response, route_trace = await _ask(user_msg)
        print(f"[E2E {idx}] User: {user_msg}")
        print(f"[E2E {idx}] Detected Route: {route_trace or 'n/a'}")
        print(f"[E2E {idx}] Bot Response:\n{bot_response}")
        assertions: list[str] = []
        for token in must_have:
            where = (bot_response + "\n" + route_trace).lower()
            token_options = [x.strip().lower() for x in token.split("||") if x.strip()]
            ok = any(opt in where for opt in token_options)
            assertions.append(f"{'PASS' if ok else 'FAIL'} contains '{token}'")
            _assert(ok, f"missing token: {token}")
        for token in must_not_have:
            where = bot_response.lower()
            ok = token.lower() not in where
            assertions.append(f"{'PASS' if ok else 'FAIL'} not contains '{token}'")
            _assert(ok, f"forbidden token present: {token}")
        print(f"[E2E {idx}] Assertion Summary: {'; '.join(assertions)}")
        print("-" * 80)

    latest_pending_approval = mcp_server.tool_paos_approval_list(status="pending", limit=1)
    _assert(bool(latest_pending_approval.get("items") or []), "pending approval should exist after ordinal select")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="paos-action-loop-e2e-handler-"))
    try:
        os.environ["PAOS_ACTION_LOOP_DIR"] = str(tmp)
        asyncio.run(_run())
        print("e2e_action_loop_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_ACTION_LOOP_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
