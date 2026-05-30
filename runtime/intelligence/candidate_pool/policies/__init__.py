from candidate_pool.policies.github import GitHubPolicy
from candidate_pool.policies.jobs import JobsPolicy
from candidate_pool.policies.keyword import KeywordPolicy
from candidate_pool.policies.linkedin import LinkedInPolicy
from candidate_pool.policies.rss import RSSPolicy
from candidate_pool.policies.threads_account import ThreadsAccountPolicy


POLICY_REGISTRY = {
    ("threads", "account"): ThreadsAccountPolicy(),
    ("github", "github"): GitHubPolicy(),
    ("linkedin", "linkedin"): LinkedInPolicy(),
    ("rss", "feed"): RSSPolicy(),
    ("web", "keyword"): KeywordPolicy(),
    ("jobs", "jobs"): JobsPolicy(),
}


def resolve_policy(item):
    platform = " ".join(str(item.get("platform") or "").split()).lower()
    source_type = " ".join(str(item.get("source_type") or "").split()).lower()

    if platform == "threads" and source_type == "keyword":
        return KeywordPolicy()

    if platform == "rss" and source_type == "feed":
        return RSSPolicy()

    if source_type == "keyword":
        return KeywordPolicy()

    if source_type == "jobs":
        return JobsPolicy()

    return POLICY_REGISTRY.get((platform, source_type))
