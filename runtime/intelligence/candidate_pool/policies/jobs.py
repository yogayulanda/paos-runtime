from candidate_pool.deduper import dedupe_candidates
from candidate_pool.normalizer import build_candidate_metadata
from candidate_pool.normalizer import compact_text


class JobsPolicy:
    policy_name = "jobs"
    policy_version = "v1"
    filter_mode = "relevance"
    source_trust = "discovery"

    def normalize_items(self, items):
        normalized_items = []
        dropped_empty = 0

        for item in items:
            title = compact_text((item.get("raw") or {}).get("title") or item.get("title"))
            content = compact_text(item.get("content"))
            if not title and len(content) < 40:
                dropped_empty += 1
                continue

            normalized_items.append(
                {
                    "platform": compact_text(item.get("platform")) or "jobs",
                    "category": compact_text(item.get("category")),
                    "source_type": compact_text(item.get("source_type")) or "jobs",
                    "source_name": compact_text(item.get("source_name")),
                    "author": compact_text(item.get("author")) or None,
                    "content": content or title,
                    "url": compact_text(item.get("url")) or None,
                    "created_at": item.get("created_at") or None,
                    "collected_at": item.get("collected_at") or None,
                    "candidate_metadata": build_candidate_metadata(
                        item=item,
                        policy_name=self.policy_name,
                        policy_version=self.policy_version,
                        filter_mode=self.filter_mode,
                        source_trust=self.source_trust,
                    ),
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
