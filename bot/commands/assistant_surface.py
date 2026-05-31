import json
import re
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
    return Path(env.get("PAOS_RUNTIME_PATH", "/home/ubuntu/paos/paos-runtime"))


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
