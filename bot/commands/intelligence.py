import json
import subprocess
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup

from context.loader import load_env


CACHE_KEY = "daily_dashboard_payload_cache"
MAX_TELEGRAM = 3900

PAOS_SECTIONS = [
    ("Ringkasan Hari Ini", "summary"),
    ("Yang Perlu Kamu Lakukan", "actions"),
    ("Yang Lagi Penting", "signals"),
    ("Peluang untuk Kamu", "opportunities"),
    ("Bahan Konten & Branding", "content"),
    ("Yang Layak Dipelajari", "learning"),
    ("Yang Layak Dicoba", "experiments"),
    ("Radar GitHub & Tools", "github"),
    ("Radar LinkedIn & Networking", "linkedin"),
    ("Radar Karier & Lowongan", "jobs"),
    ("Update Konteks Pribadi", "context"),
    ("Pantauan", "watchlist"),
    ("Source Coverage", "source_coverage"),
]

SECTION_META = {
    "actions": ("✅", "Yang Perlu Kamu Lakukan", "Apa yang perlu dilakukan", True),
    "signals": ("🔥", "Yang Lagi Penting", "Kenapa ini penting", True),
    "opportunities": ("🎯", "Peluang untuk Kamu", "Peluang", True),
    "content": ("✍️", "Bahan Konten & Branding", "Bahan post", True),
    "learning": ("📚", "Yang Layak Dipelajari", "Yang perlu dipelajari", True),
    "experiments": ("🧪", "Yang Layak Dicoba", "Yang bisa dicoba", True),
    "github": ("🛠", "GitHub & Tools", "GitHub & Tools", True),
    "linkedin": ("💼", "LinkedIn & Networking", "LinkedIn", True),
    "jobs": ("🚀", "Karier & Lowongan", "Lowongan", True),
    "context": ("🧠", "Update Konteks Pribadi", "Update konteks", True),
    "watchlist": ("👀", "Pantauan", "Pantauan", True),
}

OLD_TO_NEW_SECTION = {
    "prioritas": "actions",
    "penting": "signals",
    "pelajari": "learning",
    "coba": "experiments",
    "post": "content",
}


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


def _parse_iso_timestamp(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _stale_insight_note(digest_status, insight_status):
    if not digest_status or not insight_status:
        return None
    digest_finished = _parse_iso_timestamp(digest_status.get("finished_at"))
    insight_finished = _parse_iso_timestamp(insight_status.get("finished_at"))
    if not digest_finished or not insight_finished:
        return None
    if insight_finished < digest_finished:
        return (
            "Insight status terlihat stale:\n"
            f"- digest finished_at: {digest_status.get('finished_at')}\n"
            f"- insight finished_at: {insight_status.get('finished_at')}"
        )
    return None


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


def parse_markdown_sections(text):
    sections = {}
    current_label = None
    current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_label is not None:
                sections[current_label] = "\n".join(current_lines).strip()
            current_label = line[3:].strip()
            current_lines = []
            continue
        if current_label is not None:
            current_lines.append(line)

    if current_label is not None:
        sections[current_label] = "\n".join(current_lines).strip()
    return sections


def _split_sentences(text):
    value = _compact(text)
    if not value:
        return []
    parts = []
    chunk = ""
    for char in value:
        chunk += char
        if char in ".!?":
            parts.append(chunk.strip())
            chunk = ""
    if chunk.strip():
        parts.append(chunk.strip())
    return parts


def _extract_summary_preview(summary_body):
    lines = []
    for raw_line in summary_body.splitlines():
        stripped = _compact(raw_line)
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        stripped = stripped.lstrip("- ").strip()
        if stripped:
            lines.append(stripped)
    if lines:
        return lines[:5]
    return _split_sentences(summary_body)[:4]


def _extract_marked_titles(body):
    titles = []
    seen = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            title = stripped[4:].strip()
            if ". " in title[:4]:
                prefix, rest = title.split(". ", 1)
                if prefix.isdigit():
                    title = rest.strip()
            key = _compact(title).lower()
            if key and key not in seen:
                seen.add(key)
                titles.append(title)
    return titles


def _extract_opportunity_preview(body):
    previews = {"Project": "Belum ada peluang project kuat hari ini.", "Konten": "Belum ada peluang konten kuat hari ini.", "Karier": "Belum ada peluang karier kuat hari ini."}
    for title in _extract_marked_titles(body):
        if ":" not in title:
            continue
        raw_type, raw_value = [part.strip() for part in title.split(":", 1)]
        lowered = raw_type.lower()
        if lowered in {"project", "konten", "karier", "career", "job"}:
            key = "Karier" if lowered in {"career", "job"} else raw_type.title()
            previews[key] = raw_value or previews[key]
    return previews


def _extract_content_preview(body):
    for title in _extract_marked_titles(body):
        if title.lower().startswith("angle:"):
            return title.split(":", 1)[1].strip()
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first_line or "Belum ada bahan post yang cukup kuat hari ini."


def _has_content_material(content_body):
    body = _compact(content_body)
    if not body:
        return False
    lowered = body.lower()
    return "belum ada bahan post yang cukup kuat hari ini." not in lowered


def _derive_content_opportunity_from_material(content_body):
    body = _compact(content_body)
    if not body:
        return ""

    angle = ""
    for title in _extract_marked_titles(content_body):
        if ":" not in title:
            continue
        key, value = [part.strip() for part in title.split(":", 1)]
        if _compact(key).lower() in {"angle", "hook", "opini", "tema"} and _compact(value):
            angle = _compact(value)
            break

    for line in content_body.splitlines():
        if angle:
            break
        stripped = _compact(line)
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("angle:"):
            angle = _compact(stripped.split(":", 1)[1])
            break
        if stripped.startswith("- "):
            stripped = _compact(stripped[2:])
            if ":" in stripped:
                left, right = stripped.split(":", 1)
                if _compact(left).lower() in {"angle", "hook", "opini", "tema"} and _compact(right):
                    angle = _compact(right)
                    break
        angle = stripped
        break

    angle = angle.strip(" '\"“”‘’")
    if not angle or angle.lower() == "belum ada bahan post yang cukup kuat hari ini.":
        return ""

    if len(angle) > 96:
        angle = f"{angle[:93].rstrip()}..."
    return f"Post pendek tentang {angle}."


def _parse_source_coverage_buckets(source_coverage_body):
    buckets = {"active": set(), "inactive": set(), "missing": set()}
    for line in source_coverage_body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        key = _compact(key).lower()
        names = [_compact(part) for part in value.split(",") if _compact(part) and _compact(part) != "-"]
        if key in buckets:
            buckets[key].update(names)
    return buckets


def _family_status(name, buckets):
    if name in buckets["active"]:
        return "aktif"
    if name in buckets["inactive"]:
        return "belum aktif"
    if name in buckets["missing"]:
        return "belum aktif"
    return "belum aktif"


def _extract_source_status(source_coverage_body, section_body, inactive_phrase, empty_phrase):
    coverage_lines = {}
    for line in source_coverage_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ":" in stripped:
            key, value = stripped[2:].split(":", 1)
            coverage_lines[_compact(key).lower()] = _compact(value)

    active_blob = coverage_lines.get("active", "").lower()
    inactive_blob = coverage_lines.get("inactive", "").lower()

    if section_body and inactive_phrase.lower() in section_body.lower():
        return "belum aktif"
    if section_body and empty_phrase.lower() in section_body.lower():
        return "aktif"
    if active_blob:
        if "threads/rss" in active_blob:
            threads_status = "aktif"
        else:
            threads_status = None
    else:
        threads_status = None

    if "github" in inactive_blob and "github" in inactive_phrase.lower():
        return "belum aktif"
    if "linkedin" in inactive_blob and "linkedin" in inactive_phrase.lower():
        return "belum aktif"
    if "jobs" in inactive_blob and "job" in inactive_phrase.lower():
        return "belum aktif"
    return "aktif" if section_body else "belum aktif"


def _trim_preview_lines(lines, limit):
    result = []
    for line in lines:
        stripped = _compact(line)
        if stripped:
            result.append(stripped)
        if len(result) >= limit:
            break
    return result


def build_paos_dashboard_payload(path, category="ai", date=None):
    markdown_text = Path(path).read_text(encoding="utf-8")
    sections = parse_markdown_sections(markdown_text)
    section_map = {key: sections.get(label, "") for label, key in PAOS_SECTIONS}
    # Backward-compatible heading alias
    if not _compact(section_map.get("content")):
        section_map["content"] = sections.get("Bahan Konten", "")

    summary_body = section_map.get("summary", "")
    summary_preview = _extract_summary_preview(summary_body) or ["Belum ada ringkasan kuat hari ini."]

    actions_body = section_map.get("actions", "")
    signals_body = section_map.get("signals", "")
    opportunities_body = section_map.get("opportunities", "")
    content_body = section_map.get("content", "")
    learning_body = section_map.get("learning", "")
    experiments_body = section_map.get("experiments", "")
    context_body = section_map.get("context", "")
    watchlist_body = section_map.get("watchlist", "")
    github_body = section_map.get("github", "")
    linkedin_body = section_map.get("linkedin", "")
    jobs_body = section_map.get("jobs", "")
    source_coverage_body = section_map.get("source_coverage", "")

    action_titles = _extract_marked_titles(actions_body)[:3]
    signal_titles = _extract_marked_titles(signals_body)[:3]
    opportunity_preview = _extract_opportunity_preview(opportunities_body)
    content_preview = _extract_content_preview(content_body)
    content_exists = _has_content_material(content_body)
    konten_preview = _compact(opportunity_preview.get("Konten", ""))
    konten_preview_lower = konten_preview.lower()
    konten_is_empty_or_generic = (
        not konten_preview
        or "belum ada peluang konten kuat hari ini." in konten_preview_lower
        or "ada bahan ringan untuk post pendek" in konten_preview_lower
    )
    if content_exists and konten_is_empty_or_generic:
        derived_opportunity = _derive_content_opportunity_from_material(content_body)
        opportunity_preview["Konten"] = derived_opportunity or "Ada bahan post pendek yang bisa dipakai hari ini."
    if not content_exists and "Konten" not in opportunity_preview:
        opportunity_preview["Konten"] = "Belum ada peluang konten kuat hari ini."

    coverage_buckets = _parse_source_coverage_buckets(source_coverage_body)
    status_source = {
        "Threads Account": _family_status("Threads Account", coverage_buckets),
        "Threads Keyword": _family_status("Threads Keyword", coverage_buckets),
        "RSS Feed": _family_status("RSS Feed", coverage_buckets),
        "GitHub": _extract_source_status(source_coverage_body, github_body, "Belum ada sinyal GitHub karena source GitHub belum aktif.", "Source GitHub aktif, tapi belum ada repo/tool yang cukup relevan hari ini."),
        "LinkedIn": _extract_source_status(source_coverage_body, linkedin_body, "Belum ada sinyal LinkedIn karena source LinkedIn belum aktif.", "Source LinkedIn aktif, tapi belum ada peluang networking yang cukup relevan hari ini."),
        "Lowongan": _extract_source_status(source_coverage_body, jobs_body, "Belum ada sinyal lowongan karena source job belum aktif.", "Source job aktif, tapi belum ada lowongan yang cukup relevan hari ini."),
    }

    detail_sections = {}
    for key in SECTION_META:
        body = section_map.get(key, "")
        if body:
            emoji, label, _, _ = SECTION_META[key]
            detail_sections[key] = f"{emoji} {label}\n\n{body}"[:MAX_TELEGRAM]

    available_section_keys = []
    for key, (_, _, _, always_show) in SECTION_META.items():
        body = section_map.get(key, "")
        if body and (_compact(body) or always_show):
            available_section_keys.append(key)

    return {
        "date": date or Path(path).parent.name,
        "category": category,
        "insight_path": str(path),
        "sections": section_map,
        "summary_preview": summary_preview,
        "action_titles": action_titles,
        "signal_titles": signal_titles,
        "opportunity_preview": opportunity_preview,
        "content_preview": content_preview,
        "status_source": status_source,
        "detail_sections": detail_sections,
        "available_section_keys": available_section_keys,
    }


def build_main_dashboard_message(payload):
    summary_lines = payload.get("summary_preview") or ["Belum ada ringkasan kuat hari ini."]
    action_titles = payload.get("action_titles") or ["Tidak ada prioritas baru yang cukup kuat hari ini."]
    signal_titles = payload.get("signal_titles") or ["Belum ada sinyal penting baru yang cukup kuat hari ini."]
    opportunity_preview = payload.get("opportunity_preview") or {}
    content_preview = payload.get("content_preview") or "Belum ada bahan post yang cukup kuat hari ini."
    status_source = payload.get("status_source") or {}

    lines = [
        "🧠 PAOS Daily Intelligence",
        "",
        "📝 Ringkasan Hari Ini",
        *_trim_preview_lines(summary_lines, 4),
        "",
        "✅ Yang Perlu Kamu Lakukan",
        *[f"{index}. {title}" for index, title in enumerate(action_titles[:3], start=1)],
        "",
        "🔥 Yang Lagi Penting",
        *[f"{index}. {title}" for index, title in enumerate(signal_titles[:3], start=1)],
        "",
        "🎯 Peluang untuk Kamu",
        f"- Project: {opportunity_preview.get('Project', 'Belum ada peluang project kuat hari ini.')}",
        f"- Konten: {opportunity_preview.get('Konten', 'Belum ada peluang konten kuat hari ini.')}",
        f"- Karier: {opportunity_preview.get('Karier', 'Belum ada peluang karier kuat hari ini.')}",
        "",
        "✍️ Bahan Konten",
        _compact(content_preview) or "Belum ada bahan post yang cukup kuat hari ini.",
        "",
        "📡 Status Source",
        f"- Threads Account: {status_source.get('Threads Account', 'belum aktif')}",
        f"- Threads Keyword: {status_source.get('Threads Keyword', 'belum aktif')}",
        f"- RSS Feed: {status_source.get('RSS Feed', 'belum aktif')}",
        f"- GitHub: {status_source.get('GitHub', 'belum aktif')}",
        f"- LinkedIn: {status_source.get('LinkedIn', 'belum aktif')}",
        f"- Lowongan: {status_source.get('Lowongan', 'belum aktif')}",
        "",
        "Pilih detail di bawah.",
    ]
    return "\n".join(lines)[:MAX_TELEGRAM]


def build_section_keyboard(payload):
    buttons = []
    for key in payload.get("available_section_keys") or []:
        if key not in SECTION_META:
            continue
        _, _, button_label, _ = SECTION_META[key]
        buttons.append(InlineKeyboardButton(button_label, callback_data=f"paos_section:{key}"))

    rows = []
    row = []
    for button in buttons:
        row.append(button)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("Apa yang perlu dilakukan", callback_data="paos_section:actions")]])


def resolve_daily_dashboard(runtime_path, category="ai", preferred_insight_path=None):
    insight_root = runtime_path / "intelligence" / "insights"
    insight_path = _resolve_latest_markdown_path(
        root_dir=insight_root,
        category=category,
        preferred_path=preferred_insight_path,
    )
    if not insight_path:
        return None

    payload = build_paos_dashboard_payload(path=insight_path, category=category)
    payload["dashboard_message"] = build_main_dashboard_message(payload)
    return {
        "date": payload["date"],
        "category": category,
        "insight_path": str(insight_path),
        "payload": payload,
    }


def _cache_dashboard(context, chat_id, resolved):
    cache = context.bot_data.setdefault(CACHE_KEY, {})
    cache[str(chat_id)] = {
        "date": resolved["date"],
        "category": resolved["category"],
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
    daily_status = _read_json(runtime_path / ".runtime" / "runs" / "daily-intelligence" / "latest.json")
    rss_status = _read_json(runtime_path / ".runtime" / "runs" / "rss-collector" / "latest.json")
    threads_status = _read_json(runtime_path / ".runtime" / "runs" / "threads-account" / "latest.json")
    digest_status = _read_json(runtime_path / ".runtime" / "runs" / "digest" / "latest.json")
    insight_status = _read_json(runtime_path / ".runtime" / "runs" / "insights" / "latest.json")

    digest_path = _resolve_latest_markdown_path(runtime_path / "intelligence" / "digests", category="ai")
    insight_path = _resolve_latest_markdown_path(runtime_path / "intelligence" / "insights", category="ai")
    status_source = {}
    if insight_path:
        payload = build_paos_dashboard_payload(path=insight_path, category="ai")
        status_source = payload.get("status_source") or {}

    rss_diag = (rss_status or {}).get("diagnostics") or {}
    feed_warnings = rss_diag.get("feed_warnings") or []
    threads_diag = (threads_status or {}).get("diagnostics") or {}

    parts = ["📊 Status Runtime PAOS"]
    parts.extend(
        [
            "",
            "Daily Intelligence",
            f"- status: {(daily_status or {}).get('status', 'belum ada data')}",
            f"- started: {(daily_status or {}).get('started_at', '-')}",
            f"- finished: {(daily_status or {}).get('finished_at', '-')}",
            f"- category: {(daily_status or {}).get('category', '-')}",
            "",
            "RSS",
            f"- status: {(rss_status or {}).get('status', 'belum ada data')}",
            f"- feeds: {(rss_status or {}).get('feeds_loaded', rss_diag.get('feeds_total', '-'))}",
            f"- items_written: {rss_diag.get('items_written', (rss_status or {}).get('items_collected', '-'))}",
            f"- warnings: {len(feed_warnings)}",
            "",
            "Threads Account",
            f"- status: {(threads_status or {}).get('status', 'belum ada data')}",
            f"- succeeded/empty/failed: {threads_diag.get('accounts_succeeded', '-')}/{threads_diag.get('accounts_empty', '-')}/{threads_diag.get('accounts_failed', '-')}",
            f"- items_collected: {(threads_status or {}).get('items_collected', threads_diag.get('items_collected', '-'))}",
            "",
            "Digest",
            f"- latest: {str(digest_path) if digest_path else 'belum ada data'}",
            "",
            "Insight",
            f"- latest: {str(insight_path) if insight_path else 'belum ada data'}",
            "",
            "Legacy Digest Worker",
            "- status: deprecated/inactive (workers/ai-digest.py tidak dipakai)",
            "",
            "Source Status",
            f"- Threads Account: {status_source.get('Threads Account', 'belum ada data')}",
            f"- Threads Keyword: {status_source.get('Threads Keyword', 'belum ada data')}",
            f"- RSS Feed: {status_source.get('RSS Feed', 'belum ada data')}",
            f"- GitHub: {status_source.get('GitHub', 'belum ada data')}",
            f"- LinkedIn: {status_source.get('LinkedIn', 'belum ada data')}",
            f"- Lowongan: {status_source.get('Lowongan', 'belum ada data')}",
        ]
    )
    stale_note = _stale_insight_note(digest_status, insight_status)
    if stale_note:
        parts.extend(["", stale_note])
    message = "\n".join(parts)
    await update.message.reply_text(message[:MAX_TELEGRAM])


async def handle_insight(update, context):
    runtime_path = _runtime_path()
    resolved = resolve_daily_dashboard(runtime_path=runtime_path, category="ai")
    if not resolved:
        await update.message.reply_text("Belum ada dashboard harian PAOS. Jalankan /update dulu.")
        return

    _cache_dashboard(context, update.effective_chat.id, resolved)
    await update.message.reply_text(
        resolved["payload"]["dashboard_message"],
        reply_markup=build_section_keyboard(resolved["payload"]),
    )


async def handle_update(update, context):
    runtime_path = _runtime_path()
    progress_message = await update.message.reply_text("⏳ Update dimulai. Aku ambil data terbaru lalu siapkan dashboard PAOS.")

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
        preferred_insight_path=(run_payload or {}).get("insight_path"),
    )
    if not resolved:
        await update.message.reply_text("Update selesai, tapi dashboard belum tersedia. Coba /insight.")
        return

    _cache_dashboard(context, update.effective_chat.id, resolved)
    await update.message.reply_text(
        resolved["payload"]["dashboard_message"],
        reply_markup=build_section_keyboard(resolved["payload"]),
    )


def _resolve_callback_section_key(callback_data):
    if callback_data.startswith("paos_section:"):
        return callback_data.split(":", 1)[1]
    if callback_data.startswith("insight_section:"):
        return OLD_TO_NEW_SECTION.get(callback_data.split(":", 1)[1])
    if callback_data == "insight_post":
        return "content"
    if callback_data.startswith("insight_detail:"):
        return "actions"
    if callback_data.startswith("digest_signal:"):
        return "signals"
    return None


async def handle_paos_section_callback(query, payload, callback_data):
    section_key = _resolve_callback_section_key(callback_data)
    if not section_key:
        await query.message.reply_text("Aksi tidak dikenali.")
        return

    detail = (payload.get("detail_sections") or {}).get(section_key)
    if not detail:
        await query.message.reply_text("Detail section tidak tersedia.")
        return
    await query.message.reply_text(detail[:MAX_TELEGRAM])


async def handle_insight_callback(update, context):
    query = update.callback_query
    await query.answer()

    runtime_path = _runtime_path()
    cached = _get_cached_dashboard(context, update.effective_chat.id)

    payload = None
    if cached:
        insight_path = Path(cached.get("insight_path", ""))
        if insight_path.exists():
            payload = cached.get("payload")

    if not payload:
        resolved = resolve_daily_dashboard(runtime_path=runtime_path, category="ai")
        if not resolved:
            await query.message.reply_text("Dashboard belum tersedia. Jalankan /update dulu.")
            return
        _cache_dashboard(context, update.effective_chat.id, resolved)
        payload = resolved["payload"]

    await handle_paos_section_callback(query, payload, _compact(query.data))
