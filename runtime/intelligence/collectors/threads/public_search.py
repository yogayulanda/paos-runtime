from collectors.threads.extractor import build_error
from collectors.threads.extractor import classify_threads_error
from collectors.threads.extractor import normalize_post
from collectors.threads.extractor import relevance_score
from collectors.threads.models import build_item
from collectors.threads.models import dedupe_key
from collectors.threads.models import get_default_limit
from collectors.threads.models import iter_categories
from collectors.threads.models import load_threads_config
from collectors.threads.models import write_items


def collect_keyword_discovery(
    adapter,
    limit=None,
    min_score=3,
    category=None,
    debug=False,
):
    config = load_threads_config()
    run_seen = set()
    items = []
    stats = {
        "categories_processed": 0,
        "queries_processed": 0,
        "raw_posts": 0,
        "accepted_posts": 0,
        "rejected_posts": 0,
        "deduped_posts": 0,
    }
    debug_events = []
    errors = []

    for category_name, details in iter_categories(config, category):
        stats["categories_processed"] += 1
        keywords = details.get("keywords") or []
        per_keyword_limit = limit or get_default_limit(config, "keyword")

        for keyword in keywords:
            stats["queries_processed"] += 1
            raw_posts = []
            message = None
            event_batch = []
            try:
                raw_posts = [
                    normalize_post(post)
                    for post in adapter.search(keyword, per_keyword_limit)
                ]
            except SystemExit as exc:
                message = str(exc)
            finally:
                event_batch = adapter.consume_debug_events()
                if debug:
                    debug_events.extend(event_batch)
            if message:
                latest_event = event_batch[-1] if event_batch else {}
                errors.append(
                    build_error(
                        source_type="keyword",
                        source_name=keyword,
                        code=classify_threads_error(
                            message,
                            diagnostics=latest_event,
                            authenticated=False,
                        ),
                        message=message,
                    )
                )
            stats["raw_posts"] += len(raw_posts)

            for post in raw_posts:
                score = relevance_score(keyword, post.get("text", ""))
                if score < min_score:
                    stats["rejected_posts"] += 1
                    continue

                item = build_item(
                    source_type="keyword",
                    source_name=keyword,
                    category=category_name,
                    author=post.get("username", ""),
                    content=post.get("text", ""),
                    url=post.get("permalink", ""),
                    created_at=post.get("timestamp", ""),
                    raw=post,
                    source_trust="keyword_discovery",
                    keywords=keywords,
                    relevance=score,
                )

                key = dedupe_key(item)
                if key in run_seen:
                    stats["deduped_posts"] += 1
                    continue

                run_seen.add(key)
                items.append(item)
                stats["accepted_posts"] += 1

    written_paths = write_items(items)

    return {
        "items": items,
        "paths": written_paths,
        "stats": stats,
        "debug_events": debug_events,
        "errors": errors,
    }
