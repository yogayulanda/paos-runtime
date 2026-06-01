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
    create_resp, _ = await _ask("buat action hari ini")
    _assert("state: proposed" in create_resp.lower(), "daily action create failed")
    await _ask("apa action pending saya?")

    resp, trace = await _ask("1")
    where = (resp + "\n" + trace).lower()
    _assert("dibuat sebagai approval" in where and "no external action was applied." in where, "ordinal action should become approval")

    pending = mcp_server.tool_paos_approval_list(status="pending", limit=10)
    items = pending.get("items") or []
    _assert(bool(items), "pending approval expected")
    aid = str(items[0].get("approval_id") or "")
    _assert(bool(aid), "approval_id missing")

    dec = mcp_server.tool_paos_approval_decide(approval_id=aid, decision="approve", actor="e2e")
    _assert(dec.get("ok"), "approve failed")
    _assert((dec.get("approval") or {}).get("status") == "approved", "status must be approved")

    app = mcp_server.tool_paos_approval_apply(approval_id=aid, actor="e2e")
    _assert(app.get("ok"), "apply should pass for safe local action update")
    _assert((app.get("approval") or {}).get("status") == "applied", "status must be applied")

    rej = mcp_server.tool_paos_approval_propose(
        source="e2e",
        requested_by="e2e",
        proposed_operation="set action unknown -> rejected",
        operation_type="local_action_state_update",
        evidence_refs=["e2e"],
        payload_preview={"action_id": "missing_action", "transition": "rejected", "note": "e2e"},
    )
    rid = str((rej.get("approval") or {}).get("approval_id") or "")
    _assert(bool(rid), "proposal id missing")
    _assert(mcp_server.tool_paos_approval_decide(approval_id=rid, decision="approve", actor="e2e").get("ok"), "approve second failed")
    failed = mcp_server.tool_paos_approval_apply(approval_id=rid, actor="e2e")
    _assert(not failed.get("ok"), "apply should fail on missing action")
    _assert((failed.get("approval") or {}).get("status") == "failed", "failed apply should mark failed")

    blocked_resp, blocked_trace = await _ask("tolong commit dan push ke github")
    blocked_where = (blocked_resp + "\n" + blocked_trace).lower()
    _assert("diblokir" in blocked_where and "no external action was applied." in blocked_where, "unsafe request must be blocked")

    audits = mcp_server.tool_paos_approval_audit_list(limit=50)
    audit_items = audits.get("items") or []
    _assert(bool(audit_items), "audit items expected")
    rendered = "\n".join(str(x) for x in audit_items).lower()
    _assert("proposed" in rendered and "approved" in rendered and "applied" in rendered, "audit trail incomplete")

    normal_resp, normal_trace = await _ask("apa status PAOS hari ini?")
    normal_where = (normal_resp + "\n" + normal_trace).lower()
    _assert("route=hermes" in normal_where or "daily_ux_fallback_after_hermes" in normal_where, "normal free-text should stay hermes-first")
    _assert("contoh:" not in normal_resp.lower(), "default command menu should not be appended in normal answer")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="paos-controlled-exec-e2e-"))
    try:
        os.environ["PAOS_ACTION_LOOP_DIR"] = str(tmp / "action-loop")
        os.environ["PAOS_APPROVAL_DIR"] = str(tmp / "approval")
        os.environ["PAOS_HERMES_ORCHESTRATION_ENABLED"] = "false"
        asyncio.run(_run())
        print("e2e_controlled_execution_handler: PASS")
        return 0
    finally:
        os.environ.pop("PAOS_ACTION_LOOP_DIR", None)
        os.environ.pop("PAOS_APPROVAL_DIR", None)
        os.environ.pop("PAOS_HERMES_ORCHESTRATION_ENABLED", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
