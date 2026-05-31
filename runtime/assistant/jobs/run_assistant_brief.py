import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ASSISTANT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ASSISTANT_DIR.parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.brief import build_assistant_brief
from assistant.config import resolve_category


ROOT = ASSISTANT_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "assistant-brief" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Build PAOS assistant daily brief.")
    parser.add_argument("--category")
    return parser.parse_args()


def now_iso():
    return datetime.now().astimezone().isoformat()


def write_status(payload: dict) -> None:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    started_at = now_iso()

    try:
        resolved_category = resolve_category(args.category)
    except Exception as exc:
        status = {
            "job": "assistant-brief",
            "category": (args.category or "").strip() or "unknown",
            "category_source": "unresolved",
            "started_at": started_at,
            "finished_at": now_iso(),
            "generated_at": None,
            "status": "failed",
            "warnings": [],
            "errors": [str(exc)],
            "brief_markdown_path": None,
            "brief_json_path": None,
        }
        write_status(status)
        print("")
        return

    try:
        result = build_assistant_brief(category=resolved_category.value)
        status = {
            "job": "assistant-brief",
            "category": resolved_category.value,
            "category_source": resolved_category.source,
            "started_at": started_at,
            "finished_at": now_iso(),
            "generated_at": result.generated_at,
            "status": result.status,
            "warnings": result.warnings,
            "errors": result.errors,
            "brief_markdown_path": str(result.markdown_path),
            "brief_json_path": str(result.json_path),
        }
    except Exception as exc:
        status = {
            "job": "assistant-brief",
            "category": resolved_category.value,
            "category_source": resolved_category.source,
            "started_at": started_at,
            "finished_at": now_iso(),
            "generated_at": None,
            "status": "failed",
            "warnings": [],
            "errors": [str(exc)],
            "brief_markdown_path": None,
            "brief_json_path": None,
        }

    write_status(status)
    print(status.get("brief_markdown_path") or status.get("brief_json_path") or "")


if __name__ == "__main__":
    main()
