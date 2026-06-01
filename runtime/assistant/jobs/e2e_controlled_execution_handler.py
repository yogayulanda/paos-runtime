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

    mem_resp, _ = await _ask("ingat ini: prefer saya ringkas dan evidence-first")
    mem_where = mem_resp.lower()
    _assert("candidate_id:" in mem_where and "approval_id:" in mem_where, "explicit memory should create candidate+approval")
    mem_pending = mcp_server.tool_paos_approval_list(status="pending", limit=20).get("items") or []
    mem_item = next((x for x in mem_pending if x.get("operation_type") == "memory_candidate_promotion"), None)
    _assert(mem_item is not None, "pending memory approval expected")
    mem_preview = mem_item.get("payload_preview") if isinstance(mem_item.get("payload_preview"), dict) else {}
    _assert(bool(mem_preview.get("candidate_id")), "memory approval must reference candidate_id")
    mem_id = str(mem_item.get("approval_id") or "")
    _assert(mcp_server.tool_paos_approval_decide(approval_id=mem_id, decision="approve", actor="e2e").get("ok"), "memory approve failed")
    mem_apply = mcp_server.tool_paos_approval_apply(approval_id=mem_id, actor="e2e")
    _assert(mem_apply.get("ok"), "memory apply failed")
    _assert((mem_apply.get("approval") or {}).get("status") == "applied", "memory approval not applied")

    inferred_resp, _ = await _ask("kayaknya perlu diingat: ini kandidat saja")
    _assert("memory candidate dibuat" in inferred_resp.lower(), "inferred memory should remain candidate-only")

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

    allowed_training_prompts = [
        "saya mau training github copilot besok pagi, kira-kira materinya tentang apa?",
        "materi belajar GitHub Copilot apa saja?",
        "jelaskan cara pakai GitHub Copilot",
    ]
    for prompt in allowed_training_prompts:
        allowed_resp, allowed_trace = await _ask(prompt)
        allowed_where = (allowed_resp + "\n" + allowed_trace).lower()
        _assert("blocked_unsafe_operation_request" not in allowed_where, f"training prompt must not hit unsafe block: {prompt}")
        _assert("route=hermes" in allowed_where or "hermes_fallback_after_empty_or_error" in allowed_where, f"training prompt should stay hermes-first: {prompt}")
        _assert("diblokir" not in allowed_where and "blocked by safety policy" not in allowed_where, f"training prompt was blocked: {prompt}")

    for prompt in (
        "tolong commit dan push ke github",
        "buat PR GitHub",
        "push commit ke GitHub",
        "update issue GitHub",
        "merge PR",
        "nyalakan Hermes gateway",
        "buat cron job",
    ):
        blocked_resp, blocked_trace = await _ask(prompt)
        blocked_where = (blocked_resp + "\n" + blocked_trace).lower()
        _assert((("diblokir" in blocked_where) or ("permintaan ditolak oleh policy" in blocked_where)) and "no external action was applied." in blocked_where, f"unsafe request must be blocked: {prompt}")
        if prompt != "nyalakan Hermes gateway":
            _assert("mode: future-disabled" in blocked_where or "mode: blocked" in blocked_where, f"blocked request should show disabled mode: {prompt}")


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
