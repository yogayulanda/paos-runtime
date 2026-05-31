from pathlib import Path

from context.loader import load_env
from bot.commands.intelligence import _compact
from bot.commands.intelligence import _resolve_latest_markdown_path
from bot.commands.intelligence import parse_markdown_sections

MAX_TELEGRAM = 3900


def _resolve_latest_digest_path(runtime_path, category="ai"):
    digest_root = runtime_path / "intelligence" / "digests"
    return _resolve_latest_markdown_path(digest_root, category=category)


def _extract_key_signal_titles(body, limit=5):
    titles = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("### "):
            continue
        title = _compact(stripped[4:])
        if ". " in title[:4]:
            prefix, rest = title.split(". ", 1)
            if prefix.isdigit():
                title = _compact(rest)
        if title:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def _extract_source_coverage_lines(body, limit=3):
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("* "):
            lines.append(_compact(stripped[2:]))
        if len(lines) >= limit:
            break
    return lines


def _build_digest_message(path):
    markdown_text = Path(path).read_text(encoding="utf-8")
    sections = parse_markdown_sections(markdown_text)
    summary = _compact(sections.get("Executive Summary", "")) or "Belum ada ringkasan digest."
    signals = _extract_key_signal_titles(sections.get("Key Signals", ""), limit=5)
    coverage = _extract_source_coverage_lines(sections.get("Source Coverage", ""), limit=3)

    lines = ["🧠 PAOS Digest", "", "Ringkasan", summary, "", "Key Signals"]
    if signals:
        lines.extend([f"{index}. {title}" for index, title in enumerate(signals, start=1)])
    else:
        lines.append("Belum ada sinyal utama.")
    if coverage:
        lines.extend(["", "Source Coverage"])
        lines.extend([f"- {item}" for item in coverage])
    return "\n".join(lines)[:MAX_TELEGRAM]


async def handle_digest(update):
    env = load_env()
    runtime_path = env.get(
        "PAOS_RUNTIME_PATH",
        "/home/ubuntu/paos/paos-runtime",
    )
    digest_path = _resolve_latest_digest_path(Path(runtime_path), category="ai")
    if not digest_path:
        await update.message.reply_text("Belum ada digest. Jalankan /update dulu.")
        return
    await update.message.reply_text(_build_digest_message(digest_path))
