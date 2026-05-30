import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "intelligence" / "raw"
DIGEST_DIR = ROOT / "intelligence" / "digests"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a provider-agnostic PAOS AI digest prompt."
    )
    parser.add_argument(
        "--date",
        help="Only include raw intelligence captured on YYYY-MM-DD.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the full prompt and do not generate files.",
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
            next_index = index + 1

            if next_index < len(lines) and lines[next_index].startswith("  - "):
                items = []
                index = next_index

                while index < len(lines):
                    item_line = lines[index]

                    if item_line.startswith("  - "):
                        items.append(item_line[4:].strip())
                        index += 1
                        continue

                    break

                metadata[key] = items
                continue

            metadata[key] = ""
            index += 1
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


def resolve_entry_id(path, metadata):
    if metadata.get("id"):
        return metadata["id"]

    return path.stem


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

        entries.append(
            {
                "id": resolve_entry_id(path, metadata),
                "path": path,
                "metadata": metadata,
                "entry_date": entry_date,
                "raw_content": extract_section(body, "Raw Content"),
                "why_it_matters": extract_section(body, "Why It Matters"),
                "possible_use": extract_section(body, "Possible Use"),
            }
        )

    return entries


def resolve_digest_date(entries, requested_date):
    if requested_date:
        return requested_date

    dated_entries = [entry["entry_date"] for entry in entries if entry["entry_date"]]
    if dated_entries:
        return max(dated_entries)

    return datetime.now().astimezone().date().isoformat()


def build_digest_context(entries, digest_date):
    lines = [
        f"Digest date: {digest_date}",
        f"Target output path: {DIGEST_DIR / (digest_date + '.md')}",
        f"Raw intelligence entry count: {len(entries)}",
        "",
        "Raw intelligence entries:",
    ]

    if not entries:
        lines.append("- None")
        return "\n".join(lines)

    for entry in entries:
        metadata = entry["metadata"]
        tags = metadata.get("tags", [])
        tags_text = ", ".join(tags) if tags else "none"
        source = metadata.get("source", "unknown")
        author = metadata.get("author", "")
        url = metadata.get("url", "")

        lines.extend(
            [
                "",
                f"- id: {entry['id']}",
                f"  path: {entry['path']}",
                f"  source: {source}",
                f"  captured_at: {metadata.get('captured_at', '')}",
                f"  author: {author}",
                f"  url: {url}",
                f"  tags: {tags_text}",
                "  raw_content:",
                indent_block(entry["raw_content"] or "None"),
                "  why_it_matters:",
                indent_block(entry["why_it_matters"] or "None"),
                "  possible_use:",
                indent_block(entry["possible_use"] or "None"),
            ]
        )

    return "\n".join(lines)


def indent_block(text):
    return "\n".join(f"    {line}" for line in text.splitlines())


def build_digest_prompt(digest_date, context):
    return f"""You are generating a PAOS AI Digest from raw intelligence entries.

Focus on meaning and relationships between signals, not frequency counts.

Use only the provided raw intelligence context. Do not invent facts, dates, or references that are not present in the source entries.

Produce the digest in Markdown using exactly this structure:

# Intelligence Digest - {digest_date}

## Key Insights

## Repeated Themes

## Emerging Trends

## Relevant To PAOS

## Relevant To Forge

## Potential Actions

## Promotion Candidates

Writing guidance:
- Synthesize connections across entries where relevant.
- Prefer concise, high-signal bullets.
- Call out uncertainty when evidence is thin.
- Promotion Candidates should reference raw intelligence ids.
- Potential Actions should be specific and grounded in the source material.
- Relevant sections should explain why the signals matter to that area.

Raw intelligence context:

{context}
"""


def main():
    args = parse_args()
    entries = load_entries(args.date)
    digest_date = resolve_digest_date(entries, args.date)
    prompt = build_digest_prompt(
        digest_date,
        build_digest_context(entries, digest_date),
    )

    if args.dry_run:
        print(prompt)
        return

    # TODO: Add provider adapter for OpenAI-compatible chat completion APIs.
    # TODO: Add provider adapter for Claude message APIs.
    # TODO: Add provider adapter for OpenRouter provider routing.
    # TODO: Add provider adapter for local model execution.
    print(
        "AI digest model invocation is not implemented yet. "
        f"Target output path: {DIGEST_DIR / (digest_date + '.md')}",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
