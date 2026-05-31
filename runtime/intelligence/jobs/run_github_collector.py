import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from collectors.github.collector import collect_github_public
from config import is_source_enabled
from config import resolve_category


ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "github-collector" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run PAOS GitHub public collector.")
    parser.add_argument("--category")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def now_iso():
    return datetime.now().astimezone().isoformat()


def write_status(payload):
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def build_status(started_at, status, result=None, error_message=None, error_code=None, category=None, category_source=None):
    finished_at = now_iso()
    duration = max(
        0.0,
        datetime.fromisoformat(finished_at).timestamp() - datetime.fromisoformat(started_at).timestamp(),
    )
    diagnostics = (result or {}).get("diagnostics") or {}
    stats = (result or {}).get("stats") or {}
    return {
        "job": "github-collector",
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "category": category,
        "category_source": category_source,
        "error_code": error_code,
        "error_message": error_message,
        "sources_processed": stats.get("repositories_loaded", 0),
        "items_collected": stats.get("accepted_items", 0),
        "warnings": diagnostics.get("warnings") or [],
        "errors": diagnostics.get("errors") or [],
        "diagnostics": diagnostics,
        "paths": [str(path) for path in ((result or {}).get("paths") or [])],
        "duration_seconds": round(duration, 2),
    }


def main():
    args = parse_args()
    started_at = now_iso()
    resolved_category = resolve_category(args.category)

    if not is_source_enabled(resolved_category.value, "github"):
        status = build_status(
            started_at=started_at,
            status="skipped",
            error_code="SOURCE_DISABLED",
            error_message=f"Source family `github` is disabled for category `{resolved_category.value}`.",
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=True, indent=2))
        return

    if args.dry_run:
        status = build_status(
            started_at=started_at,
            status="skipped",
            error_code="DRY_RUN",
            error_message="Dry run enabled; no network call and no raw artifact write.",
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=True, indent=2))
        return

    try:
        result = collect_github_public(category=resolved_category.value, timeout_seconds=args.timeout_seconds)
        diagnostics = result.get("diagnostics") or {}
        total = int(diagnostics.get("repositories_total") or 0)
        succeeded = int(diagnostics.get("repositories_succeeded") or 0)
        failed = int(diagnostics.get("repositories_failed") or 0)
        items = int(diagnostics.get("items_collected") or 0)
        status_value = "success"
        error_code = None
        error_message = None

        if total <= 0:
            status_value = "success_with_warnings"
            error_code = "NO_REPOSITORIES_CONFIGURED"
            error_message = "No enabled GitHub repositories are configured for this category."
        elif succeeded <= 0 and failed > 0 and items <= 0:
            status_value = "failed"
            error_code = "ALL_REPOSITORIES_FAILED"
            error_message = "All enabled GitHub repositories failed and no usable items were collected."
        elif failed > 0 or int(diagnostics.get("repositories_empty") or 0) > 0:
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
        write_status(status)
        print(json.dumps({"status": status, "result": result}, ensure_ascii=True, indent=2, default=str))
        if status_value == "failed":
            raise SystemExit(1)
    except Exception as exc:
        status = build_status(
            started_at=started_at,
            status="failed",
            error_code="COLLECTOR_EXCEPTION",
            error_message=str(exc),
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=True, indent=2))
        raise


if __name__ == "__main__":
    main()
