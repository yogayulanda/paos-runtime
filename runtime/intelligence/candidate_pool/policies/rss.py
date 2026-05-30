from candidate_pool.deduper import dedupe_candidates
from candidate_pool.normalizer import compact_text


class RSSPolicy:
    policy_name = "rss"
    policy_version = "v1"
    filter_mode = "noise_only"
    source_trust = "rss_source"

    def normalize_items(self, items):
        normalized_items = []
        dropped_empty = 0

        for item in items:
            title = compact_text((item.get("raw") or {}).get("title") or item.get("title"))
            content = compact_text(item.get("content"))
            summary = compact_text((item.get("raw_metadata") or {}).get("summary"))
            if not title or not (content or summary):
                dropped_empty += 1
                continue

            normalized_items.append(
                {
                    "platform": compact_text(item.get("platform")) or "rss",
                    "category": compact_text(item.get("category")),
                    "source_type": compact_text(item.get("source_type")) or "feed",
                    "source_name": compact_text(item.get("source_name")),
                    "author": compact_text(item.get("author")) or None,
                    "content": content or summary,
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
        }
        return normalized_items, diagnostics

    def dedupe_items(self, items):
        return dedupe_candidates(items)
