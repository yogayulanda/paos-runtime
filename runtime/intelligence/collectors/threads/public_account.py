from collectors.threads.extractor import build_error
from collectors.threads.extractor import classify_threads_error
from collectors.threads.extractor import normalize_post
from collectors.threads.models import build_item
from collectors.threads.models import dedupe_key
from collectors.threads.models import get_default_limit
from collectors.threads.models import iter_accounts
from collectors.threads.models import load_threads_config
from collectors.threads.models import write_items
from config import is_source_enabled


def collect_account_feed(
    adapter,
    limit=None,
    category=None,
    debug=False,
    authenticated=False,
):
    if category and not is_source_enabled(category, "threads"):
        raise SystemExit(
            f"Source family `threads` is disabled for category `{category}`."
        )
    config = load_threads_config()
    category_keywords = {
        name: (details or {}).get("keywords") or []
        for name, details in (config.get("categories") or {}).items()
    }
    run_seen = set()
    items = []
    stats = {
        "accounts_processed": 0,
        "skipped_accounts": 0,
        "raw_posts": 0,
        "accepted_posts": 0,
        "deduped_posts": 0,
    }
    diagnostics = {
        "accounts_total": 0,
        "accounts_succeeded": 0,
        "accounts_empty": 0,
        "accounts_failed": 0,
        "account_warnings": [],
        "items_collected": 0,
    }
    debug_events = []
    errors = []
    skipped = []

    for account in iter_accounts(config, category):
        diagnostics["accounts_total"] += 1
        stats["accounts_processed"] += 1
        username = account["username"]
        account_category = account["category"]
        collection_mode = account.get("collection_mode", "public")
        account_limit = limit or int(
            account.get("limit") or get_default_limit(config, "account")
        )

        if collection_mode == "authenticated" and not authenticated:
            stats["skipped_accounts"] += 1
            skipped.append(
                f"account:{username}: requires authenticated collection; re-run with --auth"
            )
            continue

        raw_posts = []
        event_batch = []
        message = None
        try:
            raw_posts = [
                normalize_post(post)
                for post in adapter.fetch_account_posts(username, account_limit)
            ]
        except SystemExit as exc:
            message = str(exc)
        finally:
            event_batch = adapter.consume_debug_events()
            if debug:
                debug_events.extend(event_batch)
        if message:
            latest_event = event_batch[-1] if event_batch else {}
            code = classify_threads_error(
                message,
                diagnostics=latest_event,
                authenticated=authenticated,
            )
            if code == "EXTRACTION_EMPTY":
                diagnostics["accounts_empty"] += 1
                diagnostics["account_warnings"].append(
                    {
                        "username": username,
                        "reason": "empty_extraction",
                        "code": code,
                        "message": message,
                    }
                )
            else:
                diagnostics["accounts_failed"] += 1
                diagnostics["account_warnings"].append(
                    {
                        "username": username,
                        "reason": "extraction_error",
                        "code": code,
                        "message": message,
                    }
                )
            errors.append(
                build_error(
                    source_type="account",
                    source_name=username,
                    code=code,
                    message=message,
                )
            )
            continue
        stats["raw_posts"] += len(raw_posts)
        if not raw_posts:
            diagnostics["accounts_empty"] += 1
            diagnostics["account_warnings"].append(
                {
                    "username": username,
                    "reason": "no_posts",
                    "code": "NO_POSTS",
                    "message": "No posts were returned for this account.",
                }
            )
            continue

        accepted_for_account = 0
        for post in raw_posts:
            item = build_item(
                source_type="account",
                source_name=username,
                category=account_category,
                author=post.get("username", ""),
                content=post.get("text", ""),
                url=post.get("permalink", ""),
                created_at=post.get("timestamp", ""),
                raw=post,
                source_trust="mapped_account",
                keywords=category_keywords.get(account_category, []),
                relevance=None,
            )

            key = dedupe_key(item)
            if key in run_seen:
                stats["deduped_posts"] += 1
                continue

            run_seen.add(key)
            items.append(item)
            stats["accepted_posts"] += 1
            accepted_for_account += 1
        if accepted_for_account > 0:
            diagnostics["accounts_succeeded"] += 1
        else:
            diagnostics["accounts_empty"] += 1
            diagnostics["account_warnings"].append(
                {
                    "username": username,
                    "reason": "no_usable_items",
                    "code": "NO_USABLE_ITEMS",
                    "message": "Posts were fetched but no usable items were collected.",
                }
            )

    written_paths = write_items(items)
    diagnostics["items_collected"] = len(items)

    return {
        "items": items,
        "paths": written_paths,
        "stats": stats,
        "diagnostics": diagnostics,
        "debug_events": debug_events,
        "errors": errors,
        "skipped": skipped,
    }
