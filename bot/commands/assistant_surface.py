import json
import re
import sys
from datetime import datetime
from pathlib import Path

from context.loader import load_env


MAX_OPPORTUNITIES = 5
MAX_TODAY_OPPORTUNITIES = 3
MAX_TELEGRAM = 3900


def _compact(value):
    return " ".join(str(value or "").split())


GENERIC_BRIEF_PATTERNS = (
    "use latest digest as execution anchor",
    "translate latest insight into a small, testable change",
    "execute today focus",
    "apply one concrete task",
    "prioritize incremental delivery",
)

TITLE_PREFIX_RE = re.compile(r"^(build|learn|review|content)\s*:\s*", re.IGNORECASE)
PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def _runtime_path():
    env = load_env()
    configured = env.get("PAOS_RUNTIME_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2]


def _today_str():
    return datetime.now().astimezone().date().isoformat()


def _resolve_latest_file(root_dir, filename):
    today_candidate = root_dir / _today_str() / filename
    if today_candidate.exists() and today_candidate.is_file():
        return today_candidate
    candidates = sorted(
        [path for path in root_dir.glob(f"*/{filename}") if path.is_file()],
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_json(path_value):
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _is_generic_text(text):
    normalized = _compact(text).lower()
    if not normalized:
        return True
    return any(pattern in normalized for pattern in GENERIC_BRIEF_PATTERNS)


def _normalize_opportunity_text(text):
    cleaned = TITLE_PREFIX_RE.sub("", _compact(text).lower())
    cleaned = PUNCT_RE.sub(" ", cleaned)
    return " ".join(cleaned.split())


def _opportunity_specificity(item):
    title = _compact(item.get("title"))
    next_action = _compact(item.get("next_action"))
    title_score = len(title)
    action_score = len(next_action)
    bonus = 0
    if ":" in next_action or ";" in next_action:
        bonus += 15
    if not _is_generic_text(title):
        bonus += 20
    if not _is_generic_text(next_action):
        bonus += 20
    return title_score + action_score + bonus


def _dedupe_opportunities(items):
    deduped = []
    seen = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _compact(item.get("title"))
        next_action = _compact(item.get("next_action"))
        key = (
            _normalize_priority(item.get("priority")),
            _compact(item.get("type")).lower(),
            _normalize_opportunity_text(title),
            _normalize_opportunity_text(next_action),
        )
        if key in seen:
            current = deduped[seen[key]]
            if _opportunity_specificity(item) > _opportunity_specificity(current):
                deduped[seen[key]] = item
            continue
        seen[key] = len(deduped)
        deduped.append(item)

    grouped = {"high": [], "medium": [], "low": []}
    for item in deduped:
        grouped[_normalize_priority(item.get("priority"))].append(item)

    reduced = []
    for priority in ("high", "medium", "low"):
        bucket = sorted(grouped[priority], key=_opportunity_specificity, reverse=True)
        strong_by_type = {}
        for item in bucket:
            type_name = _compact(item.get("type")).lower()
            if not type_name:
                type_name = "unknown"
            if type_name in strong_by_type:
                continue
            if _is_generic_text(item.get("title")) and _is_generic_text(item.get("next_action")):
                continue
            strong_by_type[type_name] = item
        kept_bucket = []
        for item in bucket:
            candidate_title = _normalize_opportunity_text(item.get("title"))
            candidate_action = _normalize_opportunity_text(item.get("next_action"))
            candidate_type = _compact(item.get("type")).lower() or "unknown"
            is_close_duplicate = False
            for kept in kept_bucket:
                kept_title = _normalize_opportunity_text(kept.get("title"))
                kept_action = _normalize_opportunity_text(kept.get("next_action"))
                if (
                    candidate_title == kept_title
                    or candidate_action == kept_action
                    or (candidate_title and candidate_title in kept_title)
                    or (kept_title and kept_title in candidate_title)
                ):
                    is_close_duplicate = True
                    break
            if is_close_duplicate and _is_generic_text(item.get("title")):
                continue
            if is_close_duplicate and _is_generic_text(item.get("next_action")):
                continue
            strong = strong_by_type.get(candidate_type)
            if (
                strong is not None
                and strong is not item
                and _is_generic_text(item.get("title"))
                and _is_generic_text(item.get("next_action"))
            ):
                continue
            kept_bucket.append(item)
        reduced.extend(kept_bucket)
    return reduced


def _render_brief_message(payload):
    focus = _compact(payload.get("focus_today"))
    next_action = _compact(payload.get("suggested_next_action"))
    opportunities = payload.get("opportunities") if isinstance(payload.get("opportunities"), dict) else {}

    focus_lines = []
    if focus and not _is_generic_text(focus):
        focus_lines.append(focus)

    for candidate in (opportunities.get("build") or []) + (opportunities.get("review") or []):
        if len(focus_lines) >= 2:
            break
        candidate_text = _compact(candidate)
        if not candidate_text:
            continue
        if candidate_text in focus_lines:
            continue
        focus_lines.append(candidate_text)

    if not focus_lines:
        fallback_focus = focus or "Belum ada fokus hari ini."
        focus_lines = [fallback_focus]

    if (not next_action) or _is_generic_text(next_action):
        for candidate in opportunities.get("build") or []:
            candidate_text = _compact(candidate)
            if candidate_text:
                next_action = candidate_text
                break
    if not next_action:
        next_action = "Belum ada suggested next action."

    risks = payload.get("risks_or_checks")
    risk_lines = []
    if isinstance(risks, list):
        for item in risks[:3]:
            line = _compact(item)
            if line:
                risk_lines.append(f"- {line}")
    if not risk_lines:
        risk_lines.append("- Belum ada risiko/perlu dicek.")

    source_artifacts = payload.get("source_artifacts") if isinstance(payload.get("source_artifacts"), dict) else {}
    source_coverage = []
    for key in ("digest", "insight", "assistant_context_json"):
        source = source_artifacts.get(key) if isinstance(source_artifacts, dict) else None
        exists = bool(source.get("exists")) if isinstance(source, dict) else False
        source_coverage.append(f"- {key}: {'ada' if exists else 'tidak ada'}")

    lines = [
        "🧭 PAOS Brief",
        "",
        "Fokus Hari Ini",
        *[f"{idx}. {line}" for idx, line in enumerate(focus_lines, start=1)],
        "",
        "Suggested Next Action",
        next_action,
        "",
        "Risiko / Perlu Dicek",
        *risk_lines,
    ]
    if source_coverage:
        lines.extend(["", "Source Coverage", *source_coverage])
    return "\n".join(lines)[:MAX_TELEGRAM]


def _normalize_priority(value):
    normalized = _compact(value).lower()
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "low"


def _render_opportunity_item(item, index):
    title = _compact(item.get("title")) or "Tanpa judul"
    opp_type = _compact(item.get("type")) or "-"
    priority = _normalize_priority(item.get("priority")).title()
    next_action = _compact(item.get("next_action")) or "Belum ada next action."
    return (
        f"{index}. {title}\n"
        f"   type: {opp_type}\n"
        f"   priority: {priority}\n"
        f"   next: {next_action}"
    )


def _render_opportunities_message(payload):
    opportunities = payload.get("opportunities")
    if not isinstance(opportunities, list):
        opportunities = []
    original_count = len(opportunities)
    opportunities = _dedupe_opportunities(opportunities)

    grouped = {"high": [], "medium": [], "low": []}
    for item in opportunities:
        if not isinstance(item, dict):
            continue
        grouped[_normalize_priority(item.get("priority"))].append(item)

    ordered = grouped["high"] + grouped["medium"] + grouped["low"]
    limited = ordered[:MAX_OPPORTUNITIES]
    if not limited:
        return "🎯 PAOS Opportunities\n\nBelum ada opportunities terbaru."

    type_counts = {}
    for item in limited:
        opp_type = _compact(item.get("type")).lower() or "unknown"
        type_counts[opp_type] = type_counts.get(opp_type, 0) + 1

    lines = ["🎯 PAOS Opportunities"]
    lines.append(f"Menampilkan {len(limited)} dari {original_count} peluang terbaru.")

    index = 1
    for label, key in (("High", "high"), ("Medium", "medium"), ("Low", "low")):
        bucket = [item for item in limited if _normalize_priority(item.get("priority")) == key]
        if not bucket:
            continue
        lines.extend(["", label])
        for item in bucket:
            lines.append(_render_opportunity_item(item, index))
            index += 1

    if type_counts:
        summary_parts = [f"{name}: {count}" for name, count in sorted(type_counts.items())]
        lines.extend(["", f"Ringkasan type: {', '.join(summary_parts)}"])
    return "\n".join(lines)[:MAX_TELEGRAM]


def _extract_brief_focus_lines(brief_payload):
    focus = _compact(brief_payload.get("focus_today"))
    opportunities = (
        brief_payload.get("opportunities")
        if isinstance(brief_payload.get("opportunities"), dict)
        else {}
    )

    focus_lines = []
    if focus and not _is_generic_text(focus):
        focus_lines.append(focus)

    for candidate in (opportunities.get("build") or []) + (opportunities.get("review") or []):
        if len(focus_lines) >= 2:
            break
        candidate_text = _compact(candidate)
        if not candidate_text or candidate_text in focus_lines:
            continue
        focus_lines.append(candidate_text)

    if not focus_lines:
        focus_lines = [focus or "Belum ada fokus hari ini."]
    return focus_lines[:2]


def _render_today_message(brief_payload, opportunities_payload):
    brief_exists = bool(brief_payload)
    opportunities_exists = bool(opportunities_payload)

    lines = ["🗓 PAOS Today", "", "Fokus Hari Ini"]
    if brief_exists:
        for idx, line in enumerate(_extract_brief_focus_lines(brief_payload), start=1):
            lines.append(f"{idx}. {line}")
    else:
        lines.extend(
            [
                "1. Brief belum tersedia.",
                "Jalankan:",
                "venv/bin/python runtime/assistant/jobs/run_assistant_brief.py --category ai",
            ]
        )

    lines.extend(["", "Top Opportunities"])
    reduced_opps = []
    if opportunities_exists:
        opportunities = opportunities_payload.get("opportunities")
        if isinstance(opportunities, list):
            reduced_opps = _dedupe_opportunities(opportunities)
        ordered = sorted(
            [item for item in reduced_opps if isinstance(item, dict)],
            key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(_normalize_priority(item.get("priority")), 3),
        )
        top_items = ordered[:MAX_TODAY_OPPORTUNITIES]
        if top_items:
            for idx, item in enumerate(top_items, start=1):
                title = _compact(item.get("title")) or "Tanpa judul"
                next_action = _compact(item.get("next_action")) or "Belum ada next action."
                lines.append(f"{idx}. {title}")
                lines.append(f"   next: {next_action}")
        else:
            lines.append("Belum ada opportunities terbaru.")
    else:
        lines.extend(
            [
                "Opportunities belum tersedia.",
                "Jalankan:",
                "venv/bin/python runtime/assistant/jobs/run_assistant_opportunities.py --category ai",
            ]
        )

    next_action = ""
    if brief_exists:
        next_action = _compact(brief_payload.get("suggested_next_action"))
        if _is_generic_text(next_action):
            next_action = ""
    if not next_action and reduced_opps:
        for item in reduced_opps:
            candidate = _compact(item.get("next_action"))
            if candidate:
                next_action = candidate
                break
    if not next_action:
        next_action = "Belum ada next action."

    lines.extend(
        [
            "",
            "Next Action",
            next_action,
            "",
            "Status",
            f"- Brief: {'ada' if brief_exists else 'missing'}",
            f"- Opportunities: {'ada' if opportunities_exists else 'missing'}",
        ]
    )
    return "\n".join(lines)[:MAX_TELEGRAM]


async def handle_brief(update):
    brief_root = _runtime_path() / "assistant" / "briefs"
    json_path = _resolve_latest_file(brief_root, "assistant-brief.json")
    payload = _read_json(str(json_path) if json_path else None)
    if not payload:
        await update.message.reply_text(
            "Artifact brief belum tersedia atau rusak.\n"
            "Jalankan:\n"
            "venv/bin/python runtime/assistant/jobs/run_assistant_brief.py --category ai"
        )
        return
    await update.message.reply_text(_render_brief_message(payload))


async def handle_opportunities(update):
    opportunities_root = _runtime_path() / "assistant" / "opportunities"
    json_path = _resolve_latest_file(opportunities_root, "opportunities.json")
    payload = _read_json(str(json_path) if json_path else None)
    if not payload:
        await update.message.reply_text(
            "Artifact opportunities belum tersedia atau rusak.\n"
            "Jalankan:\n"
            "venv/bin/python runtime/assistant/jobs/run_assistant_opportunities.py --category ai"
        )
        return
    await update.message.reply_text(_render_opportunities_message(payload))


async def handle_today(update):
    brief_root = _runtime_path() / "assistant" / "briefs"
    opportunities_root = _runtime_path() / "assistant" / "opportunities"

    brief_json_path = _resolve_latest_file(brief_root, "assistant-brief.json")
    opportunities_json_path = _resolve_latest_file(opportunities_root, "opportunities.json")

    brief_payload = _read_json(str(brief_json_path) if brief_json_path else None)
    opportunities_payload = _read_json(str(opportunities_json_path) if opportunities_json_path else None)

    await update.message.reply_text(_render_today_message(brief_payload, opportunities_payload))


# ---------------------------------------------------------------------------
# /dashboard — PAOS Assistant OS Home Screen
# ---------------------------------------------------------------------------

def _freshness_label(date_value):
    if not date_value:
        return "n/a"
    today = _today_str()
    if date_value == today:
        return "fresh"
    try:
        artifact_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        today_date = datetime.strptime(today, "%Y-%m-%d").date()
        delta = (today_date - artifact_date).days
        if delta == 1:
            return "1d old"
        return f"{delta}d old"
    except ValueError:
        return "n/a"


def _resolve_artifact_date(root_dir, filename):
    """Resolve the date folder name of the latest artifact."""
    path = _resolve_latest_file(root_dir, filename)
    if not path:
        return None, None
    try:
        datetime.strptime(path.parent.name, "%Y-%m-%d")
        return path, path.parent.name
    except ValueError:
        return path, None


def _render_dashboard_message(brief_payload, opportunities_payload, context_meta, artifacts_meta, runtime_statuses):
    lines = ["🖥 PAOS Dashboard", ""]

    # Fokus Hari Ini
    lines.append("📌 Fokus Hari Ini")
    if brief_payload:
        focus = _compact(brief_payload.get("focus_today"))
        if focus and not _is_generic_text(focus):
            lines.append(focus)
        else:
            focus_lines = _extract_brief_focus_lines(brief_payload)
            for idx, line in enumerate(focus_lines, start=1):
                lines.append(f"{idx}. {line}")
    else:
        lines.append("Brief belum tersedia.")

    # Current State
    lines.extend(["", "📊 Current State"])
    for label, meta in [
        ("Brief", artifacts_meta.get("brief")),
        ("Opportunities", artifacts_meta.get("opportunities")),
        ("Context", artifacts_meta.get("context")),
        ("Digest", artifacts_meta.get("digest")),
        ("Insight", artifacts_meta.get("insight")),
    ]:
        if meta and meta.get("exists"):
            lines.append(f"- {label}: ada ({_freshness_label(meta.get('date'))})")
        else:
            lines.append(f"- {label}: missing")

    # Relevant Intelligence
    lines.extend(["", "🧠 Relevant Intelligence"])
    has_intelligence = False
    if artifacts_meta.get("digest", {}).get("exists"):
        lines.append(f"- Digest: {artifacts_meta['digest'].get('date') or 'available'}")
        has_intelligence = True
    if artifacts_meta.get("insight", {}).get("exists"):
        lines.append(f"- Insight: {artifacts_meta['insight'].get('date') or 'available'}")
        has_intelligence = True
    if not has_intelligence:
        lines.append("- Belum ada intelligence artifacts.")

    # Top Opportunities
    lines.extend(["", "🎯 Top Opportunities"])
    if opportunities_payload and isinstance(opportunities_payload.get("opportunities"), list):
        opps = opportunities_payload["opportunities"]
        reduced = _dedupe_opportunities(opps)
        ordered = sorted(
            [item for item in reduced if isinstance(item, dict)],
            key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(
                _normalize_priority(item.get("priority")), 3
            ),
        )
        for idx, item in enumerate(ordered[:3], start=1):
            title = _compact(item.get("title")) or "Tanpa judul"
            priority = _normalize_priority(item.get("priority")).title()
            lines.append(f"{idx}. [{priority}] {title}")
    else:
        lines.append("- Belum ada opportunities.")

    # Recommended Actions
    lines.extend(["", "⚡ Recommended Actions"])
    actions_added = 0
    if brief_payload:
        next_action = _compact(brief_payload.get("suggested_next_action"))
        if next_action and not _is_generic_text(next_action):
            lines.append(f"1. {next_action}")
            actions_added += 1
    if not artifacts_meta.get("brief", {}).get("exists"):
        actions_added += 1
        lines.append(f"{actions_added}. Generate assistant brief.")
    if not artifacts_meta.get("opportunities", {}).get("exists"):
        actions_added += 1
        lines.append(f"{actions_added}. Generate opportunities.")
    if not artifacts_meta.get("context", {}).get("exists"):
        actions_added += 1
        lines.append(f"{actions_added}. Build assistant context.")
    if actions_added == 0:
        lines.append("1. All artifacts available. Execute top opportunity.")

    # Context Health
    lines.extend(["", "🩺 Context Health"])
    ctx_loaded = artifacts_meta.get("context", {}).get("exists")
    lines.append(f"- Context: {'loaded' if ctx_loaded else 'not loaded'}")
    lines.append(f"- Brief: {'loaded' if artifacts_meta.get('brief', {}).get('exists') else 'not loaded'}")
    lines.append(f"- Opportunities: {'loaded' if artifacts_meta.get('opportunities', {}).get('exists') else 'not loaded'}")
    lines.append(f"- Runtime jobs: {len(runtime_statuses)}")

    # Source Status
    if runtime_statuses:
        lines.extend(["", "📡 Source Status"])
        for item in runtime_statuses[:5]:
            job = item.get("job") or "unknown"
            status = item.get("status") or "unknown"
            lines.append(f"- {job}: {status}")

    return "\n".join(lines)[:MAX_TELEGRAM]


async def handle_dashboard(update):
    runtime_path = _runtime_path()

    # Resolve brief
    brief_root = runtime_path / "assistant" / "briefs"
    brief_json_path = _resolve_latest_file(brief_root, "assistant-brief.json")
    brief_payload = _read_json(str(brief_json_path) if brief_json_path else None)

    # Resolve opportunities
    opportunities_root = runtime_path / "assistant" / "opportunities"
    opps_json_path = _resolve_latest_file(opportunities_root, "opportunities.json")
    opportunities_payload = _read_json(str(opps_json_path) if opps_json_path else None)

    # Resolve context meta
    context_root = runtime_path / "assistant" / "context"
    context_json_path, context_date = _resolve_artifact_date(context_root, "assistant-context.json")

    # Resolve digest/insight meta
    digest_root = runtime_path / "intelligence" / "digests"
    digest_path, digest_date = _resolve_artifact_date(digest_root, "ai.md")

    insight_root = runtime_path / "intelligence" / "insights"
    insight_path, insight_date = _resolve_artifact_date(insight_root, "ai.md")

    # Artifacts meta
    artifacts_meta = {
        "brief": {"exists": bool(brief_json_path), "date": brief_json_path.parent.name if brief_json_path else None},
        "opportunities": {"exists": bool(opps_json_path), "date": opps_json_path.parent.name if opps_json_path else None},
        "context": {"exists": bool(context_json_path), "date": context_date},
        "digest": {"exists": bool(digest_path), "date": digest_date},
        "insight": {"exists": bool(insight_path), "date": insight_date},
    }

    # Runtime statuses
    runtime_statuses = []
    runs_dir = runtime_path / ".runtime" / "runs"
    if runs_dir.exists() and runs_dir.is_dir():
        for status_path in sorted(runs_dir.glob("*/latest.json")):
            status_payload = _read_json(str(status_path))
            if status_payload and isinstance(status_payload, dict):
                runtime_statuses.append({
                    "job": status_payload.get("job") or status_path.parent.name,
                    "status": status_payload.get("status") or "unknown",
                    "finished_at": status_payload.get("finished_at"),
                })

    await update.message.reply_text(
        _render_dashboard_message(
            brief_payload, opportunities_payload, None, artifacts_meta, runtime_statuses
        )
    )


# ---------------------------------------------------------------------------
# /daily — Daily Action Planner
# ---------------------------------------------------------------------------

def _render_daily_message(brief_payload, opportunities_payload, artifacts_meta):
    lines = ["📋 PAOS Daily Planner", ""]

    # 3 Priorities
    lines.append("🎯 Priorities Today")
    priorities = []

    if brief_payload:
        focus = _compact(brief_payload.get("focus_today"))
        if focus and not _is_generic_text(focus):
            priorities.append(focus)
        brief_opps = brief_payload.get("opportunities") or {}
        for item in (brief_opps.get("build") or [])[:2]:
            text = _compact(item)
            if text and text not in priorities:
                priorities.append(text)

    if opportunities_payload and isinstance(opportunities_payload.get("opportunities"), list):
        for item in opportunities_payload["opportunities"][:5]:
            if len(priorities) >= 3:
                break
            if isinstance(item, dict):
                title = _compact(item.get("title"))
                if title and title not in priorities:
                    priorities.append(title)

    if not priorities:
        priorities = ["Belum ada prioritas. Generate brief dan opportunities."]

    for idx, p in enumerate(priorities[:3], start=1):
        lines.append(f"{idx}. {p}")

    # 1 Defer/Ignore
    lines.extend(["", "⏸ Defer/Ignore"])
    defer_item = ""
    if brief_payload:
        risks = brief_payload.get("risks_or_checks") or []
        for risk in reversed(risks):
            text = _compact(risk)
            if text and "no critical" not in text.lower():
                defer_item = text
                break
    if not defer_item and opportunities_payload and isinstance(opportunities_payload.get("opportunities"), list):
        low_prio = [
            item for item in opportunities_payload["opportunities"]
            if isinstance(item, dict) and _compact(item.get("priority")).lower() == "low"
        ]
        if low_prio:
            defer_item = _compact(low_prio[0].get("title"))
    if not defer_item:
        defer_item = "Tidak ada item yang perlu di-defer."
    lines.append(f"- {defer_item}")

    # 1 Next Action
    lines.extend(["", "▶️ Next Action"])
    next_action = ""
    if brief_payload:
        next_action = _compact(brief_payload.get("suggested_next_action"))
        if _is_generic_text(next_action):
            next_action = ""
    if not next_action and priorities:
        next_action = f"Mulai dari: {priorities[0]}"
    if not next_action:
        next_action = "Generate assistant brief terlebih dahulu."
    lines.append(next_action)

    # 1 Context Update Suggestion
    lines.extend(["", "💡 Context Update"])
    today = _today_str()
    ctx_meta = artifacts_meta.get("context", {})
    brief_meta = artifacts_meta.get("brief", {})
    if not ctx_meta.get("exists"):
        lines.append("Build assistant context — belum ada context artifact.")
    elif ctx_meta.get("date") and ctx_meta["date"] < today:
        lines.append(f"Refresh assistant context (last: {ctx_meta['date']}).")
    elif not brief_meta.get("exists"):
        lines.append("Generate assistant brief untuk update context loop.")
    elif brief_meta.get("date") and brief_meta["date"] < today:
        lines.append(f"Regenerate brief (last: {brief_meta['date']}).")
    else:
        lines.append("Context loop up to date.")

    # Freshness note
    lines.extend(["", "📅 Freshness"])
    for label, key in [("Brief", "brief"), ("Opps", "opportunities"), ("Context", "context"), ("Digest", "digest"), ("Insight", "insight")]:
        meta = artifacts_meta.get(key, {})
        lines.append(f"- {label}: {_freshness_label(meta.get('date')) if meta.get('exists') else 'missing'}")

    return "\n".join(lines)[:MAX_TELEGRAM]


async def handle_daily(update):
    runtime_path = _runtime_path()

    # Resolve brief
    brief_root = runtime_path / "assistant" / "briefs"
    brief_json_path = _resolve_latest_file(brief_root, "assistant-brief.json")
    brief_payload = _read_json(str(brief_json_path) if brief_json_path else None)

    # Resolve opportunities
    opportunities_root = runtime_path / "assistant" / "opportunities"
    opps_json_path = _resolve_latest_file(opportunities_root, "opportunities.json")
    opportunities_payload = _read_json(str(opps_json_path) if opps_json_path else None)

    # Resolve context meta
    context_root = runtime_path / "assistant" / "context"
    context_json_path, context_date = _resolve_artifact_date(context_root, "assistant-context.json")

    # Resolve digest/insight meta
    digest_root = runtime_path / "intelligence" / "digests"
    digest_path, digest_date = _resolve_artifact_date(digest_root, "ai.md")

    insight_root = runtime_path / "intelligence" / "insights"
    insight_path, insight_date = _resolve_artifact_date(insight_root, "ai.md")

    artifacts_meta = {
        "brief": {"exists": bool(brief_json_path), "date": brief_json_path.parent.name if brief_json_path else None},
        "opportunities": {"exists": bool(opps_json_path), "date": opps_json_path.parent.name if opps_json_path else None},
        "context": {"exists": bool(context_json_path), "date": context_date},
        "digest": {"exists": bool(digest_path), "date": digest_date},
        "insight": {"exists": bool(insight_path), "date": insight_date},
    }

    await update.message.reply_text(
        _render_daily_message(brief_payload, opportunities_payload, artifacts_meta)
    )


# ---------------------------------------------------------------------------
# /context — Context Health Inspector
# ---------------------------------------------------------------------------

def _render_context_message(artifacts_meta, runtime_statuses, warnings):
    lines = ["🩺 PAOS Context Health", ""]

    # Sections loaded
    lines.append("📦 Artifact Status")
    for label, key in [
        ("Assistant Context", "context"),
        ("Assistant Brief", "brief"),
        ("Opportunities", "opportunities"),
        ("Digest", "digest"),
        ("Insight", "insight"),
    ]:
        meta = artifacts_meta.get(key, {})
        if meta.get("exists"):
            freshness = _freshness_label(meta.get("date"))
            lines.append(f"- {label}: loaded ({freshness})")
        else:
            lines.append(f"- {label}: not loaded")

    # Runtime jobs
    lines.extend(["", "⚙️ Runtime Jobs"])
    if runtime_statuses:
        failed = [item for item in runtime_statuses if (item.get("status") or "").lower() in {"failed", "error"}]
        ok_count = len(runtime_statuses) - len(failed)
        lines.append(f"- Total: {len(runtime_statuses)} | OK: {ok_count} | Failed: {len(failed)}")
        if failed:
            for item in failed[:3]:
                lines.append(f"  ❌ {item.get('job')}: {item.get('status')}")
    else:
        lines.append("- No runtime job statuses found.")

    # Warnings
    if warnings:
        lines.extend(["", "⚠️ Warnings"])
        for w in warnings[:6]:
            lines.append(f"- {_compact(w)}")

    # Memory provider status (read-only, from runtime status if available)
    lines.extend(["", "🧠 Memory Provider"])
    lines.append("- Status: read-only check not available from Telegram surface.")
    lines.append("- Use /ops or run diagnostics job for full memory health.")

    return "\n".join(lines)[:MAX_TELEGRAM]


async def handle_context(update):
    runtime_path = _runtime_path()

    # Resolve context meta
    context_root = runtime_path / "assistant" / "context"
    context_json_path, context_date = _resolve_artifact_date(context_root, "assistant-context.json")

    # Resolve brief meta
    brief_root = runtime_path / "assistant" / "briefs"
    brief_json_path = _resolve_latest_file(brief_root, "assistant-brief.json")

    # Resolve opportunities meta
    opportunities_root = runtime_path / "assistant" / "opportunities"
    opps_json_path = _resolve_latest_file(opportunities_root, "opportunities.json")

    # Resolve digest/insight meta
    digest_root = runtime_path / "intelligence" / "digests"
    digest_path, digest_date = _resolve_artifact_date(digest_root, "ai.md")

    insight_root = runtime_path / "intelligence" / "insights"
    insight_path, insight_date = _resolve_artifact_date(insight_root, "ai.md")

    artifacts_meta = {
        "brief": {"exists": bool(brief_json_path), "date": brief_json_path.parent.name if brief_json_path else None},
        "opportunities": {"exists": bool(opps_json_path), "date": opps_json_path.parent.name if opps_json_path else None},
        "context": {"exists": bool(context_json_path), "date": context_date},
        "digest": {"exists": bool(digest_path), "date": digest_date},
        "insight": {"exists": bool(insight_path), "date": insight_date},
    }

    # Runtime statuses
    runtime_statuses = []
    runs_dir = runtime_path / ".runtime" / "runs"
    if runs_dir.exists() and runs_dir.is_dir():
        for status_path in sorted(runs_dir.glob("*/latest.json")):
            status_payload = _read_json(str(status_path))
            if status_payload and isinstance(status_payload, dict):
                runtime_statuses.append({
                    "job": status_payload.get("job") or status_path.parent.name,
                    "status": status_payload.get("status") or "unknown",
                    "finished_at": status_payload.get("finished_at"),
                })

    # Collect warnings from context JSON if available
    warnings = []
    if context_json_path:
        context_payload = _read_json(str(context_json_path))
        if context_payload and isinstance(context_payload, dict):
            diag = context_payload.get("diagnostics") or {}
            warnings.extend(diag.get("warnings") or [])

    # Check for stale artifacts
    today = _today_str()
    for label, key in [("brief", "brief"), ("opportunities", "opportunities"), ("context", "context")]:
        meta = artifacts_meta.get(key, {})
        if meta.get("exists") and meta.get("date") and meta["date"] < today:
            warnings.append(f"{label} is stale ({meta['date']})")

    await update.message.reply_text(
        _render_context_message(artifacts_meta, runtime_statuses, warnings)
    )


def _load_memory_runtime():
    runtime_module_root = _runtime_path() / "runtime"
    if str(runtime_module_root) not in sys.path:
        sys.path.insert(0, str(runtime_module_root))
    from assistant.memory import MemoryQuery, load_memory_provider  # type: ignore

    return MemoryQuery, load_memory_provider


def _format_memory_items(items, limit=3):
    prefix_re = re.compile(r"^\s*(?:[-*]\s+|\d+[.)]\s+)+")
    rows = []
    for item in items[:limit]:
        content = _compact(item.get("content") if isinstance(item, dict) else "")
        content = prefix_re.sub("", content).strip()
        if not content:
            continue
        rows.append(content[:140])
    return rows


def _parse_context_payload(context_payload):
    decisions = []
    blockers = []
    next_actions = []
    recent_progress = []
    if not isinstance(context_payload, dict):
        return decisions, blockers, next_actions, recent_progress

    sections = context_payload.get("sections")
    if not isinstance(sections, dict):
        return decisions, blockers, next_actions, recent_progress

    for key in ("recent_progress", "progress", "recent_updates"):
        value = sections.get(key)
        if isinstance(value, list):
            recent_progress.extend([_compact(x) for x in value if _compact(x)])
            break
    for key in ("decisions", "key_decisions"):
        value = sections.get(key)
        if isinstance(value, list):
            decisions.extend([_compact(x) for x in value if _compact(x)])
            break
    for key in ("blockers", "risks_or_blockers", "risks"):
        value = sections.get(key)
        if isinstance(value, list):
            blockers.extend([_compact(x) for x in value if _compact(x)])
            break
    for key in ("next_actions", "suggested_next_actions"):
        value = sections.get(key)
        if isinstance(value, list):
            next_actions.extend([_compact(x) for x in value if _compact(x)])
            break

    return decisions, blockers, next_actions, recent_progress


def _resolve_assistant_payloads():
    runtime_path = _runtime_path()
    brief_payload = _read_json(
        str(_resolve_latest_file(runtime_path / "assistant" / "briefs", "assistant-brief.json") or "")
    ) or {}
    opportunities_payload = _read_json(
        str(_resolve_latest_file(runtime_path / "assistant" / "opportunities", "opportunities.json") or "")
    ) or {}
    context_payload = _read_json(
        str(_resolve_latest_file(runtime_path / "assistant" / "context", "assistant-context.json") or "")
    ) or {}
    return brief_payload, opportunities_payload, context_payload


def _build_memory_surface_message():
    MemoryQuery, load_memory_provider = _load_memory_runtime()
    provider_name = "unknown"
    health_label = "unavailable"
    health_note = "fallback not available"
    active_memory = []
    selection = None
    memory_items = []
    try:
        selection = load_memory_provider()
        provider_name = selection.active_provider
        health = selection.active_health.to_dict()
        health_label = "healthy" if health.get("healthy") else "unhealthy"
        health_note = _compact(health.get("message"))
        memory_items = [item.to_dict() for item in selection.provider.recall(MemoryQuery(text="", limit=8))]
        active_memory = _format_memory_items(memory_items, limit=3)
    except Exception as exc:
        health_note = f"memory provider error: {exc}"

    brief_payload, opportunities_payload, context_payload = _resolve_assistant_payloads()
    decisions, blockers, next_actions, recent_progress = _parse_context_payload(context_payload)

    if not recent_progress:
        recent_progress = _format_memory_items(memory_items, limit=3)
    if not decisions and memory_items:
        decisions = _format_memory_items(memory_items, limit=2)
    if not next_actions:
        candidate = _compact(brief_payload.get("suggested_next_action"))
        if candidate:
            next_actions = [candidate]

    promotion_candidates = []
    if next_actions:
        promotion_candidates.append("domains/work/current-project.md")
    if decisions:
        promotion_candidates.append("core/current-state.md")
    if blockers:
        promotion_candidates.append("domains/daily/notes.md")

    lines = [
        "Memory Surface",
        "",
        "Memory Provider",
        f"- Active: {provider_name}",
        f"- Health: {health_label}",
        f"- Fallback: {'on' if selection and selection.fallback_used else 'off'}",
        "",
        "Health / fallback status",
        f"- {_compact(health_note) or 'n/a'}",
        "",
        "Active Memory",
        *(active_memory or ["- Belum ada memory aktif."]),
        "",
        "Recent Progress",
        *([f"- {x}" for x in recent_progress[:3]] or ["- Belum ada progress terbaru."]),
        "",
        "Decisions",
        *([f"- {x}" for x in decisions[:3]] or ["- Belum ada decisions terbaru."]),
        "",
        "Blockers",
        *([f"- {x}" for x in blockers[:3]] or ["- Belum ada blockers."]),
        "",
        "Next Actions",
        *([f"- {x}" for x in next_actions[:3]] or ["- Belum ada next actions."]),
        "",
        "Promotion Candidates",
        *([f"- {x}" for x in promotion_candidates] or ["- Belum inferable dari data saat ini."]),
    ]
    personalization = _build_insight_personalization()
    lines.extend(
        [
            "",
            "Insight Relevance",
            f"- {_compact(personalization.get('relevant_insight'))}",
            f"- Next: {_compact(personalization.get('recommended_action'))}",
        ]
    )
    return "\n".join(lines)[:MAX_TELEGRAM]


def _build_handoff_message(target="generic"):
    brief_payload, opportunities_payload, context_payload = _resolve_assistant_payloads()
    decisions, blockers, next_actions, recent_progress = _parse_context_payload(context_payload)
    top_opps = []
    if isinstance(opportunities_payload.get("opportunities"), list):
        ordered = _dedupe_opportunities(opportunities_payload.get("opportunities") or [])
        for item in ordered[:3]:
            top_opps.append(_compact(item.get("title")))

    target_label = target if target in {"codex", "claude", "hermes"} else "generic"
    files = [
        "assistant/briefs/<latest>/assistant-brief.json",
        "assistant/context/<latest>/assistant-context.json",
        "assistant/opportunities/<latest>/opportunities.json",
    ]
    if target_label == "codex":
        files.append("runtime/assistant/adapters/codex.md")
    if target_label == "claude":
        files.append("runtime/assistant/adapters/claude-code.md")
    if target_label == "hermes":
        files.extend(
            [
                "runtime/assistant/adapters/hermes.md",
                "runtime/assistant/contracts/hermes-bridge.md",
            ]
        )

    guardrail_lines = [
        "- Read-only surface only.",
        "- No scheduler, no GitHub source, no Hermes bridge.",
        "- No controlled write or memory write from this handoff surface.",
    ]
    if target_label == "hermes":
        guardrail_lines = [
            "- Read-only surface only.",
            "- No scheduler or GitHub source changes from this handoff surface.",
            "- Hermes is a consumer of PAOS; PAOS must not depend on Hermes.",
            "- No controlled write or memory write from this handoff surface.",
        ]

    lines = [
        f"Handoff ({target_label})",
        "",
        "Task summary",
        f"- {_compact(brief_payload.get('focus_today')) or 'Lanjutkan prioritas assistant terbaru.'}",
        "",
        "Current state",
        f"- Brief: {'available' if brief_payload else 'missing'}",
        f"- Context: {'available' if context_payload else 'missing'}",
        f"- Opportunities: {'available' if opportunities_payload else 'missing'}",
        "",
        "Decisions",
        *([f"- {x}" for x in decisions[:3]] or ["- Belum ada decision yang terekam."]),
        "",
        "Next action",
        *([f"- {x}" for x in next_actions[:2]] or ["- Eksekusi top opportunity terbaru."]),
        "",
        "Files/context to inspect",
        *[f"- {path}" for path in files],
        "",
        "Validation needed",
        "- Pastikan artifact terbaru parseable dan tidak stale.",
        "- Verifikasi next action tidak generik sebelum eksekusi.",
        "",
        "Guardrails",
        *guardrail_lines,
    ]
    if top_opps:
        lines.extend(["", "Top opportunities", *[f"- {x}" for x in top_opps if x]])
    if blockers:
        lines.extend(["", "Known blockers", *[f"- {x}" for x in blockers[:3]]])
    return "\n".join(lines)[:MAX_TELEGRAM]


def _build_promotion_suggestions():
    brief_payload, _, context_payload = _resolve_assistant_payloads()
    decisions, blockers, next_actions, recent_progress = _parse_context_payload(context_payload)

    suggestions = []
    if decisions:
        suggestions.append(
            {"path": "core/current-state.md", "reason": "Decision terbaru berdampak lintas sesi."}
        )
    if recent_progress:
        suggestions.append(
            {"path": "domains/daily/notes.md", "reason": "Progress harian bisa hilang jika tidak dipromosikan."}
        )
    if next_actions:
        suggestions.append(
            {"path": "domains/work/current-project.md", "reason": "Next actions siap dijadikan durable plan."}
        )
    if blockers:
        suggestions.append(
            {
                "path": "domains/career/action-plan/next-actions.md",
                "reason": "Blocker butuh tindak lanjut terstruktur.",
            }
        )
    if _compact(brief_payload.get("focus_today")):
        suggestions.append(
            {
                "path": "domains/branding/content-topics/main-topics.md",
                "reason": "Fokus bisa jadi tema berulang.",
            }
        )
    return {
        "suggestions": suggestions[:5],
        "sections": {
            "decisions": decisions[:3],
            "blockers": blockers[:3],
            "next_actions": next_actions[:3],
            "recent_progress": recent_progress[:3],
            "focus_today": _compact(brief_payload.get("focus_today")),
        },
    }


def _build_promotion_message():
    suggestion_payload = _build_promotion_suggestions()
    suggestions = suggestion_payload.get("suggestions") or []

    lines = [
        "Promote Memory Suggestion",
        "",
        "Suggested Durable Updates",
    ]
    if suggestions:
        for item in suggestions:
            lines.append(f"- {item.get('path')}: {item.get('reason')}")
    else:
        lines.append("- Belum ada kandidat kuat dari artifact terbaru.")

    lines.extend(
        [
            "",
            "Target files",
            "- core/current-state.md",
            "- domains/daily/notes.md",
            "- domains/work/current-project.md",
            "- domains/career/action-plan/next-actions.md",
            "- domains/branding/content-topics/main-topics.md",
            "",
            "Why this should be promoted",
            "- Menjaga konteks durable lintas sesi assistant.",
            "",
            "What should NOT be promoted",
            "- Chat noise, asumsi mentah, dan detail sementara yang belum tervalidasi.",
            "",
            "Confidence",
            f"- {'medium' if suggestions else 'low'}",
            "",
            "Reminder",
            "- Suggest-only: no write performed.",
        ]
    )
    return "\n".join(lines)[:MAX_TELEGRAM]


def _load_controlled_write_runtime():
    runtime_module_root = _runtime_path() / "runtime"
    if str(runtime_module_root) not in sys.path:
        sys.path.insert(0, str(runtime_module_root))
    from assistant.write import apply_latest_draft, build_preview, generate_draft  # type: ignore

    return generate_draft, build_preview, apply_latest_draft


def _render_controlled_write_preview(preview):
    if not preview.get("ok"):
        warnings = preview.get("warnings") or ["preview unavailable"]
        return "\n".join(["Context Update Preview", "", "Warnings", *[f"- {_compact(x)}" for x in warnings]])[
            :MAX_TELEGRAM
        ]
    lines = [
        "Context Update Preview",
        "",
        f"Draft: {_compact(preview.get('draft_path'))}",
        "Targets",
    ]
    targets = preview.get("target_files") or []
    lines.extend([f"- {target}" for target in targets] or ["- Belum ada target."])
    lines.extend(["", "Proposed Additions"])
    for item in preview.get("items") or []:
        lines.append(f"- {item.get('target_path')}: {item.get('addition_preview')}")
    warnings = preview.get("warnings") or []
    if warnings:
        lines.extend(["", "Warnings", *[f"- {_compact(x)}" for x in warnings[:6]]])
    return "\n".join(lines)[:MAX_TELEGRAM]


def _build_insight_personalization():
    runtime_module_root = _runtime_path() / "runtime"
    if str(runtime_module_root) not in sys.path:
        sys.path.insert(0, str(runtime_module_root))
    try:
        from assistant.insight import build_personalized_insight  # type: ignore

        return build_personalized_insight(_runtime_path())
    except Exception:
        return {
            "relevant_insight": "Belum ada insight personal yang bisa dirender.",
            "why_it_matters_to_you": "Context atau insight artifact belum siap.",
            "paos_forge_relevance": "Belum tersedia.",
            "work_career_relevance": "Belum tersedia.",
            "content_opportunity": "Belum tersedia.",
            "recommended_action": "Jalankan /insight dan /context saat artifact sudah tersedia.",
        }


def _build_insight_relevance_message():
    payload = _build_insight_personalization()
    lines = [
        "Insight Relevance",
        "",
        "Relevant Insight",
        f"- {_compact(payload.get('relevant_insight'))}",
        "",
        "Why it matters to you",
        f"- {_compact(payload.get('why_it_matters_to_you'))}",
        "",
        "PAOS / Forge relevance",
        f"- {_compact(payload.get('paos_forge_relevance'))}",
        "",
        "Work / career relevance",
        f"- {_compact(payload.get('work_career_relevance'))}",
        "",
        "Content opportunity",
        f"- {_compact(payload.get('content_opportunity'))}",
        "",
        "Recommended action",
        f"- {_compact(payload.get('recommended_action'))}",
    ]
    return "\n".join(lines)[:MAX_TELEGRAM]


def _build_hermes_status_message() -> str:
    runtime_module_root = _runtime_path() / "runtime"
    if str(runtime_module_root) not in sys.path:
        sys.path.insert(0, str(runtime_module_root))

    try:
        from assistant.hermes import hermes_container_status  # type: ignore
        from assistant.hermes import hermes_mcp_paos_status  # type: ignore
        from assistant.hermes import hermes_orchestration_enabled  # type: ignore
        from assistant.hermes import hermes_provider_status  # type: ignore
        from assistant.hermes import hermes_timeout_seconds  # type: ignore

        orchestration_enabled = hermes_orchestration_enabled()
        container_status = hermes_container_status(timeout_seconds=4)
        mcp_status = hermes_mcp_paos_status(timeout_seconds=10)
        provider_status = hermes_provider_status(timeout_seconds=10)
        if not orchestration_enabled and provider_status in {"timeout", "unknown"}:
            provider_status = "not configured/unknown"
        timeout_seconds = hermes_timeout_seconds()
    except Exception:
        orchestration_enabled = False
        container_status = "unknown"
        mcp_status = "unknown"
        provider_status = "unknown"
        timeout_seconds = 45

    lines = [
        "Hermes Status",
        "",
        f"- Telegram orchestration enabled: {'true' if orchestration_enabled else 'false'}",
        "- Fallback enabled: true",
        f"- Hermes container: {container_status}",
        f"- MCP paos: {mcp_status}",
        f"- Inference provider: {provider_status}",
        f"- Hermes timeout seconds: {timeout_seconds}",
    ]
    return "\n".join(lines)[:MAX_TELEGRAM]


async def handle_memory(update):
    await update.message.reply_text(_build_memory_surface_message())


async def handle_handoff(update):
    text = _compact(update.message.text).lower()
    if text.startswith("/handoff codex"):
        target = "codex"
    elif text.startswith("/handoff claude"):
        target = "claude"
    elif text.startswith("/handoff hermes"):
        target = "hermes"
    else:
        target = "generic"
    await update.message.reply_text(_build_handoff_message(target=target))


async def handle_hermes_status(update):
    await update.message.reply_text(_build_hermes_status_message())


async def handle_promote_memory(update):
    await update.message.reply_text(_build_promotion_message())


async def handle_insight_relevance(update):
    await update.message.reply_text(_build_insight_relevance_message())


async def handle_draft_context_update(update):
    generate_draft, _, _ = _load_controlled_write_runtime()
    source = _build_promotion_suggestions()
    result = generate_draft(source.get("suggestions") or [], source.get("sections") or {})
    payload = result.get("payload") or {}
    warnings = payload.get("warnings") or []
    entries = payload.get("entries") or []
    lines = [
        "Context Update Draft",
        "",
        f"Draft path: {_compact(result.get('draft_path'))}",
        f"Entries: {len(entries)}",
    ]
    if entries:
        lines.extend(["Targets", *[f"- {item.get('target_path')}" for item in entries]])
    if warnings:
        lines.extend(["Warnings", *[f"- {_compact(x)}" for x in warnings[:6]]])
    lines.extend(["", "Next", "- Run /preview-context-update", "- Apply only with /apply-context-update CONFIRM"])
    await update.message.reply_text("\n".join(lines)[:MAX_TELEGRAM])


async def handle_preview_context_update(update):
    _, build_preview, _ = _load_controlled_write_runtime()
    preview = build_preview()
    await update.message.reply_text(_render_controlled_write_preview(preview))


async def handle_apply_context_update(update):
    _, _, apply_latest_draft = _load_controlled_write_runtime()
    text = _compact(update.message.text)
    token = text.split(" ", 1)[1] if " " in text else ""
    result = apply_latest_draft(token)
    if not result.get("ok"):
        warnings = result.get("warnings") or ["apply failed"]
        await update.message.reply_text(
            "\n".join(
                [
                    "Apply Context Update",
                    "",
                    "No changes applied.",
                    *[f"- {_compact(x)}" for x in warnings[:6]],
                    "",
                    "Usage: /apply-context-update CONFIRM",
                ]
            )[:MAX_TELEGRAM]
        )
        return
    lines = [
        "Apply Context Update",
        "",
        f"Applied: {'yes' if result.get('applied') else 'no'}",
        "Applied targets",
    ]
    lines.extend([f"- {x}" for x in (result.get("applied_targets") or [])] or ["- none"])
    blocked = result.get("blocked_targets") or []
    if blocked:
        lines.extend(["Blocked targets", *[f"- {item.get('target_path')}: {item.get('reason')}" for item in blocked]])
    warnings = result.get("warnings") or []
    if warnings:
        lines.extend(["Warnings", *[f"- {_compact(x)}" for x in warnings[:6]]])
    lines.extend(["Audit", f"- {_compact(result.get('audit_path'))}"])
    await update.message.reply_text("\n".join(lines)[:MAX_TELEGRAM])


async def handle_draft(update):
    runtime_module_root = _runtime_path() / "runtime"
    if str(runtime_module_root) not in sys.path:
        sys.path.insert(0, str(runtime_module_root))
    from assistant.actions import create_action_draft, render_action_draft_telegram  # type: ignore
    from assistant.mcp.server import tool_paos_action_policy_get  # type: ignore

    text = _compact(update.message.text).strip()
    lowered = text.lower()
    if lowered.startswith("/draft policy"):
        policy_payload = tool_paos_action_policy_get()
        policy = (policy_payload.get("sections") or {}).get("policy") or {}
        lines = [
            "PAOS Action Policy",
            "",
            "- status: Phase 4 Agentic Draft + Approval Boundary active",
            f"- version: {_compact(policy.get('version')) or 'phase4-draft-boundary-v1'}",
            f"- mode: {_compact(policy.get('mode')) or 'draft_only_boundary'}",
            f"- mutations_enabled: {'true' if policy.get('mutations_enabled') else 'false'}",
            f"- approval_apply_enabled: {'true' if policy.get('approval_apply_enabled') else 'false'}",
            "- next_step: final validation and commit of Phase 4",
            "",
            "No action was applied.",
        ]
        await update.message.reply_text("\n".join(lines)[:MAX_TELEGRAM])
        return

    intent = "next implementation plan draft"
    target = None
    if lowered.startswith("/draft daily"):
        intent = "daily action draft"
    elif lowered.startswith("/draft next"):
        intent = "next implementation plan draft"
    elif lowered.startswith("/draft memory"):
        intent = "memory promotion suggestion draft"
    elif lowered.startswith("/draft handoff"):
        intent = "handoff draft"
        if "codex" in lowered:
            target = "codex"
        elif "claude" in lowered:
            target = "claude"
        elif "hermes" in lowered:
            target = "hermes"

    payload = create_action_draft(intent=intent, target=target, category="ai")
    await update.message.reply_text(render_action_draft_telegram(payload))


async def handle_actions(update):
    runtime_module_root = _runtime_path() / "runtime"
    if str(runtime_module_root) not in sys.path:
        sys.path.insert(0, str(runtime_module_root))
    from assistant.action_loop import list_actions, render_action_list  # type: ignore

    text = _compact(update.message.text).lower()
    debug = text.startswith("/actions debug")
    accepted = list_actions(state="accepted", limit=1, remember_list=False)
    pending = [
        item for item in list_actions(limit=30, remember_list=False)
        if item.state in {"proposed", "deferred"} and not str(item.source).lower().startswith("e2e")
    ][:5]
    lines = [
        "PAOS /actions (fallback/admin)",
        "",
        "Normal usage: cukup natural-language (contoh: 'pilih nomor 1', 'accept yang tadi').",
        "",
    ]
    if accepted:
        lines.append(f"Latest accepted: {accepted[0].title} ({accepted[0].action_id})")
    else:
        lines.append("Latest accepted: belum ada.")
    lines.append("")
    lines.append(render_action_list(pending, title="Pending Actions"))
    if debug:
        lines.extend(["", f"Debug pending_count={len(pending)}"])
    await update.message.reply_text("\n".join(lines)[:MAX_TELEGRAM])
