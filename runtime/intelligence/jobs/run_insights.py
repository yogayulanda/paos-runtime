import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from insights.generator import build_insight_layer
from insights.renderer import render_telegram_brief
from notify.telegram import send_telegram_message
from config import resolve_category


ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "insights" / "latest.json"


TELEGRAM_TITLES = {
    "en": {
        "digest": "📰 Daily Digest",
        "insights": "🎯 Daily Insights",
    },
    "id": {
        "digest": "📰 Ringkasan Harian",
        "insights": "🎯 Insight Hari Ini",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run PAOS insight engine.")
    parser.add_argument("--category")
    parser.add_argument("--date", default="today")
    parser.add_argument(
        "--mode",
        choices=["auto", "ai", "heuristic"],
        default="auto",
    )
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Send digest + insight delivery messages to Telegram.",
    )
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
    telegram_sent=False,
    category_source=None,
):
    finished_at = now_iso()
    duration = max(
        0.0,
        datetime.fromisoformat(finished_at).timestamp()
        - datetime.fromisoformat(started_at).timestamp(),
    )
    return {
        "job": "insights",
        "category": category,
        "category_source": category_source,
        "date": result.date if result else date,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "error_message": error_message,
        "language": result.language if result else None,
        "signals_loaded": result.signals_loaded if result else 0,
        "insights_generated": result.insights_generated if result else 0,
        "jsonl_path": str(result.jsonl_path) if result else None,
        "markdown_path": str(result.markdown_path) if result else None,
        "digest_path": str(result.digest_path) if result else None,
        "generation_mode": result.generation_mode if result else None,
        "fallback_used": result.fallback_used if result else False,
        "type_distribution": result.type_distribution if result else {},
        "telegram_sent": telegram_sent,
        "duration_seconds": round(duration, 2),
    }


def failure_message(status):
    return (
        "PAOS Intelligence job failed\n\n"
        "Job: insights\n"
        f"Error: {status['error_message']}\n"
        f"Time: {status['finished_at']}"
    )


def delivery_message(title, body):
    return f"{title}\n\n{body.strip()}"


def send_daily_delivery(result):
    copy = TELEGRAM_TITLES.get(result.language, TELEGRAM_TITLES["en"])
    digest_text = result.digest_path.read_text(encoding="utf-8")
    insight_jsonl = result.jsonl_path.read_text(encoding="utf-8").splitlines()
    insights = [json.loads(line) for line in insight_jsonl if line.strip()]
    insight_text = render_telegram_brief(
        language=result.language,
        signals=[None] * result.signals_loaded,
        insights=insights,
    )
    digest_ok = send_telegram_message(delivery_message(copy["digest"], digest_text))
    insight_ok = send_telegram_message(delivery_message(copy["insights"], insight_text))
    return digest_ok and insight_ok


def main():
    args = parse_args()
    started_at = now_iso()
    resolved_category = resolve_category(args.category)

    try:
        result = build_insight_layer(
            category=resolved_category.value,
            date=args.date,
            mode=args.mode,
        )
        telegram_sent = send_daily_delivery(result) if args.send_telegram else False
        status = build_status(
            started_at=started_at,
            status="success",
            category=resolved_category.value,
            date=args.date,
            result=result,
            telegram_sent=telegram_sent,
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
    print(result.markdown_path)


if __name__ == "__main__":
    main()
