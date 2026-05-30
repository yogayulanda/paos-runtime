import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "intelligence"))

from collectors.threads.extractor import ThreadsPlaywrightAdapter
from collectors.threads.extractor import detect_login_wall
from collectors.threads.extractor import extract_threads_username
from collectors.threads.extractor import normalize_threads_permalink
from collectors.threads.models import dedupe_key


FIXTURES_DIR = ROOT / "tests" / "fixtures" / "threads"


def fixture_text(name):
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_normalize_permalink_supports_threads_net_and_threads_com():
    assert (
        normalize_threads_permalink(
            "https://www.threads.net/@swyx/post/ABC123?x=1"
        )
        == "https://www.threads.com/@swyx/post/ABC123"
    )
    assert (
        normalize_threads_permalink(
            "https://www.threads.com/@swyx/post/ABC123?x=1"
        )
        == "https://www.threads.com/@swyx/post/ABC123"
    )
    assert (
        normalize_threads_permalink("/@swyx/post/ABC123?x=1")
        == "https://www.threads.com/@swyx/post/ABC123"
    )


def test_username_extraction_works_for_threads_urls():
    assert (
        extract_threads_username("https://www.threads.com/@levelsio/post/XYZ789")
        == "levelsio"
    )
    assert (
        extract_threads_username("https://www.threads.net/@swyx/post/ABC123")
        == "swyx"
    )


def test_metric_and_action_lines_are_ignored_and_useful_lines_retained():
    adapter = ThreadsPlaywrightAdapter()
    block = fixture_text("candidate_block.txt")
    permalink = "https://www.threads.com/@someone/post/ABC123"

    assert adapter.is_useful_text("reply", permalink) is False
    assert adapter.is_useful_text("2.2K", permalink) is False
    assert adapter.is_useful_text("3d", permalink) is False
    assert adapter.is_useful_text(
        "This is the actual product insight worth keeping for intelligence routing.",
        permalink,
    ) is True

    extracted = adapter.extract_full_block_text(block, permalink)
    assert "actual product insight" in extracted
    assert "building in public" in extracted
    assert "Continue with Instagram" not in extracted
    assert "2.2K" not in extracted


def test_login_wall_detector_matches_expected_indicators():
    assert detect_login_wall(fixture_text("login_wall.txt"), 0) is True
    assert detect_login_wall("useful public posts visible here", 3) is False


def test_dedupe_key_prefers_url_and_falls_back_to_content_hash():
    item_with_url = {
        "platform": "threads",
        "source_type": "keyword",
        "category": "ai",
        "content": "same content",
        "url": "https://www.threads.com/@a/post/1",
    }
    assert dedupe_key(item_with_url) == "https://www.threads.com/@a/post/1"

    first = {
        "platform": "threads",
        "source_type": "account",
        "category": "builders",
        "content": "same content",
        "url": None,
    }
    second = {
        "platform": "threads",
        "source_type": "account",
        "category": "builders",
        "content": "same content",
        "url": None,
    }
    third = {
        "platform": "threads",
        "source_type": "account",
        "category": "builders",
        "content": "different content",
        "url": None,
    }

    assert dedupe_key(first) == dedupe_key(second)
    assert dedupe_key(first) != dedupe_key(third)
