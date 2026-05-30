import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from digest.loader import load_signals
from digest.loader import resolve_date
from digest.loader import signal_path
from digest.renderer import render_digest
from signals.loader import candidate_path


ROOT = INTELLIGENCE_DIR.parents[1]
DIGESTS_DIR = ROOT / "intelligence" / "digests"


@dataclass(frozen=True)
class DigestBuildResult:
    category: str
    date: str
    signals_loaded: int
    digest_path: Path


class DigestFreshnessError(RuntimeError):
    pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render PAOS intelligence digest from signals."
    )
    parser.add_argument("--category", required=True)
    parser.add_argument("--date", default="today")
    return parser.parse_args()


def output_path_for(date, category):
    return DIGESTS_DIR / date / f"{category}.md"


def validate_signal_freshness(date, category):
    candidate_file = candidate_path(date=date, category=category)
    signal_file = signal_path(date=date, category=category)

    if not candidate_file.exists():
        raise DigestFreshnessError(
            "Candidate pool output is missing. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_candidate_pool.py --category {category}"
        )

    if not signal_file.exists():
        raise DigestFreshnessError(
            "Signal output is missing. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )

    candidate_mtime = candidate_file.stat().st_mtime
    signal_mtime = signal_file.stat().st_mtime
    if signal_mtime < candidate_mtime:
        raise DigestFreshnessError(
            "Signal output is stale relative to the current candidate pool. "
            f"candidate={candidate_file} signal={signal_file}. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )

    return candidate_file, signal_file


def build_digest(category, date):
    resolved_date = resolve_date(date)
    _candidate_file, _signal_file = validate_signal_freshness(
        date=resolved_date,
        category=category,
    )
    _input_path, signals = load_signals(date=resolved_date, category=category)
    if not signals:
        raise DigestFreshnessError(
            "Signal output is empty or incomplete. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )
    digest_path = output_path_for(resolved_date, category)
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        render_digest(category=category, date=resolved_date, signals=signals),
        encoding="utf-8",
    )
    return DigestBuildResult(
        category=category,
        date=resolved_date,
        signals_loaded=len(signals),
        digest_path=digest_path,
    )


def main():
    args = parse_args()
    result = build_digest(category=args.category, date=args.date)
    print(result.digest_path)


if __name__ == "__main__":
    main()
