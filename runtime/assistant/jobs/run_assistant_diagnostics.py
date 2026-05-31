import argparse
import json
import sys
from pathlib import Path


ASSISTANT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ASSISTANT_DIR.parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.config import resolve_category
from assistant.diagnostics import run_diagnostics


ROOT = ASSISTANT_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "assistant" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run PAOS assistant diagnostics.")
    parser.add_argument("--category")
    return parser.parse_args()


def write_status(payload: dict) -> None:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    resolved_category = resolve_category(args.category)

    try:
        payload = run_diagnostics(category=resolved_category.value)
        payload["category_source"] = resolved_category.source
    except Exception as exc:
        payload = {
            "status": "failed",
            "category": (args.category or "").strip() or "unknown",
            "category_source": "unresolved",
            "generated_at": None,
            "checks": [],
            "warnings": [],
            "errors": [str(exc)],
            "resolved_artifacts": {
                "digest": {
                    "path": None,
                    "exists": False,
                    "date": None,
                    "modified_at": None,
                    "size_bytes": None,
                },
                "insight": {
                    "path": None,
                    "exists": False,
                    "date": None,
                    "modified_at": None,
                    "size_bytes": None,
                },
                "runtime_statuses": [],
            },
        }

    write_status(payload)
    print(json.dumps(payload, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
