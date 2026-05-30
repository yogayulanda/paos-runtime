import argparse

from collectors.threads.extractor import default_provider
from collectors.threads.extractor import resolve_adapter_with_auth
from collectors.threads.models import load_threads_config
from collectors.threads.public_account import collect_account_feed
from collectors.threads.public_search import collect_keyword_discovery
from threads_auth import check_session_state
from threads_auth import session_status_error_code


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run source-driven PAOS intelligence discovery."
    )
    parser.add_argument(
        "--source",
        choices=["threads"],
        required=True,
    )
    parser.add_argument(
        "--mode",
        choices=["keyword", "account"],
        required=True,
    )
    parser.add_argument(
        "--provider",
        choices=["official", "scraper", "playwright"],
        default=default_provider(),
    )
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-score", type=int, default=3)
    parser.add_argument(
        "--extraction-mode",
        choices=["fast", "deep"],
        help="Threads account extraction mode. Defaults to fast for account mode.",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Use the persistent authenticated Threads browser profile.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Maximum runtime budget for browser-backed collection.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save Threads debug artifacts and print extractor diagnostics.",
    )
    return parser.parse_args()


def print_config_overview(config, mode, category, auth_enabled, extraction_mode):
    print(f"Source: {config.get('platform')}")
    print(f"Mode: {mode}")
    print(f"Auth mode: {auth_enabled}")
    if extraction_mode:
        print(f"Extraction mode: {extraction_mode}")

    if category:
        print(f"Category filter: {category}")

    print("")


def print_result(result):
    stats = result["stats"]
    errors = result.get("errors") or []

    print("Summary")
    for key, value in stats.items():
        print(f"{key}: {value}")

    print(f"files_written: {len(result['paths'])}")

    if result["paths"]:
        print("")
        print("Written paths:")
        for path in result["paths"]:
            print(path)

    if result["items"]:
        print("")
        print("Sample item:")
        print(result["items"][0])

    if errors:
        print("")
        print("Errors:")
        for error in errors:
            if isinstance(error, dict):
                print(
                    f"{error['source_type']}:{error['source_name']} "
                    f"{error['code']} {error['message']}"
                )
            else:
                print(error)

    skipped = result.get("skipped") or []
    if skipped:
        print("")
        print("Skipped:")
        for entry in skipped:
            print(entry)

    debug_events = result.get("debug_events") or []
    if debug_events:
        print("")
        print("Diagnostics:")
        for event in debug_events:
            print(
                f"{event['source_type']}:{event['source_name']} "
                f"page_loaded={event['page_loaded']} "
                f"permalink_count={event['permalink_count']} "
                f"visible_text_length={event['visible_text_length']} "
                f"login_wall_detected={event['login_wall_detected']} "
                f"extraction_mode={event.get('extraction_mode', '')} "
                f"raw_candidates_count={event['raw_candidates_count']} "
                f"extracted_posts_count={event['extracted_posts_count']} "
                f"href_snapshot_count={event.get('href_snapshot_count', 0)} "
                f"unique_post_url_count={event.get('unique_post_url_count', 0)} "
                f"detail_pages_attempted={event.get('detail_pages_attempted', 0)} "
                f"detail_pages_failed={event.get('detail_pages_failed', 0)} "
                f"scroll_attempts={event.get('scroll_attempts', 0)} "
                f"extraction_duration_seconds={event.get('extraction_duration_seconds', 0)} "
                f"raw_text_length={event.get('raw_text_length', 0)} "
                f"cleaned_text_length={event.get('cleaned_text_length', 0)} "
                f"removed_ui_lines_count={event.get('removed_ui_lines_count', 0)} "
                f"page_closed={event.get('page_closed', False)} "
                f"detail_page_closed={event.get('detail_page_closed', False)} "
                f"context_closed={event.get('context_closed', False)} "
                f"browser_closed={event.get('browser_closed', False)} "
                f"cleanup_error={event.get('cleanup_error', '')}"
            )
            artifacts = event.get("artifacts") or {}
            if artifacts:
                print(
                    f"artifacts html={artifacts.get('html')} "
                    f"png={artifacts.get('png')} "
                    f"txt={artifacts.get('txt')}"
                )


def main():
    args = parse_args()
    config = load_threads_config()

    if args.category and args.category not in (config.get("categories") or {}):
        raise SystemExit(
            f"Unknown category `{args.category}` for source `{args.source}`."
        )

    extraction_mode = args.extraction_mode
    if not extraction_mode and args.mode == "account":
        extraction_mode = "fast"
    if not extraction_mode:
        extraction_mode = "deep"

    provider = "playwright" if args.auth and args.mode == "account" else args.provider
    print_config_overview(
        config,
        args.mode,
        args.category,
        args.auth,
        extraction_mode if args.mode == "account" else None,
    )

    if args.auth and args.mode == "account":
        session = check_session_state(headless=True)
        if session["session_status"] != "authenticated":
            result = {
                "items": [],
                "paths": [],
                "stats": {
                    "accounts_processed": 0,
                    "skipped_accounts": 0,
                    "raw_posts": 0,
                    "accepted_posts": 0,
                    "deduped_posts": 0,
                },
                "errors": [
                    {
                        "source_type": "account",
                        "source_name": args.category or "all",
                        "code": session_status_error_code(session["session_status"]),
                        "message": (
                            "Threads login is not verified. Run manual login first."
                            f" session_status={session['session_status']}"
                        ),
                    }
                ],
                "debug_events": [],
                "skipped": [],
            }
            print_result(result)
            return

    adapter = resolve_adapter_with_auth(
        provider=provider,
        debug=args.debug,
        authenticated=args.auth and args.mode == "account",
        timeout_seconds=args.timeout_seconds,
        extraction_mode=extraction_mode,
    )

    if args.mode == "keyword":
        result = collect_keyword_discovery(
            adapter=adapter,
            limit=args.limit,
            min_score=args.min_score,
            category=args.category,
            debug=args.debug,
        )
    else:
        result = collect_account_feed(
            adapter=adapter,
            limit=args.limit,
            category=args.category,
            debug=args.debug,
            authenticated=args.auth,
        )

    print_result(result)


if __name__ == "__main__":
    main()
