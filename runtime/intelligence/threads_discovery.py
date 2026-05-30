import argparse
from datetime import datetime

from collectors.threads.extractor import ROOT
from collectors.threads.extractor import compact_text
from collectors.threads.extractor import default_provider
from collectors.threads.extractor import load_topics
from collectors.threads.extractor import normalize_post
from collectors.threads.extractor import relevance_score
from collectors.threads.extractor import resolve_adapter


RAW_DIR = ROOT / "intelligence" / "raw" / "threads"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Legacy topic-driven Threads discovery."
    )
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--query")
    query_group.add_argument(
        "--all-topics",
        action="store_true",
        help="Load topics from intelligence/topics.yaml and discover each one.",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-score", type=int, default=3)
    parser.add_argument(
        "--provider",
        choices=["official", "scraper", "playwright"],
        default=default_provider(),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the request plan without calling the Threads API.",
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

        metadata[key] = [] if value == "[]" else value
        index += 1

    return metadata, parts[2]


def load_existing_keys():
    ids = set()
    urls = set()

    for path in RAW_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(text)
        entry_id = metadata.get("id")
        entry_url = metadata.get("url")

        if entry_id:
            ids.add(entry_id)
        if entry_url:
            urls.add(entry_url)

    return ids, urls


def yaml_list(values):
    if not values:
        return "[]"

    lines = [""] + [f"  - {value}" for value in values]
    return "\n".join(lines)


def build_markdown(post, query):
    captured_at = datetime.now().astimezone().isoformat()
    tags = [token for token in query.lower().split() if token]
    text = compact_text(post.get("text"))
    extraction_mode = post.get("extraction_mode", "")
    discovered_via_query = post.get("discovered_via_query", "")

    return f"""---
id: {post['raw_id']}
source: threads
captured_at: {captured_at}
type: raw_intelligence
author: {post.get('username', '')}
url: {post.get('permalink', '')}
tags: {yaml_list(tags)}
extraction_mode: {extraction_mode}
discovered_via_query: {discovered_via_query}
signal_strength: unreviewed
promotion_status: raw
---

# Raw Content

{text}

# Why It Matters


# Possible Use

"""


def filter_relevant_posts(posts, query, min_score):
    accepted = []
    rejected_count = 0

    for post in posts:
        score = relevance_score(query, post.get("text", ""))
        post["relevance_score"] = score

        if score < min_score:
            rejected_count += 1
            continue

        accepted.append(post)

    return accepted, rejected_count


def filter_new_posts(posts, existing_ids, existing_urls):
    new_posts = []

    for post in posts:
        if post["raw_id"] in existing_ids:
            continue
        if post["permalink"] and post["permalink"] in existing_urls:
            continue
        new_posts.append(post)

    return new_posts


def save_posts(posts, query):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    for post in posts:
        output_path = RAW_DIR / f"{post['raw_id']}.md"
        output_path.write_text(
            build_markdown(post, query),
            encoding="utf-8",
        )
        saved_paths.append(output_path)

    return saved_paths


def run_query(adapter, query, limit, min_score, existing_ids, existing_urls):
    raw_posts = [normalize_post(post) for post in adapter.search(query, limit)]
    accepted_posts, rejected_count = filter_relevant_posts(
        raw_posts,
        query,
        min_score,
    )
    new_posts = filter_new_posts(
        accepted_posts,
        existing_ids,
        existing_urls,
    )
    saved_paths = save_posts(new_posts, query)

    for post in new_posts:
        existing_ids.add(post["raw_id"])
        if post["permalink"]:
            existing_urls.add(post["permalink"])

    return {
        "query": query,
        "raw_count": len(raw_posts),
        "accepted_count": len(accepted_posts),
        "rejected_count": rejected_count,
        "saved_paths": saved_paths,
        "error": "",
    }


def print_dry_run(query, limit, provider, min_score):
    print("Threads Discovery Dry Run")
    print(f"query: {query}")
    print(f"limit: {max(1, min(limit, 100))}")
    print(f"provider: {provider}")
    print(f"min_score: {min_score}")
    print(f"output_dir: {RAW_DIR}")


def main():
    args = parse_args()
    topics = [args.query]
    if args.all_topics:
        topics = load_topics()

    if args.dry_run:
        for topic in topics:
            print_dry_run(
                query=topic,
                limit=args.limit,
                provider=args.provider,
                min_score=args.min_score,
            )
        return

    adapter = resolve_adapter(args.provider)
    existing_ids, existing_urls = load_existing_keys()

    for topic in topics:
        print(f"Topic: {topic}")
        result = run_query(
            adapter,
            topic,
            args.limit,
            args.min_score,
            existing_ids,
            existing_urls,
        )
        print(
            "Summary: "
            f"raw={result['raw_count']} "
            f"accepted={result['accepted_count']} "
            f"rejected={result['rejected_count']} "
            f"saved={len(result['saved_paths'])}"
        )
        for path in result["saved_paths"]:
            print(path)


if __name__ == "__main__":
    main()
