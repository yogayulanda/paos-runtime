import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SIGNALS_DIR = ROOT / "intelligence" / "signals"


def resolve_date(value):
    if not value or value == "today":
        return datetime.now().astimezone().strftime("%Y-%m-%d")
    return value


def signal_path(date, category):
    return SIGNALS_DIR / resolve_date(date) / f"{category}.jsonl"


def load_signals(date, category):
    path = signal_path(date=date, category=category)
    if not path.exists():
        return path, []

    signals = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = (line or "").strip()
            if not payload:
                continue
            try:
                signals.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return path, signals
