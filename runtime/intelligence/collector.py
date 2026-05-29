import argparse
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "intelligence" / "raw"
SOURCES = {"manual", "threads"}


def parse_tags(value):
    if not value:
        return []

    return [
        tag.strip()
        for tag in value.split(",")
        if tag.strip()
    ]


def yaml_list(values):
    if not values:
        return "[]"

    lines = [""] + [f"  - {value}" for value in values]
    return "\n".join(lines)


def build_markdown(args, captured_at):
    tags = parse_tags(args.tags)

    return f"""---
source: {args.source}
captured_at: {captured_at.isoformat()}
type: raw_intelligence
author: {args.author or ""}
url: {args.url or ""}
tags: {yaml_list(tags)}
signal_strength: unreviewed
promotion_status: raw
---

# Raw Content

{args.text}

# Why It Matters


# Possible Use

"""


def collect(args):
    captured_at = datetime.now().astimezone()
    filename = captured_at.strftime(
        f"%Y-%m-%d-%H%M%S-{args.source}.md"
    )

    output_dir = RAW_DIR / args.source
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / filename
    output_path.write_text(
        build_markdown(args, captured_at),
        encoding="utf-8",
    )

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Capture raw PAOS intelligence as Markdown."
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=sorted(SOURCES),
    )
    parser.add_argument("--text", required=True)
    parser.add_argument("--url")
    parser.add_argument("--author")
    parser.add_argument(
        "--tags",
        help="Comma-separated tags.",
    )

    args = parser.parse_args()
    output_path = collect(args)

    print(output_path)


if __name__ == "__main__":
    main()
