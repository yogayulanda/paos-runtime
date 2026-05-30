import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from signals.builder import build_signal_layer
from config import resolve_category
from notify.telegram import send_telegram_message


ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "signal-builder" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run PAOS signal layer build."
    )
    parser.add_argument("--category")
    parser.add_argument("--date", default="today")
    parser.add_argument(
        "--mode",
        choices=["auto", "ai", "heuristic"],
        default="auto",
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
    result=None,
    error_message=None,
    category=None,
    category_source=None,
):
    finished_at = now_iso()
    duration = max(
        0.0,
        datetime.fromisoformat(finished_at).timestamp()
        - datetime.fromisoformat(started_at).timestamp(),
    )
    return {
        "job": "signal-builder",
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "category": category,
        "category_source": category_source,
        "error_message": error_message,
        "candidates_loaded": result.candidates_loaded if result else 0,
        "themes_detected": result.themes_detected if result else [],
        "signals_generated": result.signals_generated if result else 0,
        "generation_mode": result.generation_mode if result else None,
        "fallback_used": result.fallback_used if result else False,
        "output_path": str(result.output_path) if result else None,
        "diagnostics": result.diagnostics if result else {},
        "duration_seconds": round(duration, 2),
    }


def failure_message(status):
    return (
        "PAOS Intelligence job failed\n\n"
        "Job: signal-builder\n"
        f"Error: {status['error_message']}\n"
        f"Time: {status['finished_at']}"
    )


def main():
    args = parse_args()
    started_at = now_iso()

    try:
        resolved_category = resolve_category(args.category)
        result = build_signal_layer(
            category=resolved_category.value,
            date=args.date,
            mode=args.mode,
        )
        status = build_status(
            started_at=started_at,
            status="success",
            result=result,
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
    except Exception as exc:
        status = build_status(
            started_at=started_at,
            status="failed",
            error_message=str(exc),
            category=args.category,
            category_source="cli" if args.category else None,
        )
        write_status(status)
        send_telegram_message(failure_message(status))
        print(json.dumps(status, ensure_ascii=True, indent=2))
        raise

    write_status(status)
    print(json.dumps(status, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
