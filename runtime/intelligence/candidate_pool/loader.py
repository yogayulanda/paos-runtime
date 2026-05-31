import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "intelligence" / "raw"
SUPPORTED_SOURCE_FAMILIES = [
    "threads",
    "rss",
    "github",
    "linkedin",
    "jobs",
    "keyword",
]


def resolve_date(value):
    if not value or value == "today":
        return datetime.now().astimezone().strftime("%Y-%m-%d")
    return value


def candidate_paths_for_family(family, date, category=None):
    day = resolve_date(date)
    base = RAW_DIR / family / day
    if not base.exists():
        return []

    family_paths = {
        "threads": [base / "account", base / "keyword"],
        "rss": [base / "feed"],
        "github": [base, base / "github"],
        "linkedin": [base, base / "linkedin"],
        "jobs": [base, base / "jobs"],
        "keyword": [base, base / "keyword"],
    }
    roots = family_paths.get(family, [base])
    paths = []

    if category:
        for root in roots:
            paths.append(root / f"{category}.jsonl")
        return [path for path in paths if path.exists()]

    discovered = []
    for root in roots:
        if root.exists():
            discovered.extend(sorted(root.glob("*.jsonl")))
    return discovered


def load_jsonl_items(files):
    items = []
    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = (line or "").strip()
                if not payload:
                    continue
                try:
                    item = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                items.append(item)

    return items


def load_raw_source_items(date, category=None):
    files = []
    source_families = []

    for family in SUPPORTED_SOURCE_FAMILIES:
        family_paths = candidate_paths_for_family(
            family=family,
            date=date,
            category=category,
        )
        if not family_paths:
            continue
        files.extend(family_paths)
        source_families.append(family)

    items = load_jsonl_items(files)
    return files, items, source_families
