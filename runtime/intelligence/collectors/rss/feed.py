import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from config import is_source_enabled
from collectors.rss.models import compact_text
from collectors.rss.models import get_default_limit
from collectors.rss.models import iter_feeds
from collectors.rss.models import load_rss_config
from collectors.rss.models import write_items
from source_age_rules import evaluate_source_item_age
from source_age_rules import get_source_age_rule


USER_AGENT = "PAOS-Intelligence/1.0"


def strip_html(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return compact_text(text)


def first_text(element, names, namespaces=None):
    namespaces = namespaces or {}
    for name in names:
        found = element.find(name, namespaces)
        if found is not None and compact_text(found.text):
            return compact_text(found.text)
    return ""


def parse_rss(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    if root.tag.endswith("rss") or root.tag == "rss":
        for item in root.findall("./channel/item"):
            title = first_text(item, ["title"])
            link = first_text(item, ["link"])
            summary = first_text(item, ["description", "content:encoded"], namespaces)
            published = first_text(item, ["pubDate", "dc:date"], namespaces)
            entry_id = first_text(item, ["guid"]) or link
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": strip_html(summary),
                    "published_at": published,
                    "entry_id": entry_id,
                }
            )
        return items

    if root.tag.endswith("feed"):
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            title = first_text(entry, ["{http://www.w3.org/2005/Atom}title"])
            link = ""
            for link_el in entry.findall("{http://www.w3.org/2005/Atom}link"):
                href = compact_text(link_el.attrib.get("href"))
                rel = compact_text(link_el.attrib.get("rel"))
                if href and (not rel or rel == "alternate"):
                    link = href
                    break
            summary = first_text(
                entry,
                [
                    "{http://www.w3.org/2005/Atom}summary",
                    "{http://www.w3.org/2005/Atom}content",
                ],
            )
            published = first_text(
                entry,
                [
                    "{http://www.w3.org/2005/Atom}updated",
                    "{http://www.w3.org/2005/Atom}published",
                ],
            )
            entry_id = first_text(entry, ["{http://www.w3.org/2005/Atom}id"]) or link
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": strip_html(summary),
                    "published_at": published,
                    "entry_id": entry_id,
                }
            )
        return items

    return []


def dedupe_key(item):
    if item.get("url"):
        return item["url"]
    digest = hashlib.sha256(
        "||".join(
            [
                item.get("source_name") or "",
                item.get("title") or "",
                item.get("content") or "",
            ]
        ).encode("utf-8")
    ).hexdigest()
    return digest


def normalize_feed_item(feed, entry):
    collected_at = datetime.now().astimezone().isoformat()
    title = compact_text(entry.get("title"))
    summary = compact_text(entry.get("summary"))
    if not title and not summary:
        return None
    return {
        "platform": "rss",
        "source_type": "feed",
        "source_name": compact_text(feed.get("name")),
        "category": compact_text(feed.get("category")),
        "author": None,
        "title": title or None,
        "content": summary or title,
        "url": compact_text(entry.get("url")) or None,
        "published_at": compact_text(entry.get("published_at")) or None,
        "collected_at": collected_at,
        "raw_metadata": {
            "feed_url": compact_text(feed.get("url")),
            "entry_id": compact_text(entry.get("entry_id")),
            "summary": summary,
            "reason": compact_text(feed.get("reason")),
        },
    }


def collect_rss_feeds(category=None, timeout_seconds=20):
    if category and not is_source_enabled(category, "rss"):
        raise SystemExit(f"Source family `rss` is disabled for category `{category}`.")
    config = load_rss_config()
    items = []
    errors = []
    skipped = []
    stats = {
        "feeds_loaded": 0,
        "feeds_succeeded": 0,
        "feeds_failed": 0,
        "raw_items": 0,
        "collected": 0,
        "written": 0,
        "skipped_too_old": 0,
        "skipped_missing_time": 0,
        "skipped_invalid_time": 0,
        "accepted_items": 0,
    }
    seen = set()
    rule = get_source_age_rule(category=category, source_family="rss") if category else None

    for feed in iter_feeds(config, selected_category=category):
        stats["feeds_loaded"] += 1
        limit = int(feed.get("limit") or get_default_limit(config))
        try:
            response = requests.get(
                feed["url"],
                timeout=timeout_seconds,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            entries = parse_rss(response.text)
            stats["raw_items"] += len(entries)
            accepted = 0
            for entry in entries[:limit]:
                stats["collected"] += 1
                decision = evaluate_source_item_age(entry.get("published_at"), rule)
                if not decision.accepted:
                    if decision.reason == "too_old":
                        stats["skipped_too_old"] += 1
                    elif decision.reason == "missing_time":
                        stats["skipped_missing_time"] += 1
                    elif decision.reason == "invalid_time":
                        stats["skipped_invalid_time"] += 1
                    continue
                item = normalize_feed_item(feed, entry)
                if not item:
                    continue
                key = dedupe_key(item)
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
                accepted += 1
                stats["written"] += 1
            stats["accepted_items"] += accepted
            stats["feeds_succeeded"] += 1
            if accepted == 0:
                skipped.append(f"{feed['name']} no usable feed entries")
        except Exception as exc:
            stats["feeds_failed"] += 1
            errors.append(
                {
                    "source_type": "feed",
                    "source_name": compact_text(feed.get("name")),
                    "code": "FEED_FETCH_FAILED",
                    "message": str(exc),
                }
            )

    paths = write_items(items) if items else []
    return {
        "items": items,
        "paths": paths,
        "stats": stats,
        "errors": errors,
        "skipped": skipped,
    }
