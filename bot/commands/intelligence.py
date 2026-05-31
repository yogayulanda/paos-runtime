import json
import subprocess
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup

from context.loader import load_env


CACHE_KEY = "daily_dashboard_payload_cache"
MAX_TELEGRAM = 3900

INSIGHT_SECTION_KEYS = [
    ("prioritas", "Prioritas", "Prioritas Hari Ini"),
    ("penting", "Yang Penting", "Yang Lagi Penting"),
    ("pelajari", "Pelajari", "Yang Layak Dipelajari"),
    ("coba", "Coba", "Yang Layak Dicoba"),
]


def _runtime_path():
    env = load_env()
    return Path(env.get("PAOS_RUNTIME_PATH", "/home/ubuntu/paos/paos-runtime"))


def _today_str():
    return datetime.now().astimezone().date().isoformat()


def _compact(value):
    return " ".join(str(value or "").split())


def _read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _status_line(label, payload):
    if not payload:
        return f"{label}: belum ada status."
    status = payload.get("status", "unknown")
    category = payload.get("category") or "-"
    finished = payload.get("finished_at") or "-"
    output = (
        payload.get("markdown_path")
        or payload.get("digest_path")
        or payload.get("output_path")
        or payload.get("jsonl_path")
        or "-"
    )
    return (
        f"{label}: {status}\n"
        f"- category: {category}\n"
        f"- finished_at: {finished}\n"
        f"- output: {output}"
    )


def _shorten_sentence_boundary(text, limit=320):
    value = _compact(text)
    if len(value) <= limit:
        return value

    cut = value[:limit]
    for idx in range(len(cut) - 1, -1, -1):
        if cut[idx] in ".!?":
            return cut[: idx + 1].strip()

    if " " in cut:
        return cut.rsplit(" ", 1)[0].strip()
    return cut.strip()


def _resolve_latest_markdown_path(root_dir, category="ai", preferred_path=None):
    if preferred_path:
        preferred = Path(preferred_path)
        if preferred.exists() and preferred.is_file():
            return preferred

    today_path = root_dir / _today_str() / f"{category}.md"
    if today_path.exists():
        return today_path

    candidates = sorted(
        [path for path in root_dir.glob(f"*/{category}.md") if path.is_file()],
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _parse_digest_markdown(markdown_text):
    lines = markdown_text.splitlines()
    executive_summary = ""
    key_signals = []

    current = None
    in_exec = False
    in_key_signals = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped == "## Executive Summary":
            in_exec = True
            in_key_signals = False
            continue

        if stripped == "## Key Signals":
            in_exec = False
            in_key_signals = True
            continue

        if stripped.startswith("## ") and stripped not in {"## Executive Summary", "## Key Signals"}:
            in_exec = False
            in_key_signals = False

        if in_exec and stripped and not stripped.startswith(("Generated At:", "Category:", "Date:")):
            executive_summary = stripped
            in_exec = False
            continue

        if not in_key_signals:
            continue

        if stripped.startswith("### "):
            if current:
                key_signals.append(current)
            number_and_title = stripped[4:].strip()
            number = None
            title = number_and_title
            if ". " in number_and_title:
                prefix, suffix = number_and_title.split(". ", 1)
                if prefix.isdigit():
                    number = int(prefix)
                    title = suffix
            current = {
                "number": number,
                "title": _compact(title),
                "theme": "",
                "summary": "",
                "why_it_matters": "",
                "sources": [],
            }
            continue

        if not current or not stripped:
            continue

        if stripped.startswith("Theme:"):
            current["theme"] = _compact(stripped.split(":", 1)[1])
        elif stripped.startswith("Summary:"):
            current["summary"] = _compact(stripped.split(":", 1)[1])
        elif stripped.startswith("Why it matters:"):
            current["why_it_matters"] = _compact(stripped.split(":", 1)[1])
        elif stripped.startswith("* "):
            current["sources"].append(_compact(stripped.lstrip("* ")))

    if current:
        key_signals.append(current)

    key_signals = [item for item in key_signals if item.get("title")]
    for idx, item in enumerate(key_signals, start=1):
        if not item.get("number"):
            item["number"] = idx

    return {
        "executive_summary": executive_summary,
        "key_signals": key_signals,
    }


def _extract_insight_section(lines, section_title):
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and section_title in line:
            start = i + 1
            break
    if start is None:
        return []

    out = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip() == "━━━━━━━━━━":
            break
        out.append(line.rstrip())
    return out


def _parse_prioritas_items(section_lines):
    items = []
    current = None
    for raw in section_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if ". " in stripped[:4]:
            prefix, rest = stripped.split(". ", 1)
            if prefix.isdigit():
                if current:
                    items.append(current)
                current = {"number": int(prefix), "title": _compact(rest), "lines": []}
                continue
        if current:
            current["lines"].append(_compact(stripped))
    if current:
        items.append(current)
    return items


def _parse_insight_markdown(markdown_text):
    lines = markdown_text.splitlines()

    prioritas_lines = _extract_insight_section(lines, "Prioritas Hari Ini")
    penting_lines = _extract_insight_section(lines, "Yang Lagi Penting")
    pelajari_lines = _extract_insight_section(lines, "Yang Layak Dipelajari")
    coba_lines = _extract_insight_section(lines, "Yang Layak Dicoba")
    post_lines = _extract_insight_section(lines, "Siap Diposting")
    ringkasan_lines = _extract_insight_section(lines, "Ringkasan")

    prioritas_items = _parse_prioritas_items(prioritas_lines)

    sections = {
        "prioritas": {
            "title": "Prioritas Hari Ini",
            "exists": bool(prioritas_lines),
            "lines": prioritas_lines,
            "items": prioritas_items,
        },
        "penting": {
            "title": "Yang Lagi Penting",
            "exists": bool(penting_lines),
            "lines": penting_lines,
            "items": [],
        },
        "pelajari": {
            "title": "Yang Layak Dipelajari",
            "exists": bool(pelajari_lines),
            "lines": pelajari_lines,
            "items": [],
        },
        "coba": {
            "title": "Yang Layak Dicoba",
            "exists": bool(coba_lines),
            "lines": coba_lines,
            "items": [],
        },
        "post": {
            "title": "Siap Diposting",
            "exists": bool(post_lines),
            "lines": post_lines,
            "items": [],
        },
        "ringkasan": {
            "title": "Ringkasan",
            "exists": bool(ringkasan_lines),
            "lines": ringkasan_lines,
            "items": [],
        },
    }

    return sections


def _format_sources_compact(source_lines, max_items=5):
    if not source_lines:
        return "- Tidak ada sumber"
    formatted = []
    for raw in source_lines[:max_items]:
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) >= 4:
            platform = parts[0]
            source_name = parts[2]
            url = parts[3]
            formatted.append(f"- {source_name} ({platform}): {url}")
        else:
            formatted.append(f"- {raw}")
    return "\n".join(formatted)


def _render_insight_preview(sections):
    lines = ["🎯 Insight Hari Ini", ""]

    prioritas = sections["prioritas"]
    if prioritas["exists"] and prioritas["items"]:
        lines.extend(["🔥 Prioritas Hari Ini", ""])
        for item in prioritas["items"][:3]:
            lines.append(f"{item['number']}. {item['title']}")
            preview = item.get("lines", [])[:3]
            for segment in preview:
                lines.append(segment)
            lines.append("")

    penting = sections["penting"]
    if penting["exists"]:
        lines.append("🔥 Yang Lagi Penting")
        lines.append("")
        shown = 0
        for line in penting["lines"]:
            if not line.strip():
                continue
            lines.append(line)
            shown += 1
            if shown >= 3:
                break
        lines.append("")

    post = sections["post"]
    if post["exists"]:
        lines.append("✍️ Siap Diposting")
        lines.append("")
        shown = 0
        for line in post["lines"]:
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            lines.append(line)
            shown += 1
            if shown >= 8:
                break
        lines.append("")

    lines.append("Pilih detail di bawah.")
    return "\n".join(lines).strip()


def _render_section_detail(sections, key):
    section = sections.get(key)
    if not section or not section.get("exists"):
        return "Section tidak tersedia."

    header = section.get("title")
    body = "\n".join(section.get("lines") or []).strip()
    if not body:
        body = "Tidak ada konten."

    emoji = {
        "prioritas": "🔥",
        "penting": "🔥",
        "pelajari": "🧠",
        "coba": "🛠",
    }.get(key, "📝")

    return f"{emoji} {header}\n\n{body}"[:MAX_TELEGRAM]


def _build_dashboard_payload(digest_text, insight_text):
    digest = _parse_digest_markdown(digest_text)
    sections = _parse_insight_markdown(insight_text)

    exec_summary = digest.get("executive_summary") or "Tidak ada executive summary."
    key_signals = digest.get("key_signals") or []

    signal_count = 5
    summary_limit = 420

    def compose_dashboard(sig_count, sum_limit):
        summary = _shorten_sentence_boundary(exec_summary, sum_limit)
        signal_titles = [
            f"{idx}. {_compact(item['title'])}"
            for idx, item in enumerate(key_signals[:sig_count], start=1)
        ]
        insight_preview = _render_insight_preview(sections)
        message = "\n".join(
            [
                "📰 Ringkasan Harian AI",
                "",
                "Summary:",
                summary,
                "",
                "Key Signals:",
                *(signal_titles or ["- Tidak ada key signal"]),
                "",
                "━━━━━━━━━━",
                "",
                insight_preview,
            ]
        ).strip()
        return message

    dashboard_message = compose_dashboard(signal_count, summary_limit)

    if len(dashboard_message) > MAX_TELEGRAM:
        dashboard_message = compose_dashboard(3, 260)

    if len(dashboard_message) > MAX_TELEGRAM:
        trimmed_sections = dict(sections)
        for optional_key in ("pelajari", "coba"):
            if trimmed_sections[optional_key]["exists"]:
                trimmed_sections[optional_key] = {
                    **trimmed_sections[optional_key],
                    "lines": ["Lihat detail via tombol."],
                }
        sections_for_fallback = trimmed_sections
        preview = _render_insight_preview(sections_for_fallback)
        dashboard_message = "\n".join(
            [
                "📰 Ringkasan Harian AI",
                "",
                "Summary:",
                _shorten_sentence_boundary(exec_summary, 220),
                "",
                "Key Signals:",
                *[
                    f"{idx}. {_compact(item['title'])}"
                    for idx, item in enumerate(key_signals[:3], start=1)
                ],
                "",
                "━━━━━━━━━━",
                "",
                preview,
            ]
        ).strip()

    signal_details = {}
    for idx, signal in enumerate(key_signals[:5], start=1):
        signal_details[idx] = (
            f"📰 Signal {idx} — {signal['title']}\n\n"
            f"Theme:\n{signal.get('theme') or '-'}\n\n"
            f"Summary:\n{signal.get('summary') or '-'}\n\n"
            f"Why it matters:\n{signal.get('why_it_matters') or '-'}\n\n"
            f"Sources:\n{_format_sources_compact(signal.get('sources') or [])}"
        )[:MAX_TELEGRAM]

    available_sections = [
        key for key, _, _ in INSIGHT_SECTION_KEYS if sections.get(key, {}).get("exists")
    ]

    return {
        "digest_summary": _shorten_sentence_boundary(exec_summary, 420),
        "key_signals": key_signals[:5],
        "insight_sections": sections,
        "insight_priorities": sections.get("prioritas", {}).get("items", []),
        "insight_post_section": _render_section_detail(sections, "post").replace("📝 ", "✍️ "),
        "dashboard_message": dashboard_message[:MAX_TELEGRAM],
        "signal_details": signal_details,
        "available_section_keys": available_sections,
    }


def resolve_daily_dashboard(runtime_path, category="ai", preferred_digest_path=None, preferred_insight_path=None):
    digest_root = runtime_path / "intelligence" / "digests"
    insight_root = runtime_path / "intelligence" / "insights"

    digest_path = _resolve_latest_markdown_path(
        root_dir=digest_root,
        category=category,
        preferred_path=preferred_digest_path,
    )
    insight_path = _resolve_latest_markdown_path(
        root_dir=insight_root,
        category=category,
        preferred_path=preferred_insight_path,
    )

    if not digest_path or not insight_path:
        return None

    digest_text = digest_path.read_text(encoding="utf-8")
    insight_text = insight_path.read_text(encoding="utf-8")
    payload = _build_dashboard_payload(digest_text=digest_text, insight_text=insight_text)

    return {
        "date": insight_path.parent.name,
        "category": category,
        "digest_path": str(digest_path),
        "insight_path": str(insight_path),
        "payload": payload,
    }


def _build_keyboard(payload):
    rows = []

    signal_buttons = [
        InlineKeyboardButton(f"Signal {i}", callback_data=f"digest_signal:{i}")
        for i in range(1, min(5, len(payload.get("key_signals", []))) + 1)
    ]
    if signal_buttons:
        rows.append(signal_buttons[:3])
    if len(signal_buttons) > 3:
        rows.append(signal_buttons[3:5])

    section_keys = set(payload.get("available_section_keys") or [])
    row3 = []
    if "prioritas" in section_keys:
        row3.append(InlineKeyboardButton("Prioritas", callback_data="insight_section:prioritas"))
    if "penting" in section_keys:
        row3.append(InlineKeyboardButton("Yang Penting", callback_data="insight_section:penting"))
    if row3:
        rows.append(row3)

    row4 = []
    if "pelajari" in section_keys:
        row4.append(InlineKeyboardButton("Pelajari", callback_data="insight_section:pelajari"))
    if "coba" in section_keys:
        row4.append(InlineKeyboardButton("Coba", callback_data="insight_section:coba"))
    if row4:
        rows.append(row4)

    if payload.get("insight_sections", {}).get("post", {}).get("exists"):
        rows.append([InlineKeyboardButton("Siap Diposting", callback_data="insight_post")])

    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("Siap Diposting", callback_data="insight_post")]])


def _cache_dashboard(context, chat_id, resolved):
    cache = context.bot_data.setdefault(CACHE_KEY, {})
    cache[str(chat_id)] = {
        "date": resolved["date"],
        "category": resolved["category"],
        "digest_path": resolved["digest_path"],
        "insight_path": resolved["insight_path"],
        "payload": resolved["payload"],
    }


def _get_cached_dashboard(context, chat_id):
    return (context.bot_data.get(CACHE_KEY) or {}).get(str(chat_id))


def _step_status_text(step_results):
    lines = ["⏳ Update berjalan..."]
    labels = {
        "rss": "RSS",
        "candidate": "Candidate",
        "signal": "Signal",
        "digest": "Digest",
        "insight": "Insight",
    }
    for step in step_results:
        label = labels.get(step.get("step"), step.get("step", "step"))
        mark = "✅" if step.get("status") == "success" else "❌"
        lines.append(f"{mark} {label}")
    return "\n".join(lines)


def _run_update_pipeline(runtime_path, category="ai"):
    command = [
        str(runtime_path / "venv" / "bin" / "python"),
        str(runtime_path / "runtime" / "intelligence" / "jobs" / "run_daily_intelligence.py"),
        "--category",
        category,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    payload = None
    stdout = (completed.stdout or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
        except Exception:
            payload = None
    return completed, payload


async def handle_status(update):
    runtime_path = _runtime_path()
    digest_status = _read_json(runtime_path / ".runtime" / "runs" / "digest" / "latest.json")
    insight_status = _read_json(runtime_path / ".runtime" / "runs" / "insights" / "latest.json")
    message = "\n\n".join(
        [
            "Status pipeline terakhir:",
            _status_line("Digest", digest_status),
            _status_line("Insight", insight_status),
        ]
    )
    await update.message.reply_text(message[:MAX_TELEGRAM])


async def handle_insight(update, context):
    runtime_path = _runtime_path()
    resolved = resolve_daily_dashboard(runtime_path=runtime_path, category="ai")
    if not resolved:
        await update.message.reply_text("Belum ada dashboard harian. Jalankan /update dulu.")
        return

    _cache_dashboard(context, update.effective_chat.id, resolved)
    await update.message.reply_text(
        resolved["payload"]["dashboard_message"],
        reply_markup=_build_keyboard(resolved["payload"]),
    )


async def handle_update(update, context):
    runtime_path = _runtime_path()
    progress_message = await update.message.reply_text(
        "⏳ Update dimulai. Aku ambil RSS terbaru dan generate insight baru."
    )

    completed, run_payload = _run_update_pipeline(runtime_path, category="ai")
    step_text = _step_status_text((run_payload or {}).get("steps") or [])

    try:
        await progress_message.edit_text(step_text[:MAX_TELEGRAM])
    except Exception:
        await update.message.reply_text(step_text[:MAX_TELEGRAM])

    if completed.returncode != 0:
        await update.message.reply_text("Update gagal. Cek /status untuk detail terbaru.")
        return

    resolved = resolve_daily_dashboard(
        runtime_path=runtime_path,
        category="ai",
        preferred_digest_path=(run_payload or {}).get("digest_path"),
        preferred_insight_path=(run_payload or {}).get("insight_path"),
    )
    if not resolved:
        await update.message.reply_text("Update selesai, tapi dashboard belum tersedia. Coba /insight.")
        return

    _cache_dashboard(context, update.effective_chat.id, resolved)
    await update.message.reply_text(
        resolved["payload"]["dashboard_message"],
        reply_markup=_build_keyboard(resolved["payload"]),
    )


async def handle_insight_callback(update, context):
    query = update.callback_query
    await query.answer()

    runtime_path = _runtime_path()
    cached = _get_cached_dashboard(context, update.effective_chat.id)

    payload = None
    if cached:
        digest_path = Path(cached.get("digest_path", ""))
        insight_path = Path(cached.get("insight_path", ""))
        if digest_path.exists() and insight_path.exists():
            payload = cached.get("payload")

    if not payload:
        resolved = resolve_daily_dashboard(runtime_path=runtime_path, category="ai")
        if not resolved:
            await query.message.reply_text("Dashboard belum tersedia. Jalankan /update dulu.")
            return
        _cache_dashboard(context, update.effective_chat.id, resolved)
        payload = resolved["payload"]

    callback_data = _compact(query.data)

    if callback_data.startswith("digest_signal:"):
        try:
            idx = int(callback_data.split(":", 1)[1])
        except Exception:
            idx = 0
        detail = (payload.get("signal_details") or {}).get(idx)
        await query.message.reply_text(detail or "Detail signal tidak tersedia.")
        return

    if callback_data.startswith("insight_section:"):
        key = callback_data.split(":", 1)[1]
        section_text = _render_section_detail(payload.get("insight_sections") or {}, key)
        await query.message.reply_text(section_text)
        return

    if callback_data.startswith("insight_detail:"):
        # Backward compatibility
        try:
            idx = int(callback_data.split(":", 1)[1])
        except Exception:
            idx = 0
        items = (payload.get("insight_sections") or {}).get("prioritas", {}).get("items", [])
        item = next((i for i in items if i.get("number") == idx), None)
        if not item:
            await query.message.reply_text("Detail insight tidak tersedia.")
            return
        full_content = "\n".join(item.get("lines") or [])
        await query.message.reply_text(f"🔥 Insight {idx} — {item['title']}\n\n{full_content}"[:MAX_TELEGRAM])
        return

    if callback_data == "insight_post":
        section_text = _render_section_detail(payload.get("insight_sections") or {}, "post")
        section_text = section_text.replace("📝 Siap Diposting", "✍️ Siap Diposting")
        await query.message.reply_text(section_text)
        return

    await query.message.reply_text("Aksi tidak dikenali.")
