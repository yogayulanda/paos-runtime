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
    create_daily_action,
    list_actions as action_loop_list_actions,
    render_action_detail,
    render_action_list,
    render_conversational_next_steps,
    resolve_action_reference,
)
from assistant.mcp import server as mcp_server  # type: ignore
from assistant.memory import (  # type: ignore
    create_candidate,
    list_candidates,
    memory_health_get,
    memory_profile_get,
    memory_relevant_get,
    working_context_get,
)


def _has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


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
    return "Saya belum kebaca jelas. Coba tulis tujuanmu dalam 1 kalimat biar saya kasih next action paling tepat."


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
        "siang",
        "sore",
        "malam",
        "halo paos",
        "hai paos",
        "hi paos",
    }
    return cleaned in greetings


def _render_greeting_message() -> str:
    return "Halo, saya siap bantu. Mulai dari prioritasmu sekarang, nanti saya bantu pecah jadi next action yang jelas."


def _normalize_text(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered

def _compact_confidence(label: str, reason: str) -> str:
    return f"{label} ({reason[:120]})" if reason else label

def _render_product_value_block(
    *,
    title: str,
    status_signal: str,
    why_it_matters: str,
    best_next_action: str,
    confidence: str,
    evidence: str,
) -> str:
    lines = [
        f"{title}",
        f"- Status utama: {status_signal}",
        f"- Kenapa ini penting: {why_it_matters}",
        f"- Next action (30-60 menit): {best_next_action}",
        f"- Confidence: {confidence}",
        f"- Evidence ringkas: {evidence}",
        "No external action was applied.",
    ]
    return "\n".join(lines)[:3900]


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
        r"\bapa action pending saya\b",
        r"\blist action\b",
        r"\bpilih nomor \d+\b",
        r"\bnomor \d+\b",
        r"\blihat detail\b",
        r"\bbuat handoff codex dari accepted action\b",
        r"\baccept\b",
        r"\breject\b",
        r"\bdefer\b",
        r"\btunda\b",
        r"\btolak\b",
        r"\bjadikan nomor \d+\b",
        r"\bpilih nomor \d+\b",
    )
    return any(re.search(pattern, lowered) for pattern in intent_patterns)


def _is_approval_text(text: str) -> bool:
    lowered = _normalize_text(text)
    patterns = (
        r"\btampilkan approval pending\b",
        r"\blist approval\b",
        r"\bapprove\b",
        r"\breject approval\b",
        r"\bcancel approval\b",
        r"\bapply approval\b",
        r"\bapa yang akan di-apply\b",
        r"\bjalankan perubahan ini\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _format_approval_line(item: dict, idx: int) -> str:
    return (
        f"{idx}. {item.get('approval_id')} [{item.get('status')}]\n"
        f"   op: {item.get('operation_type')} | risk: {item.get('risk_level')}\n"
        f"   what: {str(item.get('proposed_operation') or '-')[:140]}"
    )


def _resolve_approval_id_from_text(lowered: str) -> str | None:
    direct = re.search(r"approval[_\-a-z0-9]+", lowered)
    if direct:
        return direct.group(0)
    ord_match = re.search(r"nomor\s+(\d+)", lowered)
    if not ord_match:
        return None
    ordinal = int(ord_match.group(1))
    listed = (mcp_server.tool_paos_approval_list(status="pending", limit=20).get("items") or [])
    if ordinal <= 0 or ordinal > len(listed):
        return None
    return str(listed[ordinal - 1].get("approval_id") or "")


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


def _is_blocked_unsafe_operation_request(text: str) -> bool:
    lowered = _normalize_text(text)
    markers = (
        "github",
        "commit",
        "push",
        "merge",
        "pull request",
        "systemd",
        "systemctl",
        "cron",
        "scheduler",
        "arbitrary shell",
        "jalankan shell",
        "run shell",
        "public api",
        "tunnel",
        "start hermes gateway",
    )
    return any(x in lowered for x in markers)

def _is_daily_operating_text(text: str) -> bool:
    lowered = _normalize_text(text)
    phrases = (
        "pagi",
        "pagi, hari ini fokus apa",
        "pagi hari ini fokus apa",
        "hari ini fokus apa",
        "apa status paos hari ini",
        "status paos hari ini",
        "daily operating summary",
        "operating summary",
        "apa next terbaik sekarang",
        "next terbaik sekarang",
        "apa next step saya sekarang",
        "apa yang perlu saya lakukan selanjutnya",
        "apa yang menarik hari ini",
        "review action saya",
        "buat daily plan dari context memory source",
        "buat daily plan",
    )
    return any(p in lowered for p in phrases)


def _is_weekly_review_text(text: str) -> bool:
    lowered = _normalize_text(text)
    return _has_any_phrase(
        lowered,
        (
            "review minggu ini",
            "weekly review",
            "ringkas minggu ini",
            "minggu ini gimana",
        ),
    )


def _is_agent_orchestration_text(text: str) -> bool:
    lowered = _normalize_text(text)
    markers = (
        "buat handoff",
        "siapkan prompt untuk agent lain",
        "buat handoff untuk codex",
        "buat handoff untuk claude",
        "buat prompt claude",
        "buat prompt codex",
        "hasil codex",
        "review hasil codex ini",
        "hasil claude",
        "hasil agent",
        "review hasil agent ini",
        "next step setelah hasil",
        "apa next setelah hasil ini",
        "next action dari hasil",
        "jadikan hasil ini action",
        "memory candidate dari hasil",
        "buat memory candidate dari hasil ini",
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

    if "buat handoff" in lowered or "buat prompt" in lowered or "siapkan prompt untuk agent lain" in lowered:
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

    if (
        "next step setelah hasil" in lowered
        or "next action dari hasil" in lowered
        or "update action ini berdasarkan hasil agent" in lowered
        or "apa next setelah hasil ini" in lowered
        or "jadikan hasil ini action" in lowered
    ):
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

    if "memory candidate dari hasil" in lowered or "buat memory candidate dari hasil ini" in lowered:
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

    if (
        "review hasil" in lowered
        or "review hasil codex ini" in lowered
        or "review hasil agent ini" in lowered
        or "hasil codex" in lowered
        or "hasil claude" in lowered
        or "hasil agent" in lowered
        or "sudah sesuai" in lowered
    ):
        _trace_route("agent", text, "phase9_agent:result_review")
        content = text
        if ":" in text:
            content = text.split(":", 1)[1].strip() or text
        payload = mcp_server.tool_paos_agent_result_review(content=content, target_agent=target_agent)
        review = (payload.get("sections") or {}).get("review") or {}
        blockers = review.get("blockers") or []
        safety = review.get("safety_violations") or []
        files = review.get("files_changed") or []
        goal_met = bool(review.get("goal_met"))
        commit_ready = bool(review.get("commit_readiness"))
        has_safety_violation = len(safety) > 0
        has_blocker = len(blockers) > 0
        if has_safety_violation:
            result_status = "unsafe"
        elif has_blocker:
            result_status = "needs_follow_up"
        elif goal_met and commit_ready:
            result_status = "accepted"
        else:
            result_status = "incomplete"
        impact_to_goal = "Mendorong goal utama karena patch mengurangi gap readiness." if goal_met else "Belum menutup goal utama, masih perlu perbaikan sebelum lanjut."
        decision_recommendation = "Lanjutkan ke verifikasi final + apply lokal terbatas." if result_status == "accepted" else "Tahan apply, selesaikan blocker/risiko dulu."
        top_risk = str((safety[0] if safety else (blockers[0] if blockers else "tidak ada risiko kritis terdeteksi")))[:180]
        lines = [
            "Review hasil agent:",
            f"- Hasil status: {result_status}",
            f"- Impact ke goal: {impact_to_goal}",
            f"- Decision recommendation: {decision_recommendation}",
            f"- Risk/Blocker utama: {top_risk}",
            f"- Next action (30-60 menit): {review.get('next_safe_step')}",
            f"- Confidence: {_compact_confidence('sedang', 'berdasarkan sinyal goal_met, readiness, blocker, dan safety')}",
            f"- Evidence ringkas: files={len(files)}, validation_failed={review.get('validation_failed_signal')}, missing_tests={review.get('missing_tests')}",
            "No external action was applied.",
            "Tidak ada commit/push dan tidak ada GitHub mutation.",
        ]
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
        if _is_weekly_review_text(text):
            summary = mcp_server.tool_paos_operating_summary_get(category="ai")
            source = mcp_server.tool_paos_source_insight_get(category="ai", limit=3)
            focus_section = (summary.get("sections") or {}).get("focus") or {}
            source_section = (summary.get("sections") or {}).get("source_intelligence") or {}
            memory_candidates = list_candidates(status="candidate", limit=3).get("items") or []

            accepted = action_loop_list_actions(state="accepted", limit=1, remember_list=False)
            pending = [
                a for a in action_loop_list_actions(limit=20, remember_list=False)
                if a.state in {"proposed", "deferred"}
            ][:3]

            interesting = source.get("items") or []
            focus = focus_section.get('current_focus') or (accepted[0].title if accepted else 'Belum ada accepted focus')
            signal = str(interesting[0].get('title') or '-')[:180] if interesting else str(source_section.get('latest_insight_summary') or '-')
            tradeoff = (
                f"Ada {len(pending)} pending action; fokus ke 1 prioritas akan menunda item lain tapi mempercepat hasil utama."
            )
            evidence = f"focus={focus}; pending={len(pending)}; signal={signal[:90]}"
            await update.message.reply_text(
                _render_product_value_block(
                    title="Review minggu ini:",
                    status_signal=f"Fokus aktif: {focus}. Signal terbaru: {signal}",
                    why_it_matters=tradeoff,
                    best_next_action=str((summary.get("sections") or {}).get("recommended_next_safe_step") or "Tutup 1 pending action prioritas tinggi terlebih dulu."),
                    confidence=_compact_confidence("sedang", "berdasarkan focus aktif, pending queue, dan signal intelligence"),
                    evidence=evidence,
                )
            )
            return True

        if "daily plan" in lowered or "rencana harian" in lowered:
            payload = mcp_server.tool_paos_daily_plan_get(category="ai")
            if not payload.get("ok"):
                await update.message.reply_text("Daily plan belum bisa dibangun sekarang. No external action was applied.")
                return True
            sections = payload.get("sections") or {}
            plan = sections.get("daily_plan") or []
            next_step = str(sections.get("recommended_next_safe_step") or "Review pending action paling atas.")
            top_items = [str(x) for x in plan[:3]]
            priority = top_items[0] if top_items else "Belum ada prioritas yang cukup jelas"
            tradeoff = "Menuntaskan prioritas #1 akan mengurangi bandwidth untuk item lain, tapi memberi progress paling terlihat hari ini."
            evidence = f"plan_items={len(plan)}; top_priority={priority[:80]}"
            await update.message.reply_text(
                _render_product_value_block(
                    title="Daily plan hari ini:",
                    status_signal=f"Prioritas utama: {priority}",
                    why_it_matters=tradeoff,
                    best_next_action=next_step,
                    confidence=_compact_confidence("sedang", "berdasarkan daily plan dan urutan prioritas saat ini"),
                    evidence=evidence,
                )
            )
            return True

        if _has_any_phrase(lowered, ("apa yang menarik hari ini", "yang menarik hari ini", "interesting today", "insight terbaru apa", "insight terbaru", "ada opportunity apa", "opportunity apa")):
            payload = mcp_server.tool_paos_source_insight_get(category="ai", limit=3)
            items = payload.get("items") or []
            if not items:
                await update.message.reply_text("Belum ada signal menarik hari ini. No external action was applied.")
                return True
            lines = ["Yang menarik hari ini:"]
            for idx, item in enumerate(items[:3], start=1):
                title = str(item.get('title') or '-')[:130]
                reason = str(item.get('reason') or '-')[:120]
                leverage = str(item.get('opportunity') or item.get('leverage') or 'potensi leverage ada jika dieksekusi cepat')[:110]
                decision = str(item.get('decision_recommendation') or item.get('next_action') or 'pilih satu eksperimen kecil dan validasi hasilnya hari ini')[:120]
                confidence = str(item.get('confidence') or 'sedang')[:80]
                source = str(item.get('source_ref') or item.get('source') or '-')[:90]
                lines.append(f"{idx}. {title}")
                lines.append(f"   kenapa ini penting: {reason}")
                lines.append(f"   leverage: {leverage}")
                lines.append(f"   rekomendasi keputusan: {decision}")
                lines.append(f"   confidence/reason: {confidence}")
                lines.append(f"   evidence sumber: {source}")
            lines.append("No external action was applied.")
            await update.message.reply_text("\n".join(lines)[:3900])
            return True

        if _has_any_phrase(lowered, ("trend apa yang relevan buat paos", "trend relevan paos", "opportunity scoring")):
            payload = mcp_server.tool_paos_source_recommendation_get(category="ai")
            opportunities = payload.get("opportunities") or []
            if not opportunities:
                await update.message.reply_text("Belum ada trend/opportunity yang cukup kuat hari ini. No external action was applied.")
                return True
            lines = ["Trend relevan buat PAOS:"]
            for idx, item in enumerate(opportunities[:3], start=1):
                lines.append(f"{idx}. {str(item.get('title') or '-')[:150]}")
                lines.append(f"   score: {item.get('opportunity_score')} | why: {str(item.get('why_it_matters') or '-')[:120]}")
                lines.append(f"   next action draft: {str(item.get('suggested_next_action_draft') or '-')[:140]}")
            lines.append("No external action was applied.")
            await update.message.reply_text("\n".join(lines)[:3900])
            return True

        if _has_any_phrase(lowered, ("apa next terbaik sekarang", "next terbaik sekarang", "next best action", "apa next step saya sekarang")):
            payload = mcp_server.tool_paos_operating_summary_get(category="ai")
            sections = payload.get("sections") or {}
            recommended = str(sections.get("recommended_next_safe_step") or "Review pending action paling atas.")
            focus = (sections.get("focus") or {}).get("current_focus") or "Belum ada fokus aktif"
            await update.message.reply_text(
                _render_product_value_block(
                    title="Next terbaik sekarang:",
                    status_signal=f"Fokus saat ini: {focus}",
                    why_it_matters="Memilih satu next action sekarang menurunkan context switching dan mempercepat output nyata.",
                    best_next_action=recommended,
                    confidence=_compact_confidence("tinggi", "rekomendasi berasal dari operating summary terbaru"),
                    evidence=f"focus={focus[:80]}; recommendation={recommended[:80]}",
                )
            )
            return True

        if _has_any_phrase(lowered, ("review action saya", "review action", "ulasan action saya")):
            accepted = action_loop_list_actions(state="accepted", limit=1, remember_list=False)
            pending = [
                a for a in action_loop_list_actions(limit=20, remember_list=False)
                if a.state in {"proposed", "deferred"}
            ][:3]
            focus_title = accepted[0].title if accepted else "Belum ada accepted focus"
            pending_top = pending[0].title if pending else "-"
            await update.message.reply_text(
                _render_product_value_block(
                    title="Review action saat ini:",
                    status_signal=f"Focus terpilih: {focus_title}; pending: {len(pending)}",
                    why_it_matters="Jika pending terlalu banyak, fokus terpecah dan delivery melambat.",
                    best_next_action=f"Eksekusi 30-60 menit pada '{pending_top if pending else focus_title}' lalu update status.",
                    confidence=_compact_confidence("sedang", "berdasarkan state accepted/proposed/deferred saat ini"),
                    evidence=f"accepted={bool(accepted)}; pending_count={len(pending)}; top_pending={pending_top[:80]}",
                )
            )
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
        await update.message.reply_text(
            _render_product_value_block(
                title="Status PAOS hari ini:",
                status_signal=f"Fokus: {focus}; pending action: {pending}; signal: {source_summary}",
                why_it_matters="Status ini menunjukkan apakah kamu perlu lanjut eksekusi fokus atau rapikan konteks dulu.",
                best_next_action=str(next_step),
                confidence=_compact_confidence("sedang", "berdasarkan operating summary, source insight, dan memory health"),
                evidence=f"focus={focus[:60]}; pending={pending}; memory={memory_summary[:70]}",
            )
        )
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

    if any(x in lowered for x in ("kayaknya perlu diingat", "mungkin perlu diingat", "ini mungkin penting", "catat sebagai candidate")):
        content = _extract_memory_content(text)
        result = create_candidate(
            content,
            memory_type=_extract_memory_type(text),
            source_type="inferred_from_dialogue",
            source_ref="telegram/free-text",
            evidence_summary=f"Inferred candidate from user utterance: {_normalize_text(text)[:160]}",
            confidence=0.7,
            status="candidate",
        )
        if result.get("ok"):
            await update.message.reply_text(
                "Memory candidate dibuat (belum ditulis sebagai memory aktif). Balas: 'simpan nomor 1' atau 'tolak memory itu'.\n"
                "No external action was applied."
            )
        else:
            await update.message.reply_text("Gagal membuat memory candidate. No memory was written yet.")
        return True

    if any(x in lowered for x in ("ingat ini", "simpan ini", "update memory")):
        content = _extract_memory_content(text)
        if not content:
            await update.message.reply_text("Isi memory belum jelas. Tulis singkat apa yang mau disimpan.")
            return True
        memory_type = _extract_memory_type(text)
        candidate = create_candidate(
            content,
            memory_type=memory_type,
            source_type="manual_user_instruction",
            source_ref="telegram/free-text",
            evidence_summary=f"Instruksi user eksplisit: {_normalize_text(text)[:160]}",
            confidence=0.95,
            status="candidate",
            metadata={"explicit_request": True, "approval_required": True},
        )
        if not candidate.get("ok"):
            await update.message.reply_text("Gagal membuat memory candidate untuk approval. No memory was written yet.")
            return True
        candidate_payload = candidate.get("candidate") or {}
        candidate_id = str(candidate_payload.get("candidate_id") or "")
        proposal = mcp_server.tool_paos_approval_propose(
            source="telegram/free-text",
            requested_by="user",
            proposed_operation="promote memory candidate from explicit free-text memory write",
            operation_type="memory_candidate_promotion",
            evidence_refs=["telegram/free-text", f"query:{_normalize_text(text)[:120]}", f"candidate_id:{candidate_id}"],
            payload_preview={
                "candidate_id": candidate_id,
                "content_preview": content[:180],
                "memory_type": memory_type,
            },
        )
        approval = proposal.get("approval") or {}
        await update.message.reply_text(
            (
                "Permintaan disiapkan sebagai approval (belum dieksekusi).\n"
                f"- candidate_id: {candidate_id}\n"
                f"- approval_id: {approval.get('approval_id')}\n"
                f"- risk: {approval.get('risk_level')}\n"
                "Lanjutkan: approve approval ini, lalu apply approval ini.\n"
                "No external action was applied."
            )[:3900]
        )
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

    if any(x in lowered for x in ("context kerja saya sekarang", "working context saya", "konteks aktif saya", "temporary context saya")):
        payload = working_context_get(category="ai")
        ctx = payload.get("context") or {}
        focus = (ctx.get("current_focus") or {}).get("title") or "Belum ada focus aktif"
        pending = ctx.get("pending_focus") or []
        decisions = ctx.get("recent_decisions") or []
        handoff = ctx.get("active_handoff") or {}
        latest_decision = str(decisions[0].get('content') or '-')[:120] if decisions else "belum ada keputusan terbaru"
        active_handoff = f"{handoff.get('handoff_id')} ({handoff.get('target_agent')})" if handoff.get("handoff_id") else "tidak ada"
        await update.message.reply_text(
            _render_product_value_block(
                title="Working context saat ini:",
                status_signal=f"Focus: {focus}; pending: {len(pending)}; handoff aktif: {active_handoff}",
                why_it_matters="Context yang jelas mengurangi salah prioritas dan mempercepat keputusan eksekusi.",
                best_next_action=f"Pilih satu fokus utama dan jalankan 30-60 menit, mulai dari: {focus}",
                confidence=_compact_confidence("sedang", "berdasarkan focus aktif, pending queue, dan keputusan terbaru"),
                evidence=f"decision={latest_decision}; pending={len(pending)}; handoff={active_handoff[:70]}",
            )
        )
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
        proposal = mcp_server.tool_paos_approval_propose(
            source="telegram/memory-candidate",
            requested_by="user",
            proposed_operation=f"promote memory candidate {candidate_id}",
            operation_type="memory_candidate_promotion",
            evidence_refs=["memory/candidate", f"candidate_id:{candidate_id}"],
            payload_preview={"candidate_id": candidate_id},
        )
        approval = proposal.get("approval") or {}
        await update.message.reply_text(
            (
                "Candidate dipilih untuk approval flow.\n"
                f"- approval_id: {approval.get('approval_id')}\n"
                "Belum ditulis ke memory aktif. Approve dulu lalu apply explicit.\n"
                "No external action was applied."
            )[:3900]
        )
        return True

    if "tolak memory itu" in lowered:
        listed = list_candidates(status="candidate", limit=1).get("items") or []
        if not listed:
            await update.message.reply_text("Tidak ada candidate aktif untuk ditolak. No memory was written yet.")
            return True
        candidate_id = str(listed[0].get("candidate_id") or "")
        result = mcp_server.tool_paos_memory_candidate_transition(candidate_id=candidate_id, transition="reject")
        if not result.get("ok"):
            await update.message.reply_text("Reject candidate memory butuh approval rail terpisah. No memory was written yet.")
        else:
            await update.message.reply_text("Candidate memory ditolak. No memory was written yet.")
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
        proposal = mcp_server.tool_paos_approval_propose(
            source="telegram/action-loop",
            requested_by="user",
            proposed_operation=f"set action {action.action_id} -> accepted",
            operation_type="local_action_state_update",
            evidence_refs=["action-loop", f"action_id:{action.action_id}"],
            payload_preview={"action_id": action.action_id, "transition": "accepted", "note": f"ordinal {lowered}"},
        )
        approval = proposal.get("approval") or {}
        await update.message.reply_text(
            (
                f"Permintaan accept action dibuat sebagai approval: {approval.get('approval_id')}.\n"
                "Accepted action tetap chosen focus; belum ada apply.\n"
                "Gunakan approve lalu apply approval secara explicit.\n"
                "No external action was applied."
            )[:3900]
        )
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

    if "pending" in lowered or "apa action pending saya" in lowered or "list action" in lowered:
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

    for trigger, target_transition in (("accept", "accepted"), ("jadikan", "accepted"), ("pilih", "accepted"), ("reject", "rejected"), ("tolak", "rejected"), ("defer", "deferred"), ("tunda", "deferred")):
        if trigger in lowered:
            _trace_route("action-loop", text, f"phase5_action_loop:transition:{trigger}")
            ordinal_match = re.search(r"nomor\s+(\d+)", lowered)
            ordinal = int(ordinal_match.group(1)) if ordinal_match else None
            action = resolve_action_reference(reference=lowered, ordinal=ordinal)
            if not action:
                await update.message.reply_text("Referensi belum jelas. Maksud Anda nomor berapa dari daftar terakhir?")
                return True
            proposal = mcp_server.tool_paos_approval_propose(
                source="telegram/action-loop",
                requested_by="user",
                proposed_operation=f"set action {action.action_id} -> {target_transition}",
                operation_type="local_action_state_update",
                evidence_refs=["action-loop", f"action_id:{action.action_id}"],
                payload_preview={"action_id": action.action_id, "transition": target_transition, "note": lowered},
            )
            approval = proposal.get("approval") or {}
            await update.message.reply_text(
                (
                    f"Perubahan action dibuat sebagai approval: {approval.get('approval_id')} [{approval.get('status')}].\n"
                    f"Risk: {approval.get('risk_level')} | Operation: {approval.get('operation_type')}.\n"
                    "Approve tidak auto-apply. Gunakan apply approval explicit.\n"
                    "No external action was applied."
                )[:3900]
            )
            return True
    return False


async def _handle_approval(update, text: str) -> bool:
    lowered = _normalize_text(text)
    if "tampilkan approval pending" in lowered or "list approval" in lowered:
        payload = mcp_server.tool_paos_approval_list(status="pending", limit=10)
        items = payload.get("items") or []
        if not items:
            await update.message.reply_text("Tidak ada approval pending. No external action was applied.")
            return True
        lines = ["Approval pending:"]
        for idx, item in enumerate(items, start=1):
            lines.append(_format_approval_line(item, idx))
        lines.append("Gunakan: approve/reject/cancel/apply approval nomor N.")
        lines.append("No external action was applied.")
        await update.message.reply_text("\n".join(lines)[:3900])
        return True

    if "apa yang akan di-apply" in lowered:
        aid = _resolve_approval_id_from_text(lowered)
        if not aid:
            await update.message.reply_text("Approval belum jelas. Sebut: apply approval nomor 1.")
            return True
        payload = mcp_server.tool_paos_approval_get(approval_id=aid)
        if not payload.get("ok"):
            await update.message.reply_text("Approval tidak ditemukan. No external action was applied.")
            return True
        item = payload.get("approval") or {}
        preview = item.get("payload_preview") if isinstance(item.get("payload_preview"), dict) else {}
        lines = [
            "Preview apply:",
            f"- approval_id: {item.get('approval_id')}",
            f"- status: {item.get('status')}",
            f"- operation: {item.get('operation_type')}",
            f"- risk: {item.get('risk_level')}",
            f"- evidence: {', '.join(item.get('evidence_refs') or ['-'])}",
            f"- payload_preview: {str(preview)[:220]}",
            f"- mode: {preview.get('mode') or '-'}",
            "Belum dieksekusi. Gunakan explicit: apply approval ...",
            "No external action was applied.",
        ]
        await update.message.reply_text("\n".join(lines)[:3900])
        return True

    decision = None
    if "approve" in lowered:
        decision = "approve"
    elif "reject approval" in lowered:
        decision = "reject"
    elif "cancel approval" in lowered:
        decision = "cancel"
    if decision:
        aid = _resolve_approval_id_from_text(lowered)
        if not aid:
            await update.message.reply_text("Approval belum jelas. Sebut nomor approval dari daftar pending.")
            return True
        payload = mcp_server.tool_paos_approval_decide(approval_id=aid, decision=decision, actor="telegram")
        if not payload.get("ok"):
            await update.message.reply_text("Decision gagal diproses. No external action was applied.")
            return True
        item = payload.get("approval") or {}
        await update.message.reply_text(
            (
                f"Approval {item.get('approval_id')} -> {item.get('status')}.\n"
                "Approve hanya mengubah status, belum apply.\n"
                f"Mode: {((item.get('payload_preview') or {}).get('mode') or '-')}\n"
                "Gunakan explicit: apply approval ...\n"
                "No external action was applied."
            )[:3900]
        )
        return True

    if "apply approval" in lowered:
        aid = _resolve_approval_id_from_text(lowered)
        if not aid:
            await update.message.reply_text("Approval belum jelas. Sebut nomor approval dari daftar pending/approved.")
            return True
        payload = mcp_server.tool_paos_approval_apply(approval_id=aid, actor="telegram")
        if not payload.get("ok"):
            await update.message.reply_text(
                (f"Apply ditolak/gagal: {', '.join(payload.get('errors') or ['unknown'])}.\nNo external action was applied.")[:3900]
            )
            return True
        item = payload.get("approval") or {}
        await update.message.reply_text(
            (
                f"Apply selesai untuk {item.get('approval_id')} dengan status {item.get('status')}.\n"
                f"Operation: {item.get('operation_type')} ({((item.get('payload_preview') or {}).get('mode') or 'local-only')}).\n"
                "No external action was applied."
            )[:3900]
        )
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
    if any(k in lowered for k in ("insight ai yang penting", "insight hari ini", "insight dari github", "insight dari threads", "insight terbaru apa", "insight terbaru")):
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
        await update.message.reply_text((("\n".join(lines)) + "\nNo external action was applied.")[:3900])
        return True
    if any(k in lowered for k in ("source paling berguna", "rekomendasi source", "keyword yang perlu saya ubah")):
        _trace_route("source-intel", text, "phase6_source_recommendation")
        payload = get_source_recommendation(category="ai")
        msg = "Rekomendasi source/keyword:\n" + "\n".join(f"- {x}" for x in (payload.get("items") or [])[:5])
        await update.message.reply_text(msg[:3900])
        return True
    if any(k in lowered for k in ("buat action dari insight terbaru", "source intelligence terbaru", "jadikan insight terbaru sebagai proposed action", "buat action dari insight ini")):
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
    if _is_blocked_unsafe_operation_request(text):
        _trace_route("free-text", text, "blocked_unsafe_operation_request")
        proposal = mcp_server.tool_paos_approval_propose(
            source="telegram/free-text",
            requested_by="user",
            proposed_operation=text,
            operation_type="future_external_write",
            evidence_refs=["telegram/free-text"],
            payload_preview={"request": text[:240], "external_operation": "github_pr_create" if "github" in _normalize_text(text) else "public_api_publish"},
        )
        approval = proposal.get("approval") or {}
        preview = approval.get("payload_preview") if isinstance(approval.get("payload_preview"), dict) else {}
        await update.message.reply_text(
            (
                "Permintaan diblokir oleh safety policy v1.5a.\n"
                f"- approval_id: {approval.get('approval_id')}\n"
                f"- status: {approval.get('status')}\n"
                f"- mode: {preview.get('mode') or 'blocked'}\n"
                "- reason: external/unsafe mutation tidak diizinkan pada controlled execution foundation.\n"
                "No external action was applied."
            )[:3900]
        )
        return
    if _is_approval_text(text):
        _trace_route("free-text", text, "phase10_approval_rail")
        if await _handle_approval(update, text):
            return
    if _is_action_loop_text(text):
        _trace_route("free-text", text, "phase5_action_loop:intent_match")
        if await _handle_action_loop(update, text):
            return
    if await _handle_memory_intent(update, text):
        _trace_route("free-text", text, "phase7_memory_intent")
        return
    if _is_agent_orchestration_text(text):
        _trace_route("free-text", text, "phase9_agent_orchestration")
        if await _handle_agent_orchestration(update, text):
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

    if _is_daily_operating_text(text) or _is_weekly_review_text(text):
        _trace_route("free-text", text, "daily_ux_fallback_after_hermes")
        if await _handle_daily_operating(update, text):
            return

    if await _handle_source_intelligence(update, text):
        _trace_route("free-text", text, "phase6_source_intelligence_fallback_after_hermes")
        return

    if not hermes_attempted:
        _trace_route("free-text", text, "unknown_after_hermes_unavailable")
    else:
        _trace_route("free-text", text, "unknown_after_hermes_attempt")

    await update.message.reply_text(_render_unknown_message())
