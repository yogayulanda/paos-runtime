import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from collectors.rss.feed import collect_rss_feeds
from config import resolve_category


ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "rss-collector" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run PAOS RSS collector.")
    parser.add_argument("--category")
    parser.add_argument("--timeout-seconds", type=int, default=20)
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
        "job": "rss-collector",
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "category": category,
        "category_source": category_source,
        "error_code": error_code,
        "error_message": error_message,
        "feeds_loaded": stats.get("feeds_loaded", 0),
        "items_collected": stats.get("accepted_items", 0),
        "diagnostics": diagnostics,
        "paths": [str(path) for path in ((result or {}).get("paths") or [])],
        "duration_seconds": round(duration, 2),
    }


def main():
    args = parse_args()
    started_at = now_iso()
    try:
        resolved_category = resolve_category(args.category)
        result = collect_rss_feeds(
            category=resolved_category.value,
            timeout_seconds=args.timeout_seconds,
        )
        diagnostics = result.get("diagnostics") or {}
        feeds_total = int(diagnostics.get("feeds_total") or 0)
        feeds_succeeded = int(diagnostics.get("feeds_succeeded") or 0)
        feeds_failed = int(diagnostics.get("feeds_failed") or 0)
        items_written = int(diagnostics.get("items_written") or 0)

        status_value = "success"
        error_code = None
        error_message = None
        if feeds_total <= 0:
            status_value = "failed"
            error_code = "NO_FEEDS_PROCESSABLE"
            error_message = "No enabled RSS feeds could be processed."
        elif feeds_succeeded <= 0 and feeds_failed > 0 and items_written <= 0:
            status_value = "failed"
            error_code = "ALL_FEEDS_FAILED"
            error_message = "All enabled RSS feeds failed and no usable items were collected."
        elif feeds_failed > 0 or int(diagnostics.get("feeds_empty") or 0) > 0:
            status_value = "success_with_warnings"

        status = build_status(
            started_at=started_at,
            status=status_value,
            result=result,
            error_code=error_code,
            error_message=error_message,
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        if status_value == "failed":
            write_status(status)
            print(json.dumps({"status": status, "result": result}, ensure_ascii=True, indent=2, default=str))
            raise SystemExit(1)
    except Exception as exc:
        status = build_status(
            started_at=started_at,
            status="failed",
            error_code="COLLECTOR_EXCEPTION",
            error_message=str(exc),
            category=args.category,
            category_source="cli" if args.category else None,
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=True, indent=2))
        raise

    write_status(status)
    print(json.dumps({"status": status, "result": result}, ensure_ascii=True, indent=2, default=str))


if __name__ == "__main__":
    main()
