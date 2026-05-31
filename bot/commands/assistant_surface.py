import json
from datetime import datetime
from pathlib import Path

from context.loader import load_env


MAX_OPPORTUNITIES = 5
MAX_TELEGRAM = 3900


def _compact(value):
    return " ".join(str(value or "").split())


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


def _render_brief_message(payload):
    focus = _compact(payload.get("focus_today")) or "Belum ada fokus hari ini."
    next_action = _compact(payload.get("suggested_next_action")) or "Belum ada suggested next action."

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
        focus,
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
    lines.append(f"Menampilkan {len(limited)} dari {len(opportunities)} peluang terbaru.")

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
