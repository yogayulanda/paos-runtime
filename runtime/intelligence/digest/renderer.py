from collections import Counter
from datetime import datetime


def compact_text(value):
    return " ".join(str(value or "").split())


def unique_ordered(values):
    seen = set()
    ordered = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def render_sources(signal):
    sources = signal.get("sources") or []
    accounts = signal.get("source_accounts") or []
    urls = signal.get("source_urls") or []
    lines = []
    if sources:
        for source in sources:
            lines.append(
                "* "
                f"{compact_text(source.get('platform'))} / "
                f"{compact_text(source.get('source_type'))} / "
                f"{compact_text(source.get('source_name'))} / "
                f"{compact_text(source.get('url'))}"
            )
        return "\n".join(lines)
    if accounts:
        lines.append(f"* accounts: {', '.join(accounts)}")
    for url in urls:
        lines.append(f"* url: {url}")
    if not accounts and not urls:
        lines.append("* No sources")
    return "\n".join(lines)


def build_executive_summary(signals):
    if not signals:
        return "No signals were generated for this category."
    lead = signals[0]
    return (
        f"{len(signals)} signals were generated today. "
        f"The strongest lead signal is `{lead.get('title', 'Untitled')}` under `{lead.get('theme', 'Other')}`, "
        "with the rest of the digest grouped around recurring product, tooling, and agent-workflow patterns."
    )


def build_emerging_themes(signals):
    counter = Counter(signal.get("theme") or "Other" for signal in signals)
    return [theme for theme, _count in counter.most_common(3)]


def build_recommended_reading(signals, limit=5):
    items = []
    for signal in signals[:limit]:
        sources = signal.get("sources") or []
        urls = signal.get("source_urls") or []
        accounts = signal.get("source_accounts") or []
        if not urls and not sources:
            continue
        first_source = sources[0] if sources else {}
        items.append(
            {
                "title": signal.get("title", "Untitled"),
                "platform": compact_text(first_source.get("platform")) if first_source else "",
                "source_type": compact_text(first_source.get("source_type")) if first_source else "",
                "source_name": compact_text(first_source.get("source_name")) if first_source else "",
                "accounts": ", ".join(accounts) if accounts else "unknown",
                "url": compact_text(first_source.get("url")) or urls[0],
            }
        )
    return items


def source_coverage(signals):
    accounts = unique_ordered(
        account
        for signal in signals
        for account in (signal.get("source_accounts") or [])
    )
    urls = unique_ordered(
        url
        for signal in signals
        for url in (signal.get("source_urls") or [])
    )
    source_records = unique_ordered(
        " / ".join(
            [
                compact_text(source.get("platform")),
                compact_text(source.get("source_type")),
                compact_text(source.get("source_name")),
                compact_text(source.get("url")),
            ]
        )
        for signal in signals
        for source in (signal.get("sources") or [])
    )
    return {
        "signals_generated": len(signals),
        "source_accounts": len(accounts),
        "source_urls": len(urls),
        "sources": len(source_records),
    }


def render_digest(category, date, signals):
    generated_at = datetime.now().astimezone().isoformat()
    summary = build_executive_summary(signals)
    themes = build_emerging_themes(signals)
    reading = build_recommended_reading(signals)
    coverage = source_coverage(signals)

    lines = [
        "# AI Intelligence Digest",
        "",
        f"Generated At: {generated_at}",
        f"Category: {category}",
        f"Date: {date}",
        "",
        "## Executive Summary",
        "",
        summary,
        "",
        "## Key Signals",
        "",
    ]

    if not signals:
        lines.extend(["No signals available.", ""])
    else:
        for index, signal in enumerate(signals, start=1):
            lines.extend(
                [
                    f"### {index}. {signal.get('title', 'Untitled')}",
                    "",
                    f"Theme: {signal.get('theme', 'Other')}",
                    "",
                    f"Summary: {compact_text(signal.get('summary'))}",
                    "",
                    f"Why it matters: {compact_text(signal.get('why_it_matters'))}",
                    "",
                    "Sources:",
                    "",
                    render_sources(signal),
                    "",
                ]
            )

    lines.extend(
        [
            "## Emerging Themes",
            "",
        ]
    )
    if themes:
        lines.extend([f"* {theme}" for theme in themes])
    else:
        lines.append("* None")

    lines.extend(["", "## Recommended Reading", ""])
    if reading:
        for item in reading:
            if item["platform"] or item["source_type"] or item["source_name"]:
                lines.append(
                    f"* {item['title']} / "
                    f"{item['platform']} / {item['source_type']} / {item['source_name']} / "
                    f"{item['url']}"
                )
            else:
                lines.append(f"* {item['title']} / accounts: {item['accounts']} / {item['url']}")
    else:
        lines.append("* None")

    lines.extend(
        [
            "",
            "## Source Coverage",
            "",
            f"* signals_generated: {coverage['signals_generated']}",
            f"* source_accounts: {coverage['source_accounts']}",
            f"* source_urls: {coverage['source_urls']}",
            f"* sources: {coverage['sources']}",
            "",
        ]
    )
    return "\n".join(lines)
