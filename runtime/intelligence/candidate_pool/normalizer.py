import re

from candidate_pool.models import NORMALIZATION_VERSION


UI_NOISE_PHRASES = [
    "For you",
    "New thread",
    "Search",
    "Messages",
    "Activity",
    "Profile",
    "Insights",
    "Saved",
    "Feeds",
    "Edit",
    "Ghost posts",
    "No replies yet",
    "View activity",
    "Some replies have been hidden. See all",
]

UI_NOISE_REGEXES = [
    re.compile(r"\bReply to\s+@?[A-Za-z0-9._]+\.\.\.", re.IGNORECASE),
    re.compile(r"\bReply to\s+@?[A-Za-z0-9._-]+\b", re.IGNORECASE),
]


def compact_text(value):
    return " ".join(str(value or "").split())


def canonicalize_threads_url(url):
    value = compact_text(url)
    if not value:
        return None

    value = value.split("?", 1)[0].rstrip("/")
    if value.endswith("/media"):
        value = value[: -len("/media")]
    return value or None


def strip_known_noise(text):
    cleaned = str(text or "")
    removed = 0

    for phrase in UI_NOISE_PHRASES:
        if phrase in cleaned:
            cleaned = cleaned.replace(phrase, " ")
            removed += 1

    for pattern in UI_NOISE_REGEXES:
        cleaned, count = pattern.subn(" ", cleaned)
        removed += count

    cleaned = compact_text(cleaned)
    return cleaned, removed


def looks_empty(text):
    return not compact_text(text)


def build_candidate_metadata(item, policy_name, policy_version, filter_mode, source_trust):
    return {
        "source_trust": source_trust or ((item.get("signals") or {}).get("source_trust") or ""),
        "duplicate_removed": False,
        "normalization_version": NORMALIZATION_VERSION,
        "policy": policy_name,
        "policy_version": policy_version,
        "filter_mode": filter_mode,
    }


def normalize_threads_account_item(
    item,
    policy_name="threads_account",
    policy_version="v1",
    filter_mode="noise_only",
    source_trust="mapped_account",
):
    content, removed_noise_count = strip_known_noise(item.get("content", ""))
    author = compact_text(item.get("author"))
    source_name = compact_text(item.get("source_name"))

    if author and content.startswith(f"{author} "):
        content = compact_text(content[len(author) :])

    if source_name and content.startswith(f"{source_name} "):
        content = compact_text(content[len(source_name) :])

    if looks_empty(content):
        return None, {
            "dropped": True,
            "reason": "empty_content",
            "removed_noise_count": removed_noise_count,
        }

    normalized = {
        "platform": compact_text(item.get("platform")) or "threads",
        "category": compact_text(item.get("category")),
        "source_type": compact_text(item.get("source_type")),
        "source_name": source_name,
        "author": author or None,
        "content": content,
        "url": canonicalize_threads_url(item.get("url")),
        "created_at": item.get("created_at") or None,
        "collected_at": item.get("collected_at") or None,
        "candidate_metadata": build_candidate_metadata(
            item=item,
            policy_name=policy_name,
            policy_version=policy_version,
            filter_mode=filter_mode,
            source_trust=source_trust,
        ),
    }
    return normalized, {
        "dropped": False,
        "reason": None,
        "removed_noise_count": removed_noise_count,
    }
