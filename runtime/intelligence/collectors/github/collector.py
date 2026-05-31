import json
import os
from datetime import datetime
from pathlib import Path
from urllib import error
from urllib import request

import yaml

from config import is_source_enabled
from config import validate_source_categories
from source_age_rules import evaluate_source_item_age
from source_age_rules import get_source_age_rule


ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = ROOT / "runtime" / "intelligence" / "sources" / "github.yaml"
RAW_BASE_DIR = ROOT / "intelligence" / "raw" / "github"


def compact_text(value):
    return " ".join(str(value or "").split())


def now_iso():
    return datetime.now().astimezone().isoformat()


def load_github_config():
    if not CONFIG_PATH.exists():
        return None
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if payload.get("platform") != "github":
        raise SystemExit("GitHub source config must declare `platform: github`.")
    categories = payload.get("categories") or {}
    if not isinstance(categories, dict) or not categories:
        raise SystemExit("GitHub source config must include `categories`.")
    validate_source_categories("github", list(categories.keys()))
    return payload


def iter_repositories(config, selected_category=None):
    for category, details in (config.get("categories") or {}).items():
        if selected_category and category != selected_category:
            continue
        repositories = (details or {}).get("repositories") or []
        if not isinstance(repositories, list):
            raise SystemExit(
                f"GitHub source config categories.{category}.repositories must be a list."
            )
        for repo_entry in repositories:
            if not isinstance(repo_entry, dict):
                continue
            if not repo_entry.get("enabled", True):
                continue
            repo = compact_text(repo_entry.get("repo"))
            if not repo or "/" not in repo:
                continue
            normalized = dict(repo_entry)
            normalized["repo"] = repo
            normalized["category"] = category
            normalized["name"] = compact_text(repo_entry.get("name") or repo.replace("/", "_"))
            normalized["source_type"] = compact_text(repo_entry.get("source_type") or "release")
            normalized["limit"] = int(repo_entry.get("limit") or 0) or None
            tags = repo_entry.get("tags") or []
            normalized["tags"] = [compact_text(tag) for tag in tags if compact_text(tag)]
            yield normalized


def default_limit(config):
    return int(((config.get("limits") or {}).get("default_per_repo") or 3) or 3)


def request_timeout(config):
    return int(((config.get("limits") or {}).get("timeout_seconds") or 20) or 20)


def _headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "paos-runtime-github-collector",
    }
    token = compact_text(os.environ.get("GITHUB_TOKEN"))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_releases(repo, per_page, timeout_seconds):
    url = f"https://api.github.com/repos/{repo}/releases?per_page={max(1, per_page)}"
    req = request.Request(url, headers=_headers(), method="GET")
    with request.urlopen(req, timeout=max(1, timeout_seconds)) as response:
        body = response.read().decode("utf-8", errors="replace")
    payload = json.loads(body or "[]")
    if not isinstance(payload, list):
        return []
    return payload


def _release_item(repo_config, release):
    summary = compact_text(release.get("body") or "")
    title = compact_text(release.get("name") or release.get("tag_name") or "untitled release")
    return {
        "platform": "github",
        "source_type": compact_text(repo_config.get("source_type") or "release"),
        "source_name": compact_text(repo_config.get("name") or repo_config.get("repo")),
        "category": compact_text(repo_config.get("category")),
        "author": compact_text(((release.get("author") or {}).get("login"))) or None,
        "title": title,
        "content": summary[:1200] if summary else title,
        "url": compact_text(release.get("html_url")) or None,
        "created_at": compact_text(release.get("published_at") or release.get("created_at")) or None,
        "collected_at": now_iso(),
        "tags": repo_config.get("tags") or [],
        "signals": {
            "source_trust": "github_public",
            "repository": compact_text(repo_config.get("repo")),
            "release_tag": compact_text(release.get("tag_name")),
            "is_prerelease": bool(release.get("prerelease")),
        },
        "raw": {
            "title": title,
            "published_at": compact_text(release.get("published_at") or ""),
            "repo": compact_text(repo_config.get("repo")),
        },
    }


def storage_path(category, collected_at=None):
    collected_at = collected_at or datetime.now().astimezone()
    day = collected_at.strftime("%Y-%m-%d")
    return RAW_BASE_DIR / day / f"{category}.jsonl"


def write_items(items):
    grouped = {}
    written_paths = []
    for item in items:
        path = storage_path(item.get("category"))
        grouped.setdefault(path, []).append(item)
    for path, bucket in grouped.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for item in bucket:
                handle.write(json.dumps(item, ensure_ascii=True) + "\n")
        written_paths.append(path)
    return written_paths


def collect_github_public(category=None, timeout_seconds=None):
    if category and not is_source_enabled(category, "github"):
        raise SystemExit(f"Source family `github` is disabled for category `{category}`.")

    config = load_github_config()
    if not config:
        return {
            "items": [],
            "paths": [],
            "stats": {"repositories_loaded": 0, "accepted_items": 0},
            "diagnostics": {
                "repositories_total": 0,
                "repositories_succeeded": 0,
                "repositories_failed": 0,
                "repositories_empty": 0,
                "items_collected": 0,
                "warnings": ["GitHub source config is missing; collector skipped safely."],
                "errors": [],
            },
        }

    timeout = timeout_seconds or request_timeout(config)
    items = []
    warnings = []
    errors = []
    repos_total = 0
    repos_succeeded = 0
    repos_failed = 0
    repos_empty = 0
    seen_urls = set()
    rule = get_source_age_rule(category=category, source_family="github") if category else None

    for repo_cfg in iter_repositories(config, selected_category=category):
        repos_total += 1
        limit = int(repo_cfg.get("limit") or default_limit(config))
        try:
            if repo_cfg.get("source_type") != "release":
                warnings.append(
                    f"unsupported source_type for {repo_cfg.get('repo')}: {repo_cfg.get('source_type')}; skipped"
                )
                repos_empty += 1
                continue
            releases = fetch_releases(repo_cfg.get("repo"), limit, timeout)
            accepted = 0
            for release in releases:
                item = _release_item(repo_cfg, release if isinstance(release, dict) else {})
                decision = evaluate_source_item_age(item.get("created_at"), rule)
                if not decision.accepted:
                    if decision.reason:
                        warnings.append(
                            f"age rule skipped item for {repo_cfg.get('repo')}: {decision.reason}"
                        )
                    continue
                url = compact_text(item.get("url"))
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                items.append(item)
                accepted += 1
            if accepted > 0:
                repos_succeeded += 1
            else:
                repos_empty += 1
        except error.HTTPError as exc:
            repos_failed += 1
            errors.append(f"{repo_cfg.get('repo')}: HTTP {exc.code}")
        except Exception as exc:  # pragma: no cover - network/env variance
            repos_failed += 1
            errors.append(f"{repo_cfg.get('repo')}: {exc}")

    written_paths = write_items(items) if items else []
    diagnostics = {
        "repositories_total": repos_total,
        "repositories_succeeded": repos_succeeded,
        "repositories_failed": repos_failed,
        "repositories_empty": repos_empty,
        "items_collected": len(items),
        "warnings": warnings,
        "errors": errors,
    }
    return {
        "items": items,
        "paths": written_paths,
        "stats": {"repositories_loaded": repos_total, "accepted_items": len(items)},
        "diagnostics": diagnostics,
    }
