import json


def compact_text(value):
    return " ".join(str(value or "").split())


def _compact_source_ref(ref):
    value = compact_text(ref)
    lowered = value.lower()
    if "claude opus 4.8" in lowered:
        return "Signal Claude Opus 4.8"
    if "usage visibility" in lowered or "sandboxing" in lowered or "harness" in lowered:
        return "Signal workflow Claude dan observability"
    if "gpt-5.5" in lowered or "codex" in lowered:
        return "Signal Codex dan workflow coding tim"
    if "healthcare" in lowered or "biodefense" in lowered or "evaluation governance" in lowered:
        return "Signal governance dan evaluasi AI"
    if "open-model" in lowered or "open model" in lowered or "ecosystem" in lowered or "china" in lowered:
        return "Signal ekosistem open model"
    if "runtime" in lowered or "pyodide" in lowered or "datasette" in lowered:
        return "Signal eksperimen runtime dan tooling"
    if "burnout" in lowered or "offline" in lowered or "culture" in lowered:
        return "Signal budaya kerja dan adopsi AI"
    if "growth and usage" in lowered or "demand for coding ai" in lowered:
        return "Signal permintaan enterprise untuk AI coding"
    return value


def _source_line(source_refs):
    refs = [_compact_source_ref(ref) for ref in (source_refs or []) if compact_text(ref)]
    return ", ".join(refs) if refs else "-"


def _status_text(status_obj, inactive_msg, empty_msg):
    if not isinstance(status_obj, dict):
        return inactive_msg
    status = compact_text(status_obj.get("status")).lower()
    items = status_obj.get("items") or []
    if "inactive" in status:
        return inactive_msg
    if not items:
        return empty_msg
    if isinstance(items[0], dict):
        first = compact_text(items[0].get("title") or items[0].get("item") or json.dumps(items[0], ensure_ascii=False))
        return first or empty_msg
    return compact_text(items[0]) or empty_msg


def _render_priority_actions(items):
    if not items:
        return ["Tidak ada prioritas baru yang cukup kuat hari ini."]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {compact_text(item.get('title'))}",
                "",
                "Kenapa penting:",
                compact_text(item.get("why_it_matters")) or "-",
                "",
                "Langkah berikutnya:",
                compact_text(item.get("next_step")) or "-",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_important_signals(items):
    if not items:
        return ["Belum ada sinyal penting baru yang cukup kuat hari ini."]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {compact_text(item.get('title'))}",
                "",
                "Artinya:",
                compact_text(item.get("meaning")) or "-",
                "",
                "Kenapa perlu dipantau:",
                compact_text(item.get("why_watch")) or "-",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_opportunities(items):
    if not items:
        return ["Belum ada peluang yang cukup kuat hari ini."]
    lines = []
    for item in items:
        opp_type = compact_text(item.get("type")).title() or "Peluang"
        lines.extend(
            [
                f"### {opp_type}: {compact_text(item.get('title'))}",
                "",
                "Kenapa relevan:",
                compact_text(item.get("why_relevant")) or "-",
                "",
                "Saran aksi:",
                compact_text(item.get("suggested_action")) or "-",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_content(items):
    if not items:
        return ["Belum ada bahan post yang cukup kuat hari ini."]
    lines = []
    for item in items:
        lines.extend(
            [
                f"### Angle: {compact_text(item.get('angle'))}",
                "",
                "Kenapa layak diposting:",
                compact_text(item.get("why_post")) or "-",
                "",
                "Threads-ready:",
                compact_text(item.get("threads_ready")) or "Belum ada copy Threads yang cukup kuat hari ini.",
                "",
                "X-ready:",
                compact_text(item.get("x_ready")) or "Belum ada copy X yang cukup kuat hari ini.",
                "",
                "LinkedIn angle:",
                compact_text(item.get("linkedin_angle")) or "Belum ada angle LinkedIn yang cukup kuat hari ini.",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_learning(items):
    if not items:
        return ["Belum ada topik belajar prioritas hari ini."]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {compact_text(item.get('topic'))}",
                "",
                "Kenapa:",
                compact_text(item.get("why_learn")) or "-",
                "",
                "Manfaat buat kamu:",
                compact_text(item.get("relevance")) or "-",
                "",
                "Mulai dari:",
                compact_text(item.get("start_from")) or "-",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_experiments(items):
    if not items:
        return ["Belum ada eksperimen kecil yang cukup kuat hari ini."]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {compact_text(item.get('experiment'))}",
                "",
                "Tujuan:",
                compact_text(item.get("purpose")) or "-",
                "",
                "Cara coba paling kecil:",
                compact_text(item.get("smallest_test")) or "-",
                "",
                "Hasil yang perlu dilihat:",
                compact_text(item.get("expected_signal")) or "-",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_context_updates(items):
    if not items:
        return ["Belum ada update konteks pribadi yang cukup kuat hari ini."]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {compact_text(item.get('suggestion'))}",
                "",
                "Kenapa:",
                compact_text(item.get("why")) or "-",
                "",
                "Aksi:",
                compact_text(item.get("action")) or "-",
                "",
            ]
        )
    return lines[:-1]


def _render_watchlist(items):
    if not items:
        return ["Belum ada item pantauan baru yang relevan hari ini."]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {compact_text(item.get('item'))}",
                "",
                "Status:",
                compact_text(item.get("status")) or "-",
                "",
                "Kenapa dipantau:",
                compact_text(item.get("watch_reason")) or "-",
                "",
                "Sumber:",
                _source_line(item.get("source_refs")),
                "",
            ]
        )
    return lines[:-1]


def _render_full_markdown(payload):
    summary_lines = [compact_text(x) for x in (payload.get("daily_summary") or []) if compact_text(x)]
    if not summary_lines:
        summary_lines = ["Belum ada ringkasan kuat hari ini."]

    source_cov = payload.get("source_coverage") or {}
    lines = [
        "# PAOS Daily Intelligence",
        "",
        "## Ringkasan Hari Ini",
        *summary_lines[:4],
        "",
        "## Yang Perlu Kamu Lakukan",
        *_render_priority_actions(payload.get("priority_actions") or []),
        "",
        "## Yang Lagi Penting",
        *_render_important_signals(payload.get("important_signals") or []),
        "",
        "## Peluang untuk Kamu",
        *_render_opportunities(payload.get("opportunities") or []),
        "",
        "## Bahan Konten & Branding",
        *_render_content(payload.get("content_branding") or []),
        "",
        "## Yang Layak Dipelajari",
        *_render_learning(payload.get("learning_queue") or []),
        "",
        "## Yang Layak Dicoba",
        *_render_experiments(payload.get("experiment_queue") or []),
        "",
        "## Radar GitHub & Tools",
        _status_text(
            payload.get("github_tools"),
            "Belum ada sinyal GitHub karena source GitHub belum aktif.",
            "Source GitHub aktif, tapi belum ada repo/tool yang cukup relevan hari ini.",
        ),
        "",
        "## Radar LinkedIn & Networking",
        _status_text(
            payload.get("linkedin_network"),
            "Belum ada sinyal LinkedIn karena source LinkedIn belum aktif.",
            "Source LinkedIn aktif, tapi belum ada peluang networking yang cukup relevan hari ini.",
        ),
        "",
        "## Radar Karier & Lowongan",
        _status_text(
            payload.get("career_jobs"),
            "Belum ada sinyal lowongan karena source job belum aktif.",
            "Source job aktif, tapi belum ada lowongan yang cukup relevan hari ini.",
        ),
        "",
        "## Update Konteks Pribadi",
        *_render_context_updates(payload.get("personal_context_updates") or []),
        "",
        "## Pantauan",
        *_render_watchlist(payload.get("watchlist") or []),
        "",
        "## Source Coverage",
        f"- Active: {', '.join(source_cov.get('active_sources') or []) or '-'}",
        f"- Inactive: {', '.join(source_cov.get('inactive_sources') or []) or '-'}",
        f"- Missing: {', '.join(source_cov.get('missing_sources') or []) or '-'}",
        f"- Notes: {compact_text(source_cov.get('notes')) or '-'}",
        "",
    ]
    return "\n".join(lines)


def _render_brief_markdown(payload):
    summary_lines = [compact_text(x) for x in (payload.get("daily_summary") or []) if compact_text(x)]
    if not summary_lines:
        summary_lines = ["Belum ada ringkasan kuat hari ini."]

    def list_titles(items, key, empty_text, limit=3):
        rows = []
        for index, item in enumerate((items or [])[:limit], start=1):
            text = compact_text(item.get(key)) if isinstance(item, dict) else compact_text(item)
            if text:
                rows.append(f"{index}. {text}")
        return rows or [empty_text]

    lines = [
        "# PAOS Daily Intelligence",
        "",
        "## Ringkasan Hari Ini",
        *summary_lines[:2],
        "",
        "## Yang Perlu Kamu Lakukan",
        *list_titles(payload.get("priority_actions") or [], "title", "Tidak ada prioritas baru yang cukup kuat hari ini."),
        "",
        "## Yang Lagi Penting",
        *list_titles(payload.get("important_signals") or [], "title", "Belum ada sinyal penting baru yang cukup kuat hari ini."),
        "",
    ]
    return "\n".join(lines)


def render_insights(category=None, date=None, language="id", signals=None, insights=None, dashboard=None):
    insights = insights or []
    payload = dashboard
    if payload is None and insights:
        payload = (insights[0].get("insight_metadata") or {}).get("dashboard_payload")
    payload = payload if isinstance(payload, dict) else {}
    return _render_full_markdown(payload)


def render_telegram_brief(language, signals, insights):
    payload = {}
    if insights:
        payload = (insights[0].get("insight_metadata") or {}).get("dashboard_payload") or {}
    return _render_brief_markdown(payload).strip()
