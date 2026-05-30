import hashlib


def compact_text(value):
    return " ".join(str(value or "").split())


def content_hash(item):
    payload = "||".join(
        [
            compact_text(item.get("platform")),
            compact_text(item.get("category")),
            compact_text(item.get("source_type")),
            compact_text(item.get("source_name")),
            compact_text(item.get("author")),
            compact_text(item.get("content")),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_candidates(items):
    unique_items = []
    seen_urls = set()
    seen_hashes = set()
    duplicate_urls = 0
    duplicate_content = 0

    for item in items:
        url = item.get("url")
        if url:
            if url in seen_urls:
                duplicate_urls += 1
                continue
            seen_urls.add(url)

        digest = content_hash(item)
        if digest in seen_hashes:
            duplicate_content += 1
            continue
        seen_hashes.add(digest)

        unique_items.append(item)

    diagnostics = {
        "duplicate_urls_removed": duplicate_urls,
        "duplicate_content_removed": duplicate_content,
    }
    return unique_items, diagnostics
