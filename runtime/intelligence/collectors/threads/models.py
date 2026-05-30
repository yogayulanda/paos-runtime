import hashlib
import json
from datetime import datetime
from pathlib import Path

import yaml

from config import validate_source_categories
from collectors.threads.extractor import ROOT
from collectors.threads.extractor import compact_text
from collectors.threads.extractor import matched_keywords


CONFIG_PATH = ROOT / "runtime" / "intelligence" / "sources" / "threads.yaml"
RAW_BASE_DIR = ROOT / "intelligence" / "raw" / "threads"


def load_threads_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(
            "Threads source config is missing.\n"
            f"Expected file: {CONFIG_PATH}"
        )

    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}

    if payload.get("platform") != "threads":
        raise SystemExit("Threads source config must declare `platform: threads`.")

    categories = payload.get("categories") or {}
    limits = payload.get("limits") or {}

    if not isinstance(categories, dict) or not categories:
        raise SystemExit("Threads source config must include `categories`.")
    validate_source_categories("threads", list(categories.keys()))

    if not isinstance(limits, dict):
        raise SystemExit("Threads source config `limits` must be a mapping.")

    return payload


def iter_categories(config, selected_category=None):
    for category, details in (config.get("categories") or {}).items():
        if selected_category and category != selected_category:
            continue
        yield category, details or {}


def iter_accounts(config, selected_category=None):
    for category, details in iter_categories(config, selected_category=selected_category):
        accounts = (details or {}).get("accounts") or []
        if not isinstance(accounts, list):
            raise SystemExit(
                f"Threads source config categories.{category}.accounts must be a list."
            )
        for account in accounts:
            if not isinstance(account, dict):
                continue
            if not account.get("enabled", True):
                continue

            username = compact_text(account.get("username"))
            if not username:
                continue

            normalized = dict(account)
            normalized["username"] = username
            normalized["source_name"] = compact_text(
                account.get("source_name") or username
            )
            normalized["category"] = category
            yield normalized


def get_default_limit(config, source_type):
    limits = config.get("limits") or {}
    if source_type == "account":
        return int(limits.get("default_per_account", 10) or 10)
    return int(limits.get("default_per_keyword", 10) or 10)


def build_item(
    source_type,
    source_name,
    category,
    content,
    url="",
    author="",
    created_at="",
    raw=None,
    source_trust="keyword_discovery",
    keywords=None,
    relevance=None,
):
    collected_at = datetime.now().astimezone().isoformat()
    normalized_content = compact_text(content)
    normalized_keywords = matched_keywords(normalized_content, keywords or [])

    return {
        "platform": "threads",
        "source_type": source_type,
        "source_name": source_name,
        "category": category,
        "author": author or None,
        "content": normalized_content,
        "url": url or None,
        "created_at": created_at or None,
        "collected_at": collected_at,
        "signals": {
            "matched_keywords": normalized_keywords,
            "relevance_score": relevance,
            "source_trust": source_trust,
        },
        "raw": raw or {},
    }


def dedupe_key(item):
    if item.get("url"):
        return item["url"]

    digest = hashlib.sha256(
        "||".join(
            [
                item.get("platform") or "",
                item.get("source_type") or "",
                item.get("category") or "",
                item.get("content") or "",
            ]
        ).encode("utf-8")
    ).hexdigest()

    return digest


def storage_path(source_type, category, collected_at=None):
    collected_at = collected_at or datetime.now().astimezone()
    day = collected_at.strftime("%Y-%m-%d")
    return RAW_BASE_DIR / day / source_type / f"{category}.jsonl"


def write_items(items):
    written_paths = []
    grouped = {}

    for item in items:
        path = storage_path(item["source_type"], item["category"])
        grouped.setdefault(path, []).append(item)

    for path, bucket in grouped.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for item in bucket:
                handle.write(json.dumps(item, ensure_ascii=True) + "\n")
        written_paths.append(path)

    return written_paths
