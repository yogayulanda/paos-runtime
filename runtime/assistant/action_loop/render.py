from __future__ import annotations

from .models import ActionLoopResult, ActionRecord

MAX_TELEGRAM = 3900


def _short(text: str) -> str:
    return " ".join(str(text or "").split())


def render_action_list(actions: list[ActionRecord], title: str = "Action Inbox") -> str:
    if not actions:
        return "Action Inbox kosong. No external action was applied."
    lines = [title]
    for idx, item in enumerate(actions, start=1):
        lines.append(f"{idx}. {_short(item.title)} [{item.state}] ({item.action_id})")
    lines.extend([
        "",
        "Balas natural: accept / reject / defer / lihat detail / pilih nomor 1.",
        "No external action was applied.",
    ])
    return "\n".join(lines)[:MAX_TELEGRAM]


def render_action_detail(action: ActionRecord) -> str:
    lines = [
        f"Action Detail: {_short(action.title)}",
        f"ID: {action.action_id}",
        f"State: {action.state}",
        "",
        _short(action.summary),
        "",
        "Steps:",
    ]
    lines.extend([f"{idx}. {_short(step)}" for idx, step in enumerate(action.steps[:6], start=1)])
    lines.append("")
    lines.append("No external action was applied.")
    return "\n".join(lines)[:MAX_TELEGRAM]


def render_action_update_result(result: ActionLoopResult) -> str:
    if not result.ok or not result.action:
        return f"{result.message} No external action was applied."
    return (
        f"Action '{_short(result.action.title)}' -> {result.action.state}.\n"
        "No external action was applied."
    )


def render_daily_action_result(result: ActionLoopResult) -> str:
    if not result.ok or not result.action:
        return f"Gagal membuat daily action. {result.message}"
    return (
        f"Daily action dibuat: {_short(result.action.title)} ({result.action.action_id})\n"
        "Balas: accept / reject / defer / lihat detail.\n"
        "No external action was applied."
    )


def render_conversational_next_steps(action: ActionRecord | None) -> str:
    if action:
        return (
            f"Fokus saat ini: {_short(action.title)} ({action.state}).\n"
            "Jika ingin ubah status, balas natural: accept/reject/defer yang tadi.\n"
            "No external action was applied."
        )
    return "Belum ada fokus accepted. Saya bisa tampilkan action pending dulu. No external action was applied."
