from candidate_pool.deduper import dedupe_candidates
from candidate_pool.normalizer import compact_text
from candidate_pool.normalizer import normalize_threads_account_item


class ThreadsAccountPolicy:
    policy_name = "threads_account"
    policy_version = "v1"
    filter_mode = "noise_only"
    source_trust = "mapped_account"

    def normalize_items(self, items):
        normalized_items = []
        dropped_empty = 0
        total_removed_noise = 0

        for item in items:
            normalized, meta = normalize_threads_account_item(
                item,
                policy_name=self.policy_name,
                policy_version=self.policy_version,
                filter_mode=self.filter_mode,
                source_trust=self.source_trust,
            )
            total_removed_noise += meta["removed_noise_count"]
            if meta["dropped"]:
                dropped_empty += 1
                continue
            normalized_items.append(normalized)

        diagnostics = {
            "policy": self.policy_name,
            "filter_mode": self.filter_mode,
            "dropped_empty": dropped_empty,
            "noise_fragments_removed": total_removed_noise,
        }
        return normalized_items, diagnostics

    def dedupe_items(self, items):
        return dedupe_candidates(items)
