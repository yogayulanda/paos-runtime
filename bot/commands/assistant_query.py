import sys
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT_DIR / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.hermes import query_hermes  # type: ignore
from assistant.hermes import hermes_orchestration_enabled  # type: ignore
from assistant.hermes import hermes_timeout_seconds  # type: ignore
from assistant.action_loop import (  # type: ignore
    accept_action,
    create_daily_action,
    defer_action,
    list_actions as action_loop_list_actions,
    reject_action,
    render_action_detail,
    render_action_list,
    render_action_update_result,
    render_conversational_next_steps,
    resolve_action_reference,
)
from assistant.mcp import server as mcp_server  # type: ignore
from assistant.memory import (  # type: ignore
    create_candidate,
    direct_approved_write,
    list_candidates,
    memory_health_get,
    memory_profile_get,
    memory_relevant_get,
    transition_candidate,
)


def _trace_route(stage: str, text: str, route: str) -> None:
    compact = " ".join(str(text or "").split())[:180]
    print(f"[paos-route] stage={stage} route={route} text='{compact}'", flush=True)


def _resolve_handoff_target(text: str) -> str:
    lowered = text.lower()
    if "codex" in lowered:
        return "codex"
    if "claude" in lowered:
        return "claude"
    return "generic"


def _render_unknown_message() -> str:
    return (
        "Saya belum paham maksudnya.\n"
        "Coba contoh: 'apa status PAOS hari ini?', 'apa fokus saya sekarang?', "
        "'buat daily plan', 'source intelligence sehat gak?', "
        "'buat handoff Codex dari fokus sekarang', atau 'review hasil Codex ini: ...'."
    )


def _is_greeting_only_text(text: str) -> bool:
    lowered = _normalize_text(text)
    if not lowered:
        return False
    cleaned = re.sub(r"[^a-z\s]", " ", lowered)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    greetings = {
        "halo",
        "hallo",
        "hai",
        "hi",
        "yo",
        "pagi",
        "siang",
        "sore",
        "malam",
        "halo paos",
        "hai paos",
        "hi paos",
    }
    return cleaned in greetings


def _render_greeting_message() -> str:
    return (
        "Halo! PAOS siap. Kamu bisa tanya: apa status PAOS hari ini?, "
        "apa fokus saya sekarang?, buat daily plan, cek context saya sehat gak?, "
        "buat handoff Codex dari fokus sekarang."
    )


def _normalize_text(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _is_action_loop_text(text: str) -> bool:
    lowered = _normalize_text(text)
    if "memory" in lowered:
        return False
    if lowered.isdigit():
        return True
    # Deterministic action-loop routing must stay narrow: only explicit local-state rails.
    intent_patterns = (
        r"\bbuat action hari ini\b",
        r"\bbuat daily action\b",
        r"\bapa action pending saya\b",
        r"\baction saya\b",
        r"\blist action\b",
        r"\bapa fokus saya sekarang\b",
        r"\bapa yang harus saya kerjakan sekarang\b",
        r"\bpilih nomor \d+\b",
        r"\bnomor \d+\b",
        r"\blihat detail\b",
        r"\bbuat handoff codex dari accepted action\b",
        r"\baccept\b",
        r"\breject\b",
        r"\bdefer\b",
        r"\btunda\b",
        r"\btolak\b",
        r"\bjadikan\b",
        r"\bpilih\b",
    )
    return any(re.search(pattern, lowered) for pattern in intent_patterns)


def _is_forbidden_gateway_request(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(
        phrase in lowered
        for phrase in (
            "nyalakan hermes gateway",
            "enable hermes gateway",
            "start hermes gateway",
            "hidupkan hermes gateway",
        )
    )

def _is_daily_operating_text(text: str) -> bool:
    lowered = _normalize_text(text)
    phrases = (
        "apa status paos hari ini",
        "status paos hari ini",
        "daily operating summary",
        "operating summary",
        "apa next step saya sekarang",
        "apa yang perlu saya lakukan selanjutnya",
        "buat daily plan dari context memory source",
        "buat daily plan",
    )
    return any(p in lowered for p in phrases)


def _is_agent_orchestration_text(text: str) -> bool:
    lowered = _normalize_text(text)
    markers = (
        "buat handoff",
        "buat prompt claude",
        "buat prompt codex",
        "hasil codex",
        "hasil claude",
        "hasil agent",
        "next step setelah hasil",
        "next action dari hasil",
        "memory candidate dari hasil",
        "update action ini berdasarkan hasil agent",
        "cek paos siap commit belum",
        "validasi runtime paos",
    )
    return any(x in lowered for x in markers)


async def _handle_agent_orchestration(update, text: str) -> bool:
    lowered = _normalize_text(text)
    target_agent = "generic"
    if "codex" in lowered:
        target_agent = "codex"
    elif "cowork" in lowered:
        target_agent = "claude_cowork"
    elif "claude" in lowered:
        target_agent = "claude_code"
    elif "hermes" in lowered:
        target_agent = "hermes"

    if "buat handoff" in lowered or "buat prompt" in lowered:
        _trace_route("agent", text, "phase9_agent:handoff_create")
        payload = mcp_server.tool_paos_agent_handoff_create(target_agent=target_agent, source="fokus sekarang")
        sections = payload.get("sections") or {}
        handoff = sections.get("handoff") or {}
        prompt = str(sections.get("prompt") or "")
        body = (
            "Handoff dibuat sebagai draft/manual prompt.\n"
            f"- handoff_id: {handoff.get('handoff_id')}\n"
            f"- target: {handoff.get('target_agent')}\n"
            f"- status: {handoff.get('status')}\n\n"
            f"Prompt:\n{prompt}\n\n"
            "No external action was applied.\n"
            "Tidak ada commit/push dan tidak ada GitHub mutation."
        )
        await update.message.reply_text(body[:3900])
        return True

    if "next step setelah hasil" in lowered or "next action dari hasil" in lowered or "update action ini berdasarkan hasil agent" in lowered:
        _trace_route("agent", text, "phase9_agent:next_action_draft")
        payload = mcp_server.tool_paos_agent_next_action_draft(content=text)
        draft = (payload.get("sections") or {}).get("draft") or {}
        await update.message.reply_text(
            (
                "Draft next action lokal berhasil dibuat.\n"
                f"- class: {draft.get('action_class')}\n"
                f"- summary: {str(draft.get('summary') or '-')[:200]}\n"
                "No external action was applied."
            )[:3900]
        )
        return True

    if "memory candidate dari hasil" in lowered:
        _trace_route("agent", text, "phase9_agent:memory_candidate")
        payload = mcp_server.tool_paos_agent_memory_candidate_create(content=text, target_agent=target_agent)
        candidate = (payload.get("sections") or {}).get("candidate") or {}
        await update.message.reply_text(
            (
                "Memory candidate dibuat dari hasil agent (belum durable write).\n"
                f"- candidate_id: {candidate.get('candidate_id', '-') }\n"
                "Balas: 'simpan memory ini' atau 'tolak memory ini' jika ingin tindak lanjut.\n"
                "No external action was applied."
            )[:3900]
        )
        return True

    if "review hasil" in lowered or "hasil codex" in lowered or "hasil claude" in lowered or "hasil agent" in lowered or "sudah sesuai" in lowered:
        _trace_route("agent", text, "phase9_agent:result_review")
        content = text
        if ":" in text:
            content = text.split(":", 1)[1].strip() or text
        payload = mcp_server.tool_paos_agent_result_review(content=content, target_agent=target_agent)
        review = (payload.get("sections") or {}).get("review") or {}
        blockers = review.get("blockers") or []
        safety = review.get("safety_violations") or []
        files = review.get("files_changed") or []
        lines = [
            "Review hasil agent:",
            f"- goal_met: {review.get('goal_met')}",
            f"- commit_readiness: {review.get('commit_readiness')}",
            f"- files_detected: {len(files)}",
            f"- validation_failed_signal: {review.get('validation_failed_signal')}",
            f"- missing_tests: {review.get('missing_tests')}",
        ]
        if blockers:
            lines.append("- blocker: " + str(blockers[0]))
        if safety:
            lines.append("- safety_violation: " + str(safety[0]))
        lines.extend(
            [
                f"- next_safe_step: {review.get('next_safe_step')}",
                "No external action was applied.",
                "Tidak ada commit/push dan tidak ada GitHub mutation.",
            ]
        )
        await update.message.reply_text("\n".join(lines)[:3900])
        return True

    if "cek paos siap commit belum" in lowered or "validasi runtime paos" in lowered:
        _trace_route("agent", text, "phase9_agent:commit_readiness_status")
        runtime = mcp_server.tool_paos_runtime_status_get()
        summary = mcp_server.tool_paos_operating_summary_get(category="ai")
        await update.message.reply_text(
            (
                "Ringkas validasi runtime PAOS:\n"
                f"- runtime: {runtime.get('summary')}\n"
                f"- operating: {summary.get('summary')}\n"
                "Boundary: accepted action != executed; handoff != execution.\n"
                "No external action was applied."
            )[:3900]
        )
        return True
    return False

async def _handle_daily_operating(update, text: str) -> bool:
    lowered = _normalize_text(text)
    try:
        if "daily plan" in lowered or "rencana harian" in lowered:
            payload = mcp_server.tool_paos_daily_plan_get(category="ai")
            if not payload.get("ok"):
                await update.message.reply_text("Daily plan belum bisa dibangun sekarang. No external action was applied.")
                return True
            sections = payload.get("sections") or {}
            plan = sections.get("daily_plan") or []
            next_step = str(sections.get("recommended_next_safe_step") or "Review pending action paling atas.")
            lines = ["Daily plan hari ini:"]
            for idx, item in enumerate(plan[:4], start=1):
                lines.append(f"{idx}. {str(item)}")
            lines.append(f"Next safe step: {next_step}")
            lines.append("No external action was applied.")
            await update.message.reply_text("\n".join(lines)[:3900])
            return True

        payload = mcp_server.tool_paos_operating_summary_get(category="ai")
        if not payload.get("ok"):
            await update.message.reply_text("Operating summary belum tersedia. Coba cek lagi sebentar.")
            return True
        sections = payload.get("sections") or {}
        focus = (sections.get("focus") or {}).get("current_focus") or "Belum ada fokus"
        pending = (sections.get("focus") or {}).get("pending_action_count")
        source_summary = (sections.get("source_intelligence") or {}).get("latest_insight_summary") or "-"
        memory_summary = (sections.get("memory_health") or {}).get("summary") or "-"
        next_step = sections.get("recommended_next_safe_step") or "Review action pending paling atas."
        lines = [
            "Status PAOS hari ini:",
            f"- Fokus: {focus}",
            f"- Pending action: {pending}",
            f"- Source insight: {source_summary}",
            f"- Memory health: {memory_summary}",
            f"- Next safe step: {next_step}",
        ]
        await update.message.reply_text("\n".join(lines)[:3900])
        return True
    except Exception:
        return False


def _extract_memory_type(text: str) -> str:
    lowered = _normalize_text(text)
    if any(x in lowered for x in ("prefer", "suka", "tidak suka")):
        return "preference"
    if any(x in lowered for x in ("cara kerja", "workflow", "gaya kerja")):
        return "working_style"
    if any(x in lowered for x in ("keputusan", "decide", "diputuskan")):
        return "decision"
    if any(x in lowered for x in ("status", "state", "sedang")):
        return "task_state"
    if "paos" in lowered:
        return "project_fact"
    return "note"


def _extract_memory_content(text: str) -> str:
    raw = str(text or "").strip()
    cleaned = re.sub(r"^(ingat ini|simpan ini ke memory|simpan ini|update memory tentang)\s*[:\-]?\s*", "", raw, flags=re.I)
    return cleaned.strip() or raw


async def _handle_memory_intent(update, text: str) -> bool:
    lowered = _normalize_text(text)
    if not lowered:
        return False

    if any(x in lowered for x in ("ingat ini", "simpan ini", "update memory")):
        content = _extract_memory_content(text)
        if not content:
            await update.message.reply_text("Isi memory belum jelas. Tulis singkat apa yang mau disimpan.")
            return True
        memory_type = _extract_memory_type(text)
        result = direct_approved_write(
            content,
            memory_type=memory_type,
            source_type="manual_user_instruction",
            source_ref="telegram/free-text",
            evidence_summary=f"Instruksi user eksplisit: {_normalize_text(text)[:160]}",
            confidence=0.95,
        )
        if result.get("ok"):
            await update.message.reply_text("Memory tersimpan dan aktif. Memory was written.")
        else:
            await update.message.reply_text("Gagal menyimpan memory. No memory was written yet.")
        return True

    if any(x in lowered for x in ("apa yang kamu ingat", "apa yang kamu ingat soal", "memory relevan", "cara kerja saya", "apa memory yang relevan")):
        topic = text
        for prefix in ("apa yang kamu ingat soal", "apa yang kamu ingat", "apa memory yang relevan untuk codex sekarang"):
            if lowered.startswith(prefix):
                topic = text[len(prefix):].strip(" :")
                break
        topic = re.sub(r"[^a-zA-Z0-9\s]", " ", topic).strip()
        payload = memory_relevant_get(query=topic, limit=5)
        if not (payload.get("items") or []):
            payload = memory_profile_get(limit=5)
        items = payload.get("items") or []
        if not items:
            await update.message.reply_text("Belum ada memory aktif yang relevan. No memory was written yet.")
            return True
        lines = ["Memory relevan:"]
        for idx, item in enumerate(items[:5], start=1):
            lines.append(f"{idx}. [{item.get('type')}] {str(item.get('content') or '')[:180]}")
        await update.message.reply_text("\n".join(lines)[:3900])
        return True

    if "ada memory baru yang perlu disimpan" in lowered:
        payload = list_candidates(status="candidate", limit=5)
        items = payload.get("items") or []
        if not items:
            await update.message.reply_text("Belum ada candidate memory baru. No memory was written yet.")
            return True
        lines = ["Ada candidate memory baru:"]
        for idx, item in enumerate(items[:5], start=1):
            lines.append(f"{idx}. [{item.get('type')}] {str(item.get('content') or '')[:140]}")
        lines.append("Balas natural: 'simpan nomor 1' atau 'tolak memory itu'.")
        await update.message.reply_text("\n".join(lines)[:3900])
        return True

    if "simpan nomor" in lowered:
        match = re.search(r"simpan nomor\s+(\d+)", lowered)
        if not match:
            await update.message.reply_text("Nomor candidate belum jelas. No memory was written yet.")
            return True
        ordinal = int(match.group(1))
        listed = list_candidates(status="candidate", limit=20).get("items") or []
        if ordinal <= 0 or ordinal > len(listed):
            await update.message.reply_text("Nomor candidate tidak ditemukan. No memory was written yet.")
            return True
        candidate_id = str(listed[ordinal - 1].get("candidate_id") or "")
        result = transition_candidate(candidate_id, "approve")
        if result.get("ok"):
            await update.message.reply_text("Candidate disetujui dan memory ditulis. Memory was written.")
        else:
            await update.message.reply_text("Candidate belum bisa disimpan. No memory was written yet.")
        return True

    if "tolak memory itu" in lowered:
        listed = list_candidates(status="candidate", limit=1).get("items") or []
        if not listed:
            await update.message.reply_text("Tidak ada candidate aktif untuk ditolak. No memory was written yet.")
            return True
        candidate_id = str(listed[0].get("candidate_id") or "")
        result = transition_candidate(candidate_id, "reject")
        if result.get("ok"):
            await update.message.reply_text("Candidate memory ditolak. No memory was written yet.")
        else:
            await update.message.reply_text("Gagal menolak candidate memory. No memory was written yet.")
        return True

    if "memory paos saya sehat" in lowered:
        payload = memory_health_get()
        await update.message.reply_text(
            (
                f"{payload.get('summary')}\n"
                f"Warnings: {', '.join(payload.get('warnings') or ['-'])}\n"
                "No memory was written yet."
            )[:3900]
        )
        return True

    return False


async def _handle_action_loop(update, text: str) -> bool:
    lowered = _normalize_text(text)
    if lowered.isdigit():
        _trace_route("action-loop", text, "phase5_action_loop:transition:ordinal_numeric")
        action = resolve_action_reference(reference=f"nomor {lowered}", ordinal=int(lowered))
        if not action:
            await update.message.reply_text("Referensi belum jelas. Maksud Anda nomor berapa dari daftar terakhir?")
            return True
        result = accept_action(action.action_id, actor="telegram", note=f"ordinal {lowered}")
        if result.ok and result.action:
            await update.message.reply_text(
                (
                    f"Action '{result.action.title}' berubah: {action.state} -> {result.action.state}.\n"
                    "Accepted berarti arah/fokus dipilih, bukan dieksekusi.\n"
                    "No external action was applied."
                )[:3900]
            )
        else:
            await update.message.reply_text(render_action_update_result(result))
        return True
    if "buat action hari ini" in lowered or ("daily action" in lowered and "buat" in lowered):
        _trace_route("action-loop", text, "phase5_action_loop:create_daily")
        result = create_daily_action(category="runtime", persist=True, actor="telegram")
        if not result.ok or not result.action:
            await update.message.reply_text("Gagal membuat action harian. No external action was applied.")
            return True
        message = (
            "Action harian dibuat.\n"
            f"1. {result.action.title}\n"
            f"   id: {result.action.action_id}\n"
            f"   state: {result.action.state}\n"
            "Balas natural: accept / reject / defer / lihat detail / pilih nomor 1.\n"
            "No external action was applied."
        )
        await update.message.reply_text(message[:3900])
        return True

    if "pending" in lowered or "action saya" in lowered or "list action" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:list_pending")
        actions = action_loop_list_actions(limit=30, remember_list=False)
        pending = [
            a for a in actions
            if a.state in {"proposed", "deferred"} and not str(a.source).lower().startswith("e2e")
        ][:5]
        try:
            from assistant.action_loop.store import load_index, save_index  # type: ignore

            idx = load_index()
            idx["latest_listed_action_ids"] = [a.action_id for a in pending]
            save_index(idx)
        except Exception:
            pass
        if not pending:
            await update.message.reply_text("Pending Actions kosong. No external action was applied.")
            return True
        await update.message.reply_text(render_action_list(pending, title="Pending Actions"))
        return True

    if "apa yang harus saya kerjakan sekarang" in lowered or "apa fokus saya sekarang" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:focus")
        accepted = action_loop_list_actions(state="accepted", limit=1, remember_list=False)
        if accepted:
            await update.message.reply_text(render_conversational_next_steps(accepted[0]))
            return True
        proposed = action_loop_list_actions(state="proposed", limit=1, remember_list=False)
        if proposed:
            top = proposed[0]
            await update.message.reply_text(
                (
                    f"Belum ada accepted action.\n"
                    f"Usulan teratas: 1. {top.title} ({top.action_id}) [proposed]\n"
                    "Balas natural: pilih nomor 1 / tunda yang tadi / tolak yang tadi.\n"
                    "No external action was applied."
                )[:3900]
            )
            return True
        await update.message.reply_text(render_conversational_next_steps(None))
        return True

    if "lihat detail" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:detail")
        action = resolve_action_reference(reference=lowered)
        if not action:
            await update.message.reply_text("Saya belum bisa resolve referensinya. Sebut 'nomor 1' dari list terbaru.")
            return True
        await update.message.reply_text(render_action_detail(action))
        return True

    if "handoff codex" in lowered and "accepted" in lowered:
        _trace_route("action-loop", text, "phase5_action_loop:handoff_codex")
        accepted = action_loop_list_actions(state="accepted", limit=1, remember_list=False)
        if not accepted:
            await update.message.reply_text("Belum ada accepted action. No external action was applied.")
            return True
        action = accepted[0]
        handoff = (
            "Codex Handoff Draft\n"
            f"Action: {action.title}\n"
            f"Summary: {action.summary}\n"
            "Steps:\n" + "\n".join([f"{i}. {s}" for i, s in enumerate(action.steps[:5], start=1)]) +
            "\nNo external action was applied."
        )
        await update.message.reply_text(handoff[:3900])
        return True

    for trigger, fn in (("accept", accept_action), ("jadikan", accept_action), ("pilih", accept_action), ("reject", reject_action), ("tolak", reject_action), ("defer", defer_action), ("tunda", defer_action)):
        if trigger in lowered:
            _trace_route("action-loop", text, f"phase5_action_loop:transition:{trigger}")
            ordinal_match = re.search(r"nomor\s+(\d+)", lowered)
            ordinal = int(ordinal_match.group(1)) if ordinal_match else None
            action = resolve_action_reference(reference=lowered, ordinal=ordinal)
            if not action:
                await update.message.reply_text("Referensi belum jelas. Maksud Anda nomor berapa dari daftar terakhir?")
                return True
            result = fn(action.action_id, actor="telegram", note=lowered)
            if result.ok and result.action:
                previous_state = action.state
                await update.message.reply_text(
                    (
                        f"Action '{result.action.title}' berubah: {previous_state} -> {result.action.state}.\n"
                        "Accepted berarti arah/fokus dipilih, bukan dieksekusi.\n"
                        "No external action was applied."
                    )[:3900]
                )
            else:
                await update.message.reply_text(render_action_update_result(result))
            return True
    return False


async def _handle_source_intelligence(update, text: str) -> bool:
    lowered = _normalize_text(text)
    if any(k in lowered for k in ("source intelligence saya sehat", "source intelligence sehat", "status source", "source status")):
        _trace_route("source-intel", text, "phase6_source_status")
        payload = get_source_status(category="ai").payload
        await update.message.reply_text(
            (
                f"{payload.get('summary')}\n"
                f"Rekomendasi: {payload.get('recommended_next_maintenance_action')}\n"
                "No external action was applied."
            )[:3900]
        )
        return True
    if any(k in lowered for k in ("insight ai yang penting", "insight hari ini", "insight dari github", "insight dari threads")):
        _trace_route("source-intel", text, "phase6_source_insight")
        payload = get_source_insights(category="ai", limit=3)
        items = payload.get("items") or []
        if not items:
            await update.message.reply_text("Belum ada insight terbaru. Coba jalankan pipeline intelligence dulu.")
            return True
        lines = []
        for i, item in enumerate(items[:3], start=1):
            lines.append(f"{i}. {item.get('title', '-')}")
            lines.append(f"   alasan: {str(item.get('reason') or '-')[:180]}")
            lines.append(f"   source: {item.get('source_ref') or item.get('source_refs') or '-'}")
        await update.message.reply_text(("\n".join(lines))[:3900])
        return True
    if any(k in lowered for k in ("source paling berguna", "rekomendasi source", "keyword yang perlu saya ubah")):
        _trace_route("source-intel", text, "phase6_source_recommendation")
        payload = get_source_recommendation(category="ai")
        msg = "Rekomendasi source/keyword:\n" + "\n".join(f"- {x}" for x in (payload.get("items") or [])[:5])
        await update.message.reply_text(msg[:3900])
        return True
    if any(k in lowered for k in ("buat action dari insight terbaru", "source intelligence terbaru", "jadikan insight terbaru sebagai proposed action")):
        _trace_route("source-intel", text, "phase6_source_action_from_insight")
        payload = create_action_from_latest_insight(category="ai")
        if not payload.get("ok"):
            await update.message.reply_text("Gagal membuat proposed action dari insight terbaru.")
            return True
        action = (payload.get("action") or {})
        await update.message.reply_text(
            (
                "Proposed action dibuat dari insight terbaru.\n"
                f"- title: {action.get('title')}\n"
                f"- state: {action.get('state')}\n"
                "No external action was applied."
            )[:3900]
        )
        return True
    return False


async def handle_free_text_query(update, context):
    text = str(update.message.text or "").strip()
    if _is_forbidden_gateway_request(text):
        _trace_route("free-text", text, "blocked_gateway_request")
        await update.message.reply_text(
            "Permintaan ditolak oleh policy: Hermes gateway tidak boleh dinyalakan dari Telegram. "
            "No external action was applied."
        )
        return
    if _is_action_loop_text(text):
        _trace_route("free-text", text, "phase5_action_loop:intent_match")
        if await _handle_action_loop(update, text):
            return
    if await _handle_memory_intent(update, text):
        _trace_route("free-text", text, "phase7_memory_intent")
        return
    hermes_attempted = False
    if hermes_orchestration_enabled():
        hermes_attempted = True
        _trace_route("free-text", text, "hermes_orchestration")
        hermes_result = query_hermes(text, timeout_seconds=hermes_timeout_seconds())
        if hermes_result.used and hermes_result.response_text.strip():
            _trace_route("free-text", text, "hermes_response_used")
            await update.message.reply_text(hermes_result.response_text.strip())
            return
        _trace_route("free-text", text, "hermes_fallback_after_empty_or_error")
    else:
        _trace_route("free-text", text, "hermes_unavailable:orchestration_disabled")

    if _is_greeting_only_text(text):
        _trace_route("free-text", text, "greeting_fallback")
        await update.message.reply_text(_render_greeting_message())
        return

    if not hermes_attempted:
        _trace_route("free-text", text, "unknown_after_hermes_unavailable")
    else:
        _trace_route("free-text", text, "unknown_after_hermes_attempt")

    await update.message.reply_text(_render_unknown_message())
