import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "intelligence" / "raw"
DIGEST_DIR = ROOT / "intelligence" / "digests"
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "v1",
    "with",
}
PROJECT_KEYWORDS = {
    "PAOS": {"paos", "runtime", "intelligence", "digest"},
    "Forge": {"forge", "product", "build", "system"},
    "Career": {"career", "role", "hiring", "job", "market"},
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a PAOS intelligence digest."
    )
    parser.add_argument(
        "--date",
        help="Only include raw intelligence captured on YYYY-MM-DD.",
    )
    return parser.parse_args()


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text

    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text

    metadata = {}
    lines = parts[1].splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        if ":" not in line:
            index += 1
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            items = []
            index += 1

            while index < len(lines):
                item_line = lines[index]

                if item_line.startswith("  - "):
                    items.append(item_line[4:].strip())
                    index += 1
                    continue

                break

            metadata[key] = items
            continue

        if value == "[]":
            metadata[key] = []
        else:
            metadata[key] = value

        index += 1

    return metadata, parts[2]


def extract_section(body, heading):
    pattern = rf"^# {re.escape(heading)}\s*$"
    match = re.search(pattern, body, flags=re.MULTILINE)
    if not match:
        return ""

    start = match.end()
    next_match = re.search(r"^# .+$", body[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(body)

    return body[start:end].strip()


def tokenize(text):
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text.lower())
    return [
        word for word in words
        if len(word) > 2 and word not in STOP_WORDS
    ]


def load_entries(target_date):
    entries = []

    for path in sorted(RAW_DIR.glob("**/*.md")):
        if path.name == ".gitkeep":
            continue

        text = path.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(text)
        captured_at = metadata.get("captured_at", "")
        entry_date = captured_at[:10] if captured_at else ""

        if target_date and entry_date != target_date:
            continue

        raw_content = extract_section(body, "Raw Content")
        why_it_matters = extract_section(body, "Why It Matters")
        possible_use = extract_section(body, "Possible Use")
        combined_text = "\n".join(
            part for part in [
                raw_content,
                why_it_matters,
                possible_use,
            ] if part
        )

        entries.append(
            {
                "path": path,
                "metadata": metadata,
                "entry_date": entry_date,
                "raw_content": raw_content,
                "why_it_matters": why_it_matters,
                "possible_use": possible_use,
                "tokens": tokenize(combined_text),
            }
        )

    return entries


def unique_ordered(values):
    seen = set()
    ordered = []

    for value in values:
        if not value or value in seen:
            continue

        seen.add(value)
        ordered.append(value)

    return ordered


def build_strong_signals(entries):
    signals = []

    for entry in entries:
        metadata = entry["metadata"]
        source = metadata.get("source", "unknown")
        tags = metadata.get("tags", [])
        summary = entry["raw_content"] or entry["why_it_matters"] or "No content."
        summary = summary.splitlines()[0].strip()
        tag_text = ", ".join(tags) if tags else "none"

        signals.append(
            f"- [{source}] {summary} (tags: {tag_text})"
        )

    return signals or ["- No strong signals captured."]


def build_repeated_themes(entries):
    tag_counter = Counter()
    keyword_counter = Counter()

    for entry in entries:
        tag_counter.update(entry["metadata"].get("tags", []))
        keyword_counter.update(entry["tokens"])

    lines = []

    for tag, count in tag_counter.most_common(5):
        if count >= 1:
            lines.append(f"- Tag `{tag}` appeared {count} time(s).")

    for keyword, count in keyword_counter.most_common(5):
        if count >= 2:
            lines.append(
                f"- Keyword `{keyword}` repeated {count} time(s)."
            )

    return unique_ordered(lines) or ["- No repeated themes detected yet."]


def build_emerging_trends(entries):
    source_counter = Counter(
        entry["metadata"].get("source", "unknown")
        for entry in entries
    )
    tag_counter = Counter()

    for entry in entries:
        tag_counter.update(entry["metadata"].get("tags", []))

    lines = []

    for source, count in source_counter.most_common():
        lines.append(
            f"- Source `{source}` contributed {count} signal(s) today."
        )

    for tag, count in tag_counter.most_common(3):
        lines.append(
            f"- Tag `{tag}` is active across {count} signal(s)."
        )

    # TODO: Add simple rolling-window comparison across prior digest dates.
    return unique_ordered(lines) or ["- No emerging trends yet."]


def build_project_relevance(entries, project_name):
    keywords = PROJECT_KEYWORDS[project_name]
    lines = []

    for entry in entries:
        matched = keywords.intersection(entry["tokens"])
        if not matched:
            continue

        summary = entry["raw_content"] or "No content."
        summary = summary.splitlines()[0].strip()
        matched_text = ", ".join(sorted(matched))
        lines.append(
            f"- {summary} (matched: {matched_text})"
        )

    return lines or ["- No clear match."]


def build_potential_actions(entries):
    actions = []

    for entry in entries:
        if entry["possible_use"]:
            action = entry["possible_use"].splitlines()[0].strip()
            actions.append(f"- {action}")
            continue

        summary = entry["raw_content"] or "Review signal manually."
        summary = summary.splitlines()[0].strip()
        actions.append(
            f"- Review and classify: {summary}"
        )

    # TODO: Add rule-based action templates per tag cluster.
    return unique_ordered(actions) or ["- No actions proposed."]


def build_promotion_candidates(entries):
    lines = []

    for entry in entries:
        metadata = entry["metadata"]
        tags = metadata.get("tags", [])

        if tags or entry["why_it_matters"] or entry["possible_use"]:
            lines.append(f"- {entry['path'].name}")

    # TODO: Add scoring to separate digest candidates from archive-only noise.
    return lines or ["- No promotion candidates."]


def build_ignore_noise(entries):
    lines = []

    for entry in entries:
        metadata = entry["metadata"]
        tags = metadata.get("tags", [])
        has_context = entry["why_it_matters"] or entry["possible_use"]

        if not tags and not has_context:
            lines.append(
                f"- {entry['path'].name}: missing tags and interpretation."
            )

    return lines or ["- No obvious noise."]


def resolve_digest_date(entries, requested_date):
    if requested_date:
        return requested_date

    dated_entries = [entry["entry_date"] for entry in entries if entry["entry_date"]]
    if dated_entries:
        return max(dated_entries)

    return datetime.now().astimezone().date().isoformat()


def render_digest(digest_date, entries):
    lines = [
        f"# Intelligence Digest - {digest_date}",
        "",
        "## Strong Signals",
        "",
        *build_strong_signals(entries),
        "",
        "## Repeated Themes",
        "",
        *build_repeated_themes(entries),
        "",
        "## Emerging Trends",
        "",
        *build_emerging_trends(entries),
        "",
        "## Relevant To Current Projects",
        "",
        "### PAOS",
        "",
        *build_project_relevance(entries, "PAOS"),
        "",
        "### Forge",
        "",
        *build_project_relevance(entries, "Forge"),
        "",
        "### Career",
        "",
        *build_project_relevance(entries, "Career"),
        "",
        "## Potential Actions",
        "",
        *build_potential_actions(entries),
        "",
        "## Promotion Candidates",
        "",
        *build_promotion_candidates(entries),
        "",
        "## Ignore / Noise",
        "",
        *build_ignore_noise(entries),
        "",
    ]

    return "\n".join(lines)


def write_digest(digest_date, content):
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DIGEST_DIR / f"{digest_date}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def main():
    args = parse_args()
    entries = load_entries(args.date)
    digest_date = resolve_digest_date(entries, args.date)
    content = render_digest(digest_date, entries)
    output_path = write_digest(digest_date, content)
    print(output_path)


if __name__ == "__main__":
    main()
