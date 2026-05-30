import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from candidate_pool.deduper import dedupe_candidates
from candidate_pool.loader import load_raw_source_items
from candidate_pool.loader import resolve_date
from candidate_pool.models import CandidatePoolBuildResult
from candidate_pool.policies import resolve_policy


ROOT = INTELLIGENCE_DIR.parents[1]
CANDIDATES_DIR = ROOT / "intelligence" / "candidates"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build deterministic PAOS candidate pool from raw intelligence."
    )
    parser.add_argument("--category", required=True)
    parser.add_argument("--date", default="today")
    return parser.parse_args()


def output_path_for(date, category):
    return CANDIDATES_DIR / date / f"{category}.jsonl"


def write_candidates(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")


def build_candidate_pool(category, date):
    resolved_date = resolve_date(date)
    files_loaded, raw_items, source_families = load_raw_source_items(
        date=resolved_date,
        category=category,
    )
    if not raw_items:
        normalized_items = []
        normalization_diagnostics = {
            "policy": None,
            "filter_mode": None,
            "dropped_empty": 0,
            "noise_fragments_removed": 0,
        }
        deduped_items = []
        dedupe_diagnostics = {
            "duplicate_urls_removed": 0,
            "duplicate_content_removed": 0,
        }
        policies_used = []
    else:
        batches = defaultdict(list)
        policy_objects = {}
        batch_order = []

        for item in raw_items:
            policy = resolve_policy(item)
            if not policy:
                raise SystemExit(
                    "No candidate pool policy is registered for "
                    f"platform={item.get('platform')} "
                    f"source_type={item.get('source_type')}"
                )
            key = policy.policy_name
            if key not in policy_objects:
                policy_objects[key] = policy
                batch_order.append(key)
            batches[key].append(item)

        normalized_items = []
        policies_used = []
        dropped_empty = 0
        noise_fragments_removed = 0

        for policy_name in batch_order:
            policy = policy_objects[policy_name]
            batch_items, batch_diagnostics = policy.normalize_items(batches[policy_name])
            normalized_items.extend(batch_items)
            policies_used.append(policy_name)
            dropped_empty += int(batch_diagnostics.get("dropped_empty", 0) or 0)
            noise_fragments_removed += int(
                batch_diagnostics.get("noise_fragments_removed", 0) or 0
            )

        normalization_diagnostics = {
            "policy": policies_used[0] if len(policies_used) == 1 else "multiple",
            "filter_mode": (
                policy_objects[policies_used[0]].filter_mode
                if len(policies_used) == 1
                else "mixed"
            ),
            "dropped_empty": dropped_empty,
            "noise_fragments_removed": noise_fragments_removed,
        }
        deduped_items, dedupe_diagnostics = dedupe_candidates(normalized_items)

    output_path = output_path_for(resolved_date, category)
    write_candidates(output_path, deduped_items)

    diagnostics = {
        "input_source": "raw_intelligence",
        "source_families_loaded": source_families,
        "files_loaded": [str(path) for path in files_loaded],
        "policies_used": policies_used,
        **normalization_diagnostics,
        **dedupe_diagnostics,
    }

    return CandidatePoolBuildResult(
        date=resolved_date,
        category=category,
        files_loaded=files_loaded,
        items_loaded=len(raw_items),
        items_after_normalization=len(normalized_items),
        items_after_dedupe=len(deduped_items),
        candidates_written=len(deduped_items),
        output_path=output_path,
        diagnostics=diagnostics,
    )


def print_result(result):
    print("Candidate Pool Build")
    print(f"date: {result.date}")
    print(f"category: {result.category}")
    print(f"files_loaded: {len(result.files_loaded)}")
    print(f"items_loaded: {result.items_loaded}")
    print(f"items_after_normalization: {result.items_after_normalization}")
    print(f"items_after_dedupe: {result.items_after_dedupe}")
    print(f"candidates_written: {result.candidates_written}")
    print(f"output_path: {result.output_path}")
    print("diagnostics:")
    for key, value in result.diagnostics.items():
        print(f"  {key}: {value}")


def main():
    args = parse_args()
    result = build_candidate_pool(category=args.category, date=args.date)
    print_result(result)


if __name__ == "__main__":
    main()
