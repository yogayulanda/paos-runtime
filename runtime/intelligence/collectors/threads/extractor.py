import os
import re
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

import requests
import yaml


ROOT = Path(__file__).resolve().parents[4]
RUNTIME_DIR = ROOT / ".runtime"
THREADS_BROWSER_PROFILE_DIR = RUNTIME_DIR / "browser-profiles" / "threads"
TOPICS_PATH = ROOT / "intelligence" / "topics.yaml"
DEBUG_BASE_DIR = ROOT / "debug" / "threads"
THREADS_HOME_URL = "https://www.threads.com/"
THREADS_API_URL = "https://graph.threads.net/v1.0/keyword_search"
THREADS_WEB_SEARCH_URL = "https://www.threads.com/search?q={query}"
THREADS_PROFILE_URL = "https://www.threads.com/@{username}"
THREADS_FIELDS = (
    "id,text,media_type,permalink,timestamp,"
    "username,has_replies,is_quote_post,is_reply"
)
SCRAPER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
THREADS_UI_TEXT = {
    "reply",
    "replies",
    "like",
    "likes",
    "repost",
    "reposts",
    "share",
    "follow",
    "following",
    "more",
    "view replies",
    "see translation",
    "translate",
    "quoted",
    "log in",
    "thread",
    "author",
}
THREADS_UI_PHRASES = (
    "For you",
    "New thread",
    "Search",
    "Messages",
    "Activity",
    "Profile",
    "Insights",
    "Saved",
    "Feeds",
    "Edit",
    "Ghost posts",
    "No replies yet",
)
THREADS_STOP_PHRASES = (
    "View activity",
    "Reply to ",
    "No replies yet",
)
LOGIN_WALL_INDICATORS = (
    "Log in",
    "Sign up",
    "Continue with Instagram",
    "Create new account",
)
ERROR_CODES = {
    "AUTH_NOT_VERIFIED",
    "LOGIN_REQUIRED",
    "PUBLIC_ACCESS_ONLY",
    "AUTHENTICATED_PROFILE_BLOCKED",
    "LOGIN_WALL_DETECTED",
    "CAPTCHA_OR_CHALLENGE",
    "BROWSER_TIMEOUT",
    "NETWORK_ERROR",
    "EXTRACTION_EMPTY",
    "LOCKED",
    "UNKNOWN_AUTH_STATE",
    "UNKNOWN_ERROR",
}
TIMESTAMP_PATTERNS = (
    r"^\d+[smhdwy]$",
    r"^\d{1,2}/\d{1,2}/\d{2,4}$",
    r"^\d{1,2}:\d{2}$",
)


def default_provider():
    if os.getenv("THREADS_ACCESS_TOKEN"):
        return "official"
    return "playwright"


def compact_text(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def sanitize_id(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip())
    cleaned = cleaned.strip("-._")
    return cleaned or datetime.now().strftime("%Y-%m-%d-%H%M%S-threads")


def debug_slug(value):
    return sanitize_id(value or "unknown")


def query_tags(query):
    return [
        token
        for token in re.findall(r"[A-Za-z0-9_-]+", query.lower())
        if token
    ]


def query_terms(query):
    return query_tags(query)


def relevance_score(query, text):
    terms = query_terms(query)
    cleaned = compact_text(text).lower()

    if not terms or not cleaned:
        return 0

    score = 0
    phrase = " ".join(terms)

    if phrase and phrase in cleaned:
        score += 4

    for index, term in enumerate(terms):
        if re.search(rf"\b{re.escape(term)}\b", cleaned):
            score += 3 if index == 0 else 1

    if len(terms) >= 2:
        for left, right in zip(terms, terms[1:]):
            if re.search(
                rf"\b{re.escape(left)}\b(?:\W+\w+){{0,3}}\W+\b{re.escape(right)}\b",
                cleaned,
            ):
                score += 2

    return score


def matched_keywords(text, keywords):
    lowered = compact_text(text).lower()
    matches = []

    for keyword in keywords or []:
        candidate = compact_text(keyword).lower()
        if candidate and candidate in lowered:
            matches.append(keyword)

    return matches


def detect_login_wall(visible_text, permalink_count):
    has_login_text = any(
        indicator in (visible_text or "")
        for indicator in LOGIN_WALL_INDICATORS
    )
    return permalink_count == 0 and has_login_text


def detect_challenge_page(visible_text):
    lowered = (visible_text or "").lower()
    return "captcha" in lowered or "challenge" in lowered


def normalize_threads_permalink(href):
    if not href:
        return ""

    if href.startswith("/"):
        href = f"https://www.threads.com{href}"

    if href.startswith("https://www.threads.net/"):
        href = href.replace("https://www.threads.net/", "https://www.threads.com/", 1)

    if not href.startswith("https://www.threads.com/"):
        return ""

    if "/post/" not in href:
        return ""

    return href.split("?", 1)[0]


def extract_threads_username(permalink):
    match = re.search(r"threads\.(?:net|com)/@([^/]+)/post/", permalink or "")
    return match.group(1) if match else ""


def load_topics():
    if not TOPICS_PATH.exists():
        raise SystemExit(
            "Topics registry is missing.\n"
            f"Expected file: {TOPICS_PATH}"
        )

    payload = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")) or {}
    topics = payload.get("topics", [])

    if not isinstance(topics, list):
        raise SystemExit(
            "Topics registry is invalid.\n"
            "Expected `topics` to be a YAML list."
        )

    return [
        compact_text(topic)
        for topic in topics
        if isinstance(topic, str) and compact_text(topic)
    ]


def normalize_post(post):
    raw_id = post.get("id") or post.get("permalink") or ""
    permalink = normalize_threads_permalink(post.get("permalink", ""))

    return {
        "raw_id": sanitize_id(raw_id),
        "username": post.get("username", ""),
        "permalink": permalink,
        "text": compact_text(post.get("text", "")),
        "timestamp": post.get("timestamp", ""),
        "media_type": post.get("media_type", ""),
        "has_replies": post.get("has_replies", False),
        "is_quote_post": post.get("is_quote_post", False),
        "is_reply": post.get("is_reply", False),
        "extraction_mode": post.get("extraction_mode", ""),
        "discovered_via_query": post.get("discovered_via_query", ""),
    }


def classify_threads_error(message, diagnostics=None, authenticated=False):
    lowered = (message or "").lower()
    diagnostics = diagnostics or {}

    if diagnostics.get("login_wall_detected"):
        if authenticated:
            return "AUTHENTICATED_PROFILE_BLOCKED"
        return "LOGIN_WALL_DETECTED"

    if detect_challenge_page(diagnostics.get("visible_text", "")) or (
        "captcha" in lowered or "challenge" in lowered
    ):
        return "CAPTCHA_OR_CHALLENGE"

    if "timeout" in lowered or "timed out" in lowered:
        return "BROWSER_TIMEOUT"

    if "network" in lowered or "err_" in lowered:
        return "NETWORK_ERROR"

    if diagnostics.get("extracted_posts_count", 0) == 0:
        return "EXTRACTION_EMPTY"

    return "UNKNOWN_ERROR"


def build_error(source_type, source_name, code, message):
    return {
        "source_type": source_type,
        "source_name": source_name,
        "code": code if code in ERROR_CODES else "UNKNOWN_ERROR",
        "message": message,
    }


class ThreadsApiAdapter:
    def __init__(self):
        self.debug_enabled = False
        self.debug_events = []
        self.authenticated = False
        self.timeout_seconds = 180
        self.extraction_mode = "deep"

    @property
    def provider_name(self):
        raise NotImplementedError

    def search(self, query, limit):
        raise NotImplementedError

    def fetch_account_posts(self, username, limit):
        raise SystemExit(
            f"Provider `{self.provider_name}` does not support public account feed collection."
        )

    def configure(
        self,
        debug=False,
        authenticated=False,
        timeout_seconds=180,
        extraction_mode="deep",
    ):
        self.debug_enabled = debug
        self.authenticated = authenticated
        self.timeout_seconds = timeout_seconds
        self.extraction_mode = extraction_mode
        self.debug_events = []
        return self

    def configure_debug(self, enabled=False):
        self.debug_enabled = enabled
        self.debug_events = []
        return self

    def consume_debug_events(self):
        events = list(self.debug_events)
        self.debug_events = []
        return events

    def record_debug_event(self, payload):
        self.debug_events.append(payload)


class OfficialThreadsApiAdapter(ThreadsApiAdapter):
    def __init__(self, access_token):
        super().__init__()
        self.access_token = access_token

    @property
    def provider_name(self):
        return "official"

    def search(self, query, limit):
        params = {
            "q": query,
            "search_type": "TOP",
            "fields": THREADS_FIELDS,
            "limit": max(1, min(limit, 100)),
            "access_token": self.access_token,
        }

        response = requests.get(
            THREADS_API_URL,
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        return payload.get("data", [])

    def fetch_account_posts(self, username, limit):
        raise SystemExit(
            "Official Threads account feed collection is not wired yet.\n"
            "Use `--provider playwright` for public account collection."
        )


class ThreadsScraperAdapter(ThreadsApiAdapter):
    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": SCRAPER_USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    @property
    def provider_name(self):
        return "scraper"

    def search(self, query, limit):
        url = THREADS_WEB_SEARCH_URL.format(
            query=quote_plus(query)
        )
        response = self.session.get(
            url,
            timeout=30,
        )
        response.raise_for_status()

        posts = self.extract_posts(response.text, limit)
        if posts:
            return posts

        raise SystemExit(
            "Threads scraper fallback could not extract public search results "
            "from the simple HTTP response.\n"
            "Limitation: Threads search currently returns a JS-driven shell "
            "without stable server-rendered post results for this query.\n"
            "Use `--provider official` with THREADS_ACCESS_TOKEN, or `--provider playwright`."
        )

    def fetch_account_posts(self, username, limit):
        response = self.session.get(
            THREADS_PROFILE_URL.format(username=username),
            timeout=30,
        )
        response.raise_for_status()

        posts = self.extract_posts(response.text, limit, username=username)
        if posts:
            return posts

        raise SystemExit(
            "Threads scraper fallback could not extract public account posts "
            "from the simple HTTP response.\n"
            "Use `--provider playwright` for account collection."
        )

    def extract_posts(self, html, limit, username=""):
        posts = []
        seen = set()
        pattern = (
            r"https://www\.threads\.(?:net|com)/@(?P<username>[^/\"\s]+)/post/"
            r"(?P<post_id>[A-Za-z0-9_-]+)"
        )

        for match in re.finditer(pattern, html):
            permalink = normalize_threads_permalink(match.group(0))
            post_id = match.group("post_id")
            post_username = match.group("username")

            if username and post_username.lower() != username.lower():
                continue

            if permalink in seen:
                continue

            text = self.extract_text_near_permalink(html, match.group(0))
            if not text:
                continue

            seen.add(permalink)
            posts.append(
                {
                    "id": post_id,
                    "text": text,
                    "permalink": permalink,
                    "timestamp": "",
                    "username": post_username,
                    "media_type": "TEXT",
                    "has_replies": False,
                    "is_quote_post": False,
                    "is_reply": False,
                    "extraction_mode": "scraper_snippet",
                }
            )

            if len(posts) >= limit:
                break

        return posts

    def extract_text_near_permalink(self, html, permalink):
        window = 4000
        index = html.find(permalink)

        if index == -1:
            return ""

        segment = html[max(0, index - window): index + window]
        candidates = re.findall(r'"text":"([^"]+)"', segment)

        for candidate in candidates:
            text = self.clean_scraped_text(candidate)
            if text:
                return text

        return ""

    def clean_scraped_text(self, text):
        cleaned = unescape(text)
        cleaned = cleaned.replace("\\n", " ").replace("\\/", "/")
        return compact_text(cleaned)


class ThreadsPlaywrightAdapter(ThreadsApiAdapter):
    def __init__(self, authenticated=False, timeout_seconds=180):
        super().__init__()
        self.authenticated = authenticated
        self.timeout_seconds = timeout_seconds
        self.search_url_template = THREADS_WEB_SEARCH_URL
        self.profile_url_template = THREADS_PROFILE_URL
        self.permalink_timeout_ms = 12000

    @property
    def provider_name(self):
        return "playwright"

    def search(self, query, limit):
        search_url = self.search_url_template.format(
            query=quote_plus(query)
        )
        context = {
            "source_type": "keyword",
            "source_name": query,
            "url": search_url,
        }
        posts, diagnostics = self._run_browser_session(
            url=search_url,
            context=context,
            extractor=lambda page, detail_page: self.extract_search_posts(
                page,
                detail_page,
                query,
                limit,
            ),
        )
        self.record_debug_event(diagnostics)

        if posts:
            return posts

        if diagnostics["challenge_detected"]:
            raise SystemExit(
                "Threads challenge or captcha detected while loading the search page."
            )

        if diagnostics["permalink_count"] > 0:
            raise SystemExit(
                "Playwright found post links but could not extract useful post text."
            )

        raise SystemExit(
            "Playwright loaded the page but no public posts were extracted."
        )

    def fetch_account_posts(self, username, limit):
        profile_url = self.profile_url_template.format(username=username)
        context = {
            "source_type": "account",
            "source_name": username,
            "url": profile_url,
        }
        posts, diagnostics = self._run_browser_session(
            url=profile_url,
            context=context,
            extractor=lambda page, detail_page: self.extract_account_posts(
                page,
                detail_page,
                username,
                limit,
            ),
        )
        self.record_debug_event(diagnostics)

        if posts:
            return posts

        if diagnostics["challenge_detected"]:
            raise SystemExit(
                "Threads challenge or captcha detected while loading the account page."
            )

        if diagnostics["login_wall_detected"]:
            raise SystemExit(
                "Threads session appears logged out or blocked by login wall."
            )

        if diagnostics["permalink_count"] > 0:
            raise SystemExit(
                f"Playwright found post links for @{username} but could not extract useful public post text."
            )

        raise SystemExit(
            f"Playwright loaded @{username} but no public posts were extracted."
        )

    def _run_browser_session(self, url, context, extractor):
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
            try:
                from playwright._impl._errors import TargetClosedError
            except Exception:
                class TargetClosedError(Exception):
                    pass
        except ModuleNotFoundError:
            raise SystemExit(
                "Playwright is not installed.\n"
                "Install instructions:\n"
                "1. pip install playwright\n"
                "2. python -m playwright install chromium\n"
                "3. Re-run this command with `--provider playwright`."
            )

        diagnostics = {
            "provider": self.provider_name,
            "source_type": context["source_type"],
            "source_name": context["source_name"],
            "url": url,
            "extraction_mode": self.extraction_mode,
            "page_loaded": False,
            "permalink_count": 0,
            "visible_text_length": 0,
            "login_wall_detected": False,
            "raw_candidates_count": 0,
            "extracted_posts_count": 0,
            "href_snapshot_count": 0,
            "unique_post_url_count": 0,
            "detail_pages_attempted": 0,
            "detail_pages_failed": 0,
            "scroll_attempts": 0,
            "extraction_duration_seconds": 0,
            "page_closed": False,
            "detail_page_closed": False,
            "context_closed": False,
            "browser_closed": False,
            "cleanup_error": "",
            "artifacts": {},
        }

        with sync_playwright() as playwright:
            browser = None
            context_handle = None
            page = None
            detail_page = None

            try:
                if self.authenticated:
                    THREADS_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                    context_handle = playwright.chromium.launch_persistent_context(
                        str(THREADS_BROWSER_PROFILE_DIR),
                        headless=True,
                    )
                    pages = context_handle.pages
                    page = pages[0] if pages else context_handle.new_page()
                    detail_page = context_handle.new_page()
                else:
                    browser = playwright.chromium.launch(headless=True)
                    context_handle = browser.new_context()
                    page = context_handle.new_page()
                    detail_page = context_handle.new_page()

                page.set_default_timeout(min(self.timeout_seconds, 180) * 1000)
                detail_page.set_default_timeout(min(self.timeout_seconds, 180) * 1000)

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=min(self.timeout_seconds, 180) * 1000,
                )
                diagnostics["page_loaded"] = True
                page.wait_for_timeout(3000)
                self.dismiss_common_dialogs(page)
                page.wait_for_timeout(1000)

                try:
                    page.wait_for_selector(
                        "a[href*='/post/']",
                        timeout=10000,
                    )
                except PlaywrightTimeoutError:
                    pass

                diagnostics.update(self.capture_page_state(page, context))
                extraction_started = time.perf_counter()
                posts, extraction_meta = extractor(page, detail_page)
                diagnostics["extraction_duration_seconds"] = round(
                    time.perf_counter() - extraction_started,
                    2,
                )
                diagnostics["raw_candidates_count"] = extraction_meta["raw_candidates_count"]
                diagnostics["extracted_posts_count"] = len(posts)
                diagnostics["raw_text_length"] = extraction_meta.get("raw_text_length", 0)
                diagnostics["cleaned_text_length"] = extraction_meta.get("cleaned_text_length", 0)
                diagnostics["removed_ui_lines_count"] = extraction_meta.get("removed_ui_lines_count", 0)
                diagnostics["href_snapshot_count"] = extraction_meta.get("href_snapshot_count", 0)
                diagnostics["unique_post_url_count"] = extraction_meta.get("unique_post_url_count", 0)
                diagnostics["detail_pages_attempted"] = extraction_meta.get("detail_pages_attempted", 0)
                diagnostics["detail_pages_failed"] = extraction_meta.get("detail_pages_failed", 0)
                diagnostics["scroll_attempts"] = extraction_meta.get("scroll_attempts", 0)

                return posts, diagnostics
            finally:
                cleanup_errors = []

                def safe_close(target, label, close_method_name="close", **kwargs):
                    if target is None:
                        return False

                    try:
                        is_closed = getattr(target, "is_closed", None)
                        if callable(is_closed) and is_closed():
                            return True
                    except Exception:
                        pass

                    try:
                        getattr(target, close_method_name)(**kwargs)
                        return True
                    except (TargetClosedError, PlaywrightError, Exception) as exc:
                        cleanup_errors.append(f"{label}:{exc}")
                        return False

                diagnostics["detail_page_closed"] = safe_close(
                    detail_page,
                    "detail_page",
                    run_before_unload=False,
                )
                diagnostics["page_closed"] = safe_close(
                    page,
                    "page",
                    run_before_unload=False,
                )
                diagnostics["context_closed"] = safe_close(
                    context_handle,
                    "context",
                )
                diagnostics["browser_closed"] = safe_close(
                    browser,
                    "browser",
                )
                diagnostics["cleanup_error"] = " | ".join(cleanup_errors)

    def capture_page_state(self, page, context):
        visible_text = ""
        html = ""
        permalink_count = 0

        try:
            html = page.content()
        except Exception:
            html = ""

        try:
            permalink_count = page.locator("a[href*='/post/']").count()
        except Exception:
            permalink_count = 0

        try:
            body_locator = page.locator("body")
            if body_locator.count() > 0:
                visible_text = body_locator.first.inner_text(timeout=2000)
        except Exception:
            visible_text = ""

        artifacts = {}
        if self.debug_enabled:
            artifacts = self.save_debug_artifacts(
                source_type=context["source_type"],
                source_name=context["source_name"],
                html=html,
                visible_text=visible_text,
                page=page,
            )

        return {
            "permalink_count": permalink_count,
            "visible_text_length": len(visible_text or ""),
            "visible_text": visible_text or "",
            "login_wall_detected": detect_login_wall(visible_text, permalink_count),
            "challenge_detected": detect_challenge_page(visible_text),
            "artifacts": artifacts,
        }

    def save_debug_artifacts(self, source_type, source_name, html, visible_text, page):
        output_dir = DEBUG_BASE_DIR / source_type
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = debug_slug(source_name)

        html_path = output_dir / f"{slug}.html"
        png_path = output_dir / f"{slug}.png"
        txt_path = output_dir / f"{slug}.txt"

        html_path.write_text(html or "", encoding="utf-8")
        txt_path.write_text(visible_text or "", encoding="utf-8")

        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            png_path.write_bytes(b"")

        return {
            "html": str(html_path),
            "png": str(png_path),
            "txt": str(txt_path),
        }

    def dismiss_common_dialogs(self, page):
        button_texts = [
            "Not now",
            "Not Now",
            "Maybe later",
            "Close",
        ]

        for text in button_texts:
            locator = page.get_by_text(text, exact=True)
            try:
                if locator.count() > 0:
                    locator.first.click(timeout=1000)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    def extract_search_posts(self, page, detail_page, query, limit):
        posts, extraction_meta = self.extract_posts_from_listing(
            page,
            detail_page,
            limit=limit,
        )

        for post in posts:
            post["discovered_via_query"] = query

        return posts, extraction_meta

    def extract_account_posts(self, page, detail_page, username, limit):
        if self.extraction_mode == "fast":
            return self.extract_posts_from_listing_fast(
                page,
                limit=limit,
                expected_username=username,
            )

        return self.extract_posts_from_listing_deep(
            page,
            detail_page,
            limit=limit,
            expected_username=username,
        )

    def extract_posts_from_listing(
        self,
        page,
        detail_page,
        limit,
        expected_username="",
    ):
        return self.extract_posts_from_listing_deep(
            page,
            detail_page,
            limit,
            expected_username=expected_username,
        )

    def extract_posts_from_listing_deep(
        self,
        page,
        detail_page,
        limit,
        expected_username="",
    ):
        posts = []
        seen = set()
        snapshot_meta = self.snapshot_post_urls(
            page,
            limit=max(1, limit) * 8,
            scrolls=2 if self.authenticated else 0,
        )
        raw_candidates_count = snapshot_meta["href_snapshot_count"]
        unique_urls = snapshot_meta["urls"]
        total_raw_text_length = 0
        total_cleaned_text_length = 0
        total_removed_ui_lines = 0
        detail_pages_attempted = 0
        detail_pages_failed = 0

        for permalink in unique_urls:
            if not permalink or permalink in seen:
                continue

            username = self.extract_username(permalink)
            if expected_username and username.lower() != expected_username.lower():
                continue

            post_id = self.extract_post_id(permalink)
            snippet = self.extract_post_text(page, permalink)
            detail_pages_attempted += 1
            detail = self.extract_full_post_text(
                detail_page,
                permalink,
            )
            if not detail["text"]:
                detail_pages_failed += 1

            text = detail["text"] or snippet["text"]
            extraction_mode = (
                detail["mode"] or snippet["mode"] or "search_snippet"
            )
            total_raw_text_length += detail["raw_text_length"] or snippet["raw_text_length"]
            total_cleaned_text_length += detail["cleaned_text_length"] or snippet["cleaned_text_length"]
            total_removed_ui_lines += detail["removed_ui_lines_count"] or snippet["removed_ui_lines_count"]

            if not post_id or not text:
                continue

            seen.add(permalink)
            posts.append(
                {
                    "id": post_id,
                    "text": text,
                    "permalink": permalink,
                    "timestamp": "",
                    "username": username,
                    "media_type": "TEXT",
                    "has_replies": False,
                    "is_quote_post": False,
                    "is_reply": False,
                    "extraction_mode": extraction_mode,
                    "raw_text_length": detail["raw_text_length"] or snippet["raw_text_length"],
                    "cleaned_text_length": detail["cleaned_text_length"] or snippet["cleaned_text_length"],
                    "removed_ui_lines_count": detail["removed_ui_lines_count"] or snippet["removed_ui_lines_count"],
                }
            )

            if len(posts) >= limit:
                break

        return posts, {
            "raw_candidates_count": raw_candidates_count,
            "href_snapshot_count": snapshot_meta["href_snapshot_count"],
            "unique_post_url_count": snapshot_meta["unique_post_url_count"],
            "detail_pages_attempted": detail_pages_attempted,
            "detail_pages_failed": detail_pages_failed,
            "scroll_attempts": snapshot_meta["scroll_attempts"],
            "raw_text_length": total_raw_text_length,
            "cleaned_text_length": total_cleaned_text_length,
            "removed_ui_lines_count": total_removed_ui_lines,
        }

    def extract_posts_from_listing_fast(
        self,
        page,
        limit,
        expected_username="",
    ):
        posts = []
        seen = set()
        snapshot_meta = self.snapshot_post_urls(
            page,
            limit=max(1, limit) * 4,
            scrolls=2 if self.authenticated else 0,
        )
        total_raw_text_length = 0
        total_cleaned_text_length = 0
        total_removed_ui_lines = 0

        for permalink in snapshot_meta["urls"]:
            if not permalink or permalink in seen:
                continue

            username = self.extract_username(permalink)
            if expected_username and username.lower() != expected_username.lower():
                continue

            post_id = self.extract_post_id(permalink)
            snippet = self.extract_post_text(page, permalink)
            text = snippet["text"]
            if not post_id or not text:
                continue

            total_raw_text_length += snippet["raw_text_length"]
            total_cleaned_text_length += snippet["cleaned_text_length"]
            total_removed_ui_lines += snippet["removed_ui_lines_count"]

            seen.add(permalink)
            posts.append(
                {
                    "id": post_id,
                    "text": text,
                    "permalink": permalink,
                    "timestamp": "",
                    "username": username,
                    "media_type": "TEXT",
                    "has_replies": False,
                    "is_quote_post": False,
                    "is_reply": False,
                    "extraction_mode": "listing_snapshot",
                    "raw_text_length": snippet["raw_text_length"],
                    "cleaned_text_length": snippet["cleaned_text_length"],
                    "removed_ui_lines_count": snippet["removed_ui_lines_count"],
                }
            )

            if len(posts) >= limit:
                break

        return posts, {
            "raw_candidates_count": snapshot_meta["href_snapshot_count"],
            "href_snapshot_count": snapshot_meta["href_snapshot_count"],
            "unique_post_url_count": snapshot_meta["unique_post_url_count"],
            "detail_pages_attempted": 0,
            "detail_pages_failed": 0,
            "scroll_attempts": snapshot_meta["scroll_attempts"],
            "raw_text_length": total_raw_text_length,
            "cleaned_text_length": total_cleaned_text_length,
            "removed_ui_lines_count": total_removed_ui_lines,
        }

    def snapshot_post_urls(self, page, limit, scrolls=0):
        hrefs = []
        scroll_attempts = 0

        for _ in range(max(0, scrolls) + 1):
            hrefs.extend(self.get_post_hrefs_snapshot(page))
            unique_urls = self.unique_ordered(
                [
                    self.normalize_permalink(href)
                    for href in hrefs
                    if self.normalize_permalink(href)
                ]
            )
            if len(unique_urls) >= limit:
                return {
                    "urls": unique_urls[:limit],
                    "href_snapshot_count": len(hrefs),
                    "unique_post_url_count": len(unique_urls),
                    "scroll_attempts": scroll_attempts,
                }

            if scroll_attempts >= scrolls:
                break

            try:
                page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
                page.wait_for_timeout(1000)
            except Exception:
                break
            scroll_attempts += 1

        unique_urls = self.unique_ordered(
            [
                self.normalize_permalink(href)
                for href in hrefs
                if self.normalize_permalink(href)
            ]
        )
        return {
            "urls": unique_urls[:limit],
            "href_snapshot_count": len(hrefs),
            "unique_post_url_count": len(unique_urls),
            "scroll_attempts": scroll_attempts,
        }

    def get_post_hrefs_snapshot(self, page):
        try:
            hrefs = page.eval_on_selector_all(
                "a[href*='/post/']",
                "(els) => els.map((a) => a.href || a.getAttribute('href') || '')",
            )
            return [href for href in hrefs if href]
        except Exception:
            return []

    def extract_full_post_text(self, page, permalink):
        try:
            page.goto(
                permalink,
                wait_until="domcontentloaded",
                timeout=self.permalink_timeout_ms,
            )
            page.wait_for_timeout(2000)
            self.dismiss_common_dialogs(page)
            page.wait_for_timeout(500)

            candidate_blocks = []

            article_locator = page.locator("article, [role='article']")
            article_count = min(article_locator.count(), 3)
            for index in range(article_count):
                candidate_blocks.append(
                    article_locator.nth(index).inner_text(timeout=1000)
                )

            nearest = self.pick_best_full_text(candidate_blocks, permalink)
            if nearest["text"]:
                nearest["mode"] = "nearest_post_block"
                return nearest

            fallback_blocks = []
            main_locator = page.locator("main")
            if main_locator.count() > 0:
                fallback_blocks.append(
                    main_locator.first.inner_text(timeout=1000)
                )

            section_locator = page.locator("section")
            section_count = min(section_locator.count(), 2)
            for index in range(section_count):
                fallback_blocks.append(
                    section_locator.nth(index).inner_text(timeout=1000)
                )

            body_locator = page.locator("body")
            if body_locator.count() > 0:
                fallback_blocks.append(
                    body_locator.first.inner_text(timeout=1000)
                )

            fallback = self.pick_best_full_text(fallback_blocks, permalink)
            fallback["mode"] = "fallback_full_post" if fallback["text"] else ""
            return fallback
        except Exception:
            return self.empty_text_result()

    def extract_post_text(self, page, permalink):
        selector = (
            f"a[href='{permalink}'], "
            f"a[href='{permalink.replace('https://www.threads.com', '').replace('https://www.threads.net', '')}']"
        )
        anchor = page.locator(selector).first

        try:
            if anchor.count() == 0:
                return self.empty_text_result()

            candidate_blocks = []

            article = anchor.locator(
                "xpath=ancestor::*[self::article or @role='article'][1]"
            )
            if article.count() > 0:
                candidate_blocks.append(article.first.inner_text(timeout=1000))

            for depth in range(1, 5):
                parent = anchor.locator(
                    f"xpath=ancestor::*[self::div or self::section or self::li][{depth}]"
                )
                if parent.count() > 0:
                    candidate_blocks.append(parent.first.inner_text(timeout=1000))
        except Exception:
            return self.empty_text_result()

        return self.pick_best_text(candidate_blocks, permalink)

    def pick_best_text(self, blocks, permalink):
        candidates = []

        for block in blocks:
            for line in self.extract_candidate_lines(block):
                cleaned_line, removed = self.clean_ui_line(line)
                if not self.is_useful_text(cleaned_line, permalink):
                    continue

                score = self.score_text(cleaned_line)
                candidates.append(
                    (
                        score,
                        cleaned_line,
                        len(line),
                        len(cleaned_line),
                        removed,
                    )
                )

        if not candidates:
            return self.empty_text_result()

        candidates.sort(key=lambda item: item[0], reverse=True)
        best = candidates[0]
        cleaned = compact_text(best[1])[:2000]
        return {
            "text": cleaned,
            "raw_text_length": best[2],
            "cleaned_text_length": len(cleaned),
            "removed_ui_lines_count": best[4],
            "mode": "search_snippet",
        }

    def pick_best_full_text(self, blocks, permalink):
        candidates = []

        for block in blocks:
            result = self.extract_full_block_text(block, permalink)
            text = result["text"]
            if not text:
                continue

            score = self.score_text(text) + len(text)
            candidates.append((score, text, result))

        if not candidates:
            return self.empty_text_result()

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][2]

    def extract_full_block_text(self, block, permalink):
        useful_lines = []
        removed_ui_lines_count = 0
        raw_text_length = len(block or "")

        for raw_line in block.splitlines():
            line = compact_text(raw_line)
            cleaned_line, removed = self.clean_ui_line(line)
            removed_ui_lines_count += removed
            if not self.is_useful_full_line(cleaned_line, permalink):
                continue

            useful_lines.append(cleaned_line)

        useful_lines = self.unique_ordered(useful_lines)
        if not useful_lines:
            return {
                "text": "",
                "raw_text_length": raw_text_length,
                "cleaned_text_length": 0,
                "removed_ui_lines_count": removed_ui_lines_count,
                "mode": "",
            }

        text = compact_text("\n".join(useful_lines))[:2000]
        return {
            "text": text,
            "raw_text_length": raw_text_length,
            "cleaned_text_length": len(text),
            "removed_ui_lines_count": removed_ui_lines_count,
            "mode": "",
        }

    def extract_candidate_lines(self, block):
        lines = []

        for raw_line in block.splitlines():
            line = compact_text(raw_line)
            if line:
                lines.append(line)

        return self.unique_ordered(lines)

    def is_useful_full_line(self, text, permalink):
        if not text:
            return False

        lowered = text.lower()

        if lowered in THREADS_UI_TEXT:
            return False

        if text == permalink:
            return False

        if text.startswith("http://") or text.startswith("https://"):
            return False

        if "/post/" in text:
            return False

        if self.looks_like_timestamp(text):
            return False

        if self.looks_like_metric_line(text):
            return False

        if self.looks_like_action_only(text):
            return False

        if len(text) < 4:
            return False

        return True

    def is_useful_text(self, text, permalink):
        lowered = text.lower()

        if len(text) < 20:
            return False

        if lowered in THREADS_UI_TEXT:
            return False

        if text == permalink:
            return False

        if text.startswith("http://") or text.startswith("https://"):
            return False

        if "/post/" in text:
            return False

        if self.looks_like_timestamp(text):
            return False

        if self.looks_like_metric_line(text):
            return False

        if self.looks_like_action_only(text):
            return False

        return True

    def clean_ui_line(self, line):
        if not line:
            return "", 0

        removed = 0
        cleaned = line

        while True:
            matched = False
            for phrase in THREADS_UI_PHRASES:
                prefix = f"{phrase} "
                if cleaned.startswith(prefix):
                    cleaned = compact_text(cleaned[len(prefix):])
                    removed += 1
                    matched = True
                    break
                if cleaned == phrase:
                    return "", removed + 1
            if not matched:
                break

        if cleaned.startswith("Reply to ") or cleaned.startswith("Reply to @"):
            return "", removed + 1

        if cleaned.startswith("No replies yet"):
            return "", removed + 1

        for phrase in THREADS_STOP_PHRASES:
            index = cleaned.find(phrase)
            if index > 0:
                cleaned = compact_text(cleaned[:index])
                removed += 1
                break
            if index == 0:
                return "", removed + 1

        return cleaned, removed

    def looks_like_timestamp(self, text):
        cleaned = text.strip().lower()

        for pattern in TIMESTAMP_PATTERNS:
            if re.match(pattern, cleaned):
                return True

        return False

    def looks_like_action_only(self, text):
        words = re.findall(r"[a-zA-Z]+", text.lower())
        if not words:
            return True

        if len(words) <= 4 and all(word in THREADS_UI_TEXT for word in words):
            return True

        return False

    def looks_like_metric_line(self, text):
        cleaned = text.strip().lower()

        if re.match(r"^\d+(?:\.\d+)?[kmb]?(?:\s+views)?$", cleaned):
            return True

        if re.match(r"^[\d\s.,kmb]+$", cleaned):
            return True

        return False

    def score_text(self, text):
        words = re.findall(r"[A-Za-z0-9']+", text)
        score = len(text) + (len(words) * 10)

        if len(words) >= 6:
            score += 50

        if any(word.lower() not in THREADS_UI_TEXT for word in words):
            score += 25

        return score

    def empty_text_result(self):
        return {
            "text": "",
            "raw_text_length": 0,
            "cleaned_text_length": 0,
            "removed_ui_lines_count": 0,
            "mode": "",
        }

    def unique_ordered(self, values):
        seen = set()
        ordered = []

        for value in values:
            if value in seen:
                continue

            seen.add(value)
            ordered.append(value)

        return ordered

    def normalize_permalink(self, href):
        return normalize_threads_permalink(href)

    def extract_post_id(self, permalink):
        match = re.search(r"/post/([A-Za-z0-9_-]+)", permalink)
        return match.group(1) if match else ""

    def extract_username(self, permalink):
        return extract_threads_username(permalink)


def resolve_adapter(provider, debug=False):
    return resolve_adapter_with_auth(
        provider=provider,
        debug=debug,
        authenticated=False,
        timeout_seconds=180,
        extraction_mode="deep",
    )


def resolve_adapter_with_auth(
    provider,
    debug=False,
    authenticated=False,
    timeout_seconds=180,
    extraction_mode="deep",
):
    access_token = os.getenv("THREADS_ACCESS_TOKEN")

    if authenticated and provider != "playwright":
        raise SystemExit(
            "Authenticated Threads session mode currently supports only `--provider playwright`."
        )

    if provider == "official":
        if access_token:
            return OfficialThreadsApiAdapter(access_token).configure(
                debug=debug,
                authenticated=authenticated,
                timeout_seconds=timeout_seconds,
                extraction_mode=extraction_mode,
            )

        raise SystemExit(
            "THREADS_ACCESS_TOKEN is not configured.\n"
            "Setup required:\n"
            "1. Create a Meta app with Threads API access.\n"
            "2. Generate a Threads user access token with "
            "`threads_basic` and `threads_keyword_search`.\n"
            "3. Export THREADS_ACCESS_TOKEN in your shell.\n"
            "4. Re-run this command or use `--provider playwright`."
        )

    if provider == "scraper":
        return ThreadsScraperAdapter().configure(
            debug=debug,
            authenticated=authenticated,
            timeout_seconds=timeout_seconds,
            extraction_mode=extraction_mode,
        )

    if provider == "playwright":
        return ThreadsPlaywrightAdapter(
            authenticated=authenticated,
            timeout_seconds=timeout_seconds,
        ).configure(
            debug=debug,
            authenticated=authenticated,
            timeout_seconds=timeout_seconds,
            extraction_mode=extraction_mode,
        )

    if access_token:
        return OfficialThreadsApiAdapter(access_token).configure(
            debug=debug,
            authenticated=authenticated,
            timeout_seconds=timeout_seconds,
            extraction_mode=extraction_mode,
        )

    return ThreadsPlaywrightAdapter(
        authenticated=authenticated,
        timeout_seconds=timeout_seconds,
    ).configure(
        debug=debug,
        authenticated=authenticated,
        timeout_seconds=timeout_seconds,
        extraction_mode=extraction_mode,
    )
