import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from digest.builder import build_digest
from config import resolve_category
from notify.telegram import send_telegram_message


ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "digest" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run PAOS digest renderer.")
    parser.add_argument("--category")
    parser.add_argument("--date", default="today")
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
    category,
    date,
    result=None,
    error_message=None,
    category_source=None,
):
    finished_at = now_iso()
    duration = max(
        0.0,
        datetime.fromisoformat(finished_at).timestamp()
        - datetime.fromisoformat(started_at).timestamp(),
    )
    return {
        "job": "digest",
        "category": category,
        "category_source": category_source,
        "date": result.date if result else date,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "error_message": error_message,
        "signals_loaded": result.signals_loaded if result else 0,
        "digest_path": str(result.digest_path) if result else None,
        "duration_seconds": round(duration, 2),
    }


def failure_message(status):
    return (
        "PAOS Intelligence job failed\n\n"
        "Job: digest\n"
        f"Error: {status['error_message']}\n"
        f"Time: {status['finished_at']}"
    )


def main():
    args = parse_args()
    started_at = now_iso()
    resolved_category = resolve_category(args.category)

    try:
        result = build_digest(category=resolved_category.value, date=args.date)
        status = build_status(
            started_at=started_at,
            status="success",
            category=resolved_category.value,
            date=args.date,
            result=result,
            category_source=resolved_category.source,
        )
    except Exception as exc:
        status = build_status(
            started_at=started_at,
            status="failed",
            category=resolved_category.value,
            date=args.date,
            error_message=str(exc),
            category_source=resolved_category.source,
        )
        write_status(status)
        send_telegram_message(failure_message(status))
        print(json.dumps(status, ensure_ascii=True, indent=2))
        raise

    write_status(status)
    print(result.digest_path)


if __name__ == "__main__":
    main()
