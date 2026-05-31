from candidate_pool.deduper import dedupe_candidates
from candidate_pool.normalizer import compact_text


class ThreadsKeywordPolicy:
    policy_name = "threads_keyword"
    policy_version = "v1"
    filter_mode = "relevance"
    source_trust = "discovery"

    def normalize_items(self, items):
        normalized_items = []
        dropped_empty = 0

        for item in items:
            content = compact_text(item.get("content"))
            if len(content) < 40:
                dropped_empty += 1
                continue

            normalized_items.append(
                {
                    "platform": compact_text(item.get("platform")) or "threads",
                    "category": compact_text(item.get("category")),
                    "source_type": "keyword",
                    "source_name": compact_text(item.get("source_name")),
                    "author": compact_text(item.get("author")) or None,
                    "content": content,
                    "url": compact_text(item.get("url")) or None,
                    "created_at": item.get("created_at") or None,
                    "collected_at": item.get("collected_at") or None,
                    "candidate_metadata": {
                        "source_trust": self.source_trust,
                        "duplicate_removed": False,
                        "normalization_version": "candidate_pool.v1",
                        "policy": self.policy_name,
                        "policy_version": self.policy_version,
                        "filter_mode": self.filter_mode,
                    },
                }
            )

        diagnostics = {
            "policy": self.policy_name,
            "filter_mode": self.filter_mode,
            "dropped_empty": dropped_empty,
            "relevance_filter_applied": True,
        }
        return normalized_items, diagnostics

    def dedupe_items(self, items):
        return dedupe_candidates(items)
