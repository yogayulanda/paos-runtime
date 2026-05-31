import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from collectors.threads.extractor import resolve_adapter_with_auth
from collectors.threads.public_search import collect_keyword_discovery
from config import is_source_enabled
from config import resolve_category
from threads_auth import check_session_state


ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "threads-keyword" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run Threads keyword discovery safely.")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--min-score", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--provider",
        choices=["playwright", "official", "scraper"],
        default="playwright",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def now_iso():
    return datetime.now().astimezone().isoformat()


def write_status(payload):
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def build_status(
    started_at,
    status,
    result=None,
    error_message=None,
    error_code=None,
    category=None,
    category_source=None,
    authenticated=None,
):
    finished_at = now_iso()
    duration = max(
        0.0,
        datetime.fromisoformat(finished_at).timestamp()
        - datetime.fromisoformat(started_at).timestamp(),
    )
    stats = (result or {}).get("stats") or {}
    diagnostics = (result or {}).get("diagnostics") or {}
    return {
        "job": "threads-keyword",
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "category": category,
        "category_source": category_source,
        "error_code": error_code,
        "error_message": error_message,
        "authenticated_session": authenticated,
        "queries_processed": stats.get("queries_processed", 0),
        "items_collected": stats.get("accepted_posts", 0),
        "diagnostics": diagnostics,
        "paths": [str(path) for path in ((result or {}).get("paths") or [])],
        "duration_seconds": round(duration, 2),
    }


def main():
    args = parse_args()
    started_at = now_iso()
    resolved_category = resolve_category(args.category)
    if not is_source_enabled(resolved_category.value, "keyword"):
        status = build_status(
            started_at=started_at,
            status="skipped",
            error_code="SOURCE_DISABLED",
            error_message=(
                f"Source family `keyword` is disabled for category `{resolved_category.value}`."
            ),
            category=resolved_category.value,
            category_source=resolved_category.source,
            authenticated=False,
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=True, indent=2))
        return

    session = check_session_state(headless=True)
    authenticated = session.get("session_status") == "authenticated"
    adapter = resolve_adapter_with_auth(
        provider=args.provider,
        debug=args.debug,
        authenticated=authenticated,
        timeout_seconds=args.timeout_seconds,
        extraction_mode="deep",
    )
    result = collect_keyword_discovery(
        adapter=adapter,
        limit=args.limit,
        min_score=args.min_score,
        category=resolved_category.value,
        debug=args.debug,
    )
    diagnostics = result.get("diagnostics") or {}
    queries_total = int(diagnostics.get("queries_total") or 0)
    queries_succeeded = int(diagnostics.get("queries_succeeded") or 0)
    queries_failed = int(diagnostics.get("queries_failed") or 0)
    items_collected = int(diagnostics.get("items_collected") or 0)

    status_value = "success"
    error_code = None
    error_message = None
    if queries_total <= 0:
        status_value = "failed"
        error_code = "NO_QUERIES_CONFIGURED"
        error_message = "No enabled Threads keywords are configured."
    elif queries_succeeded <= 0 and queries_failed > 0 and items_collected <= 0:
        status_value = "failed"
        error_code = "ALL_QUERIES_FAILED"
        error_message = "All enabled Threads keyword queries failed and no usable items were collected."
    elif queries_failed > 0 or int(diagnostics.get("queries_empty") or 0) > 0:
        status_value = "success_with_warnings"

    status = build_status(
        started_at=started_at,
        status=status_value,
        result=result,
        error_code=error_code,
        error_message=error_message,
        category=resolved_category.value,
        category_source=resolved_category.source,
        authenticated=authenticated,
    )
    write_status(status)
    output = {"status": status, "result": result}
    print(json.dumps(output, ensure_ascii=True, indent=2, default=str))
    if status_value == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
