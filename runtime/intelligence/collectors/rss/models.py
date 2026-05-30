import json
from datetime import datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = ROOT / "runtime" / "intelligence" / "sources" / "rss.yaml"
RAW_BASE_DIR = ROOT / "intelligence" / "raw" / "rss"


def compact_text(value):
    return " ".join(str(value or "").split())


def load_rss_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(
            "RSS source config is missing.\n"
            f"Expected file: {CONFIG_PATH}"
        )

    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if payload.get("platform") != "rss":
        raise SystemExit("RSS source config must declare `platform: rss`.")
    return payload


def iter_feeds(config, selected_category=None):
    categories = set((config.get("categories") or {}).keys())
    for feed in config.get("feeds") or []:
        if not isinstance(feed, dict):
            continue
        if not feed.get("enabled", True):
            continue
        category = compact_text(feed.get("category"))
        if category not in categories:
            continue
        if selected_category and category != selected_category:
            continue
        if not compact_text(feed.get("url")) or not compact_text(feed.get("name")):
            continue
        yield feed


def get_default_limit(config):
    return int(((config.get("limits") or {}).get("default_per_feed", 5)) or 5)


def storage_path(category, collected_at=None):
    collected_at = collected_at or datetime.now().astimezone()
    day = collected_at.strftime("%Y-%m-%d")
    return RAW_BASE_DIR / day / "feed" / f"{category}.jsonl"


def write_items(items):
    written_paths = []
    grouped = {}

    for item in items:
        path = storage_path(item["category"])
        grouped.setdefault(path, []).append(item)

    for path, bucket in grouped.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for item in bucket:
                handle.write(json.dumps(item, ensure_ascii=True) + "\n")
        written_paths.append(path)

    return written_paths
