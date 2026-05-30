import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANDIDATES_DIR = ROOT / "intelligence" / "candidates"


def resolve_date(value):
    if not value or value == "today":
        return datetime.now().astimezone().strftime("%Y-%m-%d")
    return value


def candidate_path(date, category):
    return CANDIDATES_DIR / resolve_date(date) / f"{category}.jsonl"


def load_candidates(date, category):
    path = candidate_path(date=date, category=category)
    if not path.exists():
        return path, []

    items = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = (line or "").strip()
            if not payload:
                continue
            try:
                items.append(json.loads(payload))
            except json.JSONDecodeError:
                continue

    return path, items
