import argparse
import os
import shutil
import time
from pathlib import Path

import yaml

from collectors.threads.extractor import ROOT
from collectors.threads.extractor import THREADS_BROWSER_PROFILE_DIR
from collectors.threads.extractor import THREADS_HOME_URL
from collectors.threads.extractor import THREADS_PROFILE_URL
from collectors.threads.extractor import detect_challenge_page
from collectors.threads.extractor import detect_login_wall


DEBUG_DIR = ROOT / "debug" / "threads" / "auth"
THREADS_CONFIG_PATH = ROOT / "runtime" / "intelligence" / "sources" / "threads.yaml"
HOME_IDENTITY_TEXT_MARKERS = (
    "Log out",
    "Switch profiles",
    "Settings",
    "Pengaturan",
    "Keluar",
    "Cambiar de perfil",
    "Configuracion",
)
AUTH_COOKIE_CANDIDATES = {"sessionid", "ds_user_id", "csrftoken", "ig_did"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage the persistent authenticated Threads browser profile."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login")
    login_parser.add_argument(
        "--headless",
        action="store_true",
        help="Launch the login browser in headless mode.",
    )
    login_parser.add_argument(
        "--wait-timeout-seconds",
        type=int,
        default=600,
        help="Maximum wait time for authenticated session detection.",
    )

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument(
        "--debug",
        action="store_true",
        help="Save auth debug artifacts for the home and expected profile checks.",
    )

    logout_parser = subparsers.add_parser("logout")
    logout_parser.add_argument("--yes", action="store_true")

    return parser.parse_args()


def launch_persistent_context(playwright, headless):
    THREADS_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(THREADS_BROWSER_PROFILE_DIR),
        headless=headless,
    )


def capture_page_state(page):
    body_text = ""
    body = page.locator("body")
    if body.count() > 0:
        body_text = body.first.inner_text(timeout=2000)

    permalink_count = page.locator("a[href*='/post/']").count()
    title = page.title()
    current_url = page.url
    html = page.content()

    return {
        "title": title,
        "current_url": current_url,
        "visible_text": body_text or "",
        "visible_text_length": len(body_text or ""),
        "permalink_count": permalink_count,
        "login_wall_detected": detect_login_wall(body_text, permalink_count),
        "challenge_detected": detect_challenge_page(body_text),
        "html": html or "",
    }


def save_debug_artifacts(page, slug, state):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    png_path = DEBUG_DIR / f"{slug}.png"
    html_path = DEBUG_DIR / f"{slug}.html"
    txt_path = DEBUG_DIR / f"{slug}.txt"

    page.screenshot(path=str(png_path), full_page=True)
    html_path.write_text(state["html"], encoding="utf-8")
    txt_path.write_text(state["visible_text"], encoding="utf-8")

    return {
        "png": str(png_path),
        "html": str(html_path),
        "txt": str(txt_path),
    }


def identity_evidence_from_state(state):
    evidence = []
    visible_text = state.get("visible_text", "")

    for indicator in HOME_IDENTITY_TEXT_MARKERS:
        if indicator in visible_text:
            evidence.append(f"home_text:{indicator}")

    return evidence


def profile_identity_evidence(profile_state, expected_username):
    if not profile_state or not expected_username:
        return []

    evidence = []
    expected_handle = f"@{expected_username}"
    visible_text = profile_state.get("visible_text", "")
    lowered_text = visible_text.lower()
    lowered_username = expected_username.lower()
    lowered_title = (profile_state.get("title") or "").lower()

    if (
        not profile_state["login_wall_detected"]
        and not profile_state["challenge_detected"]
        and profile_state["current_url"].startswith("https://www.threads.com/@")
        and profile_state["permalink_count"] > 0
    ):
        evidence.append("expected_profile_accessible")

    if (
        expected_handle.lower() in lowered_text
        or lowered_username in lowered_text
        or lowered_username in lowered_title
    ):
        evidence.append("expected_profile_visible")

    return evidence


def cookie_identity_evidence(cookies):
    evidence = []
    by_name = {cookie.get("name"): cookie for cookie in cookies or []}

    for name in sorted(AUTH_COOKIE_CANDIDATES):
        if name in by_name:
            evidence.append(f"cookie:{name}")

    return evidence


def load_expected_username():
    from_env = os.getenv("THREADS_EXPECTED_USERNAME", "").strip()
    if from_env:
        return from_env, "env"

    if not THREADS_CONFIG_PATH.exists():
        return "", "none"

    payload = yaml.safe_load(THREADS_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    categories = payload.get("categories") or {}
    if not isinstance(categories, dict):
        return "", "none"

    for _category, details in categories.items():
        accounts = (details or {}).get("accounts") or []
        if not isinstance(accounts, list):
            continue
        for account in accounts:
            if not isinstance(account, dict):
                continue
            if not account.get("enabled", True):
                continue
            if str(account.get("collection_mode", "public")).strip() != "authenticated":
                continue
            username = str(account.get("username", "")).strip()
            if username:
                return username, "config"

    return "", "none"


def evaluate_session(
    home_state,
    profile_state=None,
    expected_username="",
    cookies=None,
):
    identity_evidence = identity_evidence_from_state(home_state)
    identity_evidence.extend(
        profile_identity_evidence(profile_state, expected_username)
    )
    identity_evidence.extend(cookie_identity_evidence(cookies))
    identity_evidence = list(dict.fromkeys(identity_evidence))

    public_accessible = (
        not home_state["login_wall_detected"]
        and not home_state["challenge_detected"]
    )

    if (
        home_state["login_wall_detected"]
        or home_state["challenge_detected"]
        or (profile_state and (profile_state["login_wall_detected"] or profile_state["challenge_detected"]))
    ):
        session_status = "login_required"
        authenticated = False
        status_reason = "login_wall_or_challenge_detected"
    elif (
        "expected_profile_visible" in identity_evidence
        and "expected_profile_accessible" in identity_evidence
        and any(item.startswith("cookie:") for item in identity_evidence)
    ):
        session_status = "authenticated"
        authenticated = True
        status_reason = "expected_profile_and_auth_cookie_confirmed"
    elif (
        "expected_profile_visible" in identity_evidence
        and "expected_profile_accessible" in identity_evidence
        and any(item.startswith("home_text:") for item in identity_evidence)
    ):
        session_status = "authenticated"
        authenticated = True
        status_reason = "expected_profile_and_identity_ui_confirmed"
    elif public_accessible:
        session_status = "public_access_only"
        authenticated = False
        status_reason = "public_page_accessible_but_missing_auth_indicators"
    else:
        session_status = "public_access_only"
        authenticated = False
        status_reason = "missing_auth_indicators"

    return {
        "session_status": session_status,
        "authenticated": authenticated,
        "public_accessible": public_accessible,
        "login_wall_detected": home_state["login_wall_detected"],
        "challenge_detected": home_state["challenge_detected"],
        "visible_text_length": home_state["visible_text_length"],
        "permalink_count": home_state["permalink_count"],
        "identity_indicators": identity_evidence,
        "reason": status_reason,
    }


def check_session_state(headless=True, debug=False):
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        raise SystemExit(
            "Playwright is not installed.\n"
            "Install instructions:\n"
            "1. pip install playwright\n"
            "2. python -m playwright install chromium"
        )

    expected_username, expected_username_source = load_expected_username()
    home_state = {}
    profile_state = None
    home_artifacts = {}
    profile_artifacts = {}
    cookies = []
    profile_url_checked = None

    with sync_playwright() as playwright:
        context = launch_persistent_context(playwright, headless=headless)
        try:
            home_page = context.pages[0] if context.pages else context.new_page()
            home_page.goto(
                THREADS_HOME_URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            home_page.wait_for_timeout(3000)
            home_state = capture_page_state(home_page)
            if debug:
                home_artifacts = save_debug_artifacts(
                    home_page,
                    "check-home",
                    home_state,
                )
            cookies = context.cookies([THREADS_HOME_URL])

            if expected_username:
                profile_page = context.new_page()
                profile_url_checked = THREADS_PROFILE_URL.format(
                    username=expected_username
                )
                profile_page.goto(
                    profile_url_checked,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                profile_page.wait_for_timeout(3000)
                profile_state = capture_page_state(profile_page)
                if debug:
                    profile_artifacts = save_debug_artifacts(
                        profile_page,
                        "check-profile",
                        profile_state,
                    )
                profile_page.close()
        finally:
            context.close()

    result = evaluate_session(
        home_state,
        profile_state=profile_state,
        expected_username=expected_username,
        cookies=cookies,
    )
    result["expected_username"] = expected_username or None
    result["expected_username_source"] = expected_username_source
    result["profile_dir"] = str(THREADS_BROWSER_PROFILE_DIR)
    result["home_url_checked"] = THREADS_HOME_URL
    result["profile_url_checked"] = profile_url_checked
    result["home_state"] = home_state
    result["profile_state"] = profile_state
    result["home_artifacts"] = home_artifacts
    result["profile_artifacts"] = profile_artifacts
    return result


def print_check_result(result):
    home_state = result["home_state"]
    profile_state = result.get("profile_state")

    print(f"session_status={result['session_status']}")
    print(f"authenticated={str(result['authenticated']).lower()}")
    print(f"profile_dir={result['profile_dir']}")
    print(f"expected_username={result.get('expected_username') or 'none'}")
    print(
        f"expected_username_source={result.get('expected_username_source') or 'none'}"
    )
    print(f"home_url_checked={result['home_url_checked']}")
    print(f"profile_url_checked={result.get('profile_url_checked') or 'none'}")
    print(f"public_accessible={str(result['public_accessible']).lower()}")
    print(f"login_wall_detected={str(result['login_wall_detected']).lower()}")
    print(f"challenge_detected={str(result['challenge_detected']).lower()}")
    print(f"current_url={home_state['current_url']}")
    print(f"title={home_state['title']}")
    print(f"visible_text_length={home_state['visible_text_length']}")
    print(f"permalink_count={home_state['permalink_count']}")
    indicators = result.get("identity_indicators") or []
    print(f"identity_indicators={','.join(indicators) if indicators else 'none'}")
    print(f"reason={result.get('reason') or 'none'}")

    if result.get("home_artifacts"):
        print(f"home_debug_png={result['home_artifacts']['png']}")
        print(f"home_debug_html={result['home_artifacts']['html']}")
        print(f"home_debug_txt={result['home_artifacts']['txt']}")

    if profile_state:
        print(f"profile_url={profile_state['current_url']}")
        print(f"profile_title={profile_state['title']}")
        print(
            f"profile_visible_text_length={profile_state['visible_text_length']}"
        )
        print(f"profile_permalink_count={profile_state['permalink_count']}")
        print(
            f"expected_profile_accessible={str(not profile_state['login_wall_detected']).lower()}"
        )

    if result.get("profile_artifacts"):
        print(f"profile_debug_png={result['profile_artifacts']['png']}")
        print(f"profile_debug_html={result['profile_artifacts']['html']}")
        print(f"profile_debug_txt={result['profile_artifacts']['txt']}")


def save_login_after_enter_artifacts(page):
    state = capture_page_state(page)
    artifacts = save_debug_artifacts(page, "login-after-enter", state)
    return state, artifacts


def login(headless=False, wait_timeout_seconds=600):
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        raise SystemExit(
            "Playwright is not installed.\n"
            "Install instructions:\n"
            "1. pip install playwright\n"
            "2. python -m playwright install chromium"
        )

    deadline = time.time() + max(60, int(wait_timeout_seconds or 600))
    result = None

    with sync_playwright() as playwright:
        context = launch_persistent_context(playwright, headless=headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(
            THREADS_HOME_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        print("Login dan isi OTP di browser ini. Script akan menunggu sampai session authenticated.")
        print(f"wait_timeout_seconds={max(60, int(wait_timeout_seconds or 600))}")
        while time.time() < deadline:
            page.wait_for_timeout(5000)
            result = check_session_state(headless=True, debug=False)
            if result["session_status"] == "authenticated":
                break
            remaining = int(max(0, deadline - time.time()))
            print(
                f"session_status={result['session_status']} "
                f"reason={result.get('reason') or '-'} "
                f"remaining_seconds={remaining}"
            )
        state, artifacts = save_login_after_enter_artifacts(page)
        print(f"current_url={state['current_url']}")
        print(f"title={state['title']}")
        print(f"visible_text_length={state['visible_text_length']}")
        print(f"login_debug_png={artifacts['png']}")
        print(f"login_debug_html={artifacts['html']}")
        print(f"login_debug_txt={artifacts['txt']}")
        context.close()

    print(f"profile_saved={THREADS_BROWSER_PROFILE_DIR}")
    result = result or check_session_state(headless=True, debug=True)
    print_check_result(result)
    if result["session_status"] != "authenticated":
        print("warning=login_not_verified")


def check(debug=False):
    result = check_session_state(headless=True, debug=debug)
    print_check_result(result)


def logout(yes=False):
    if not THREADS_BROWSER_PROFILE_DIR.exists():
        print(f"profile_missing={THREADS_BROWSER_PROFILE_DIR}")
        return

    if not yes:
        answer = input(
            f"Delete Threads browser profile at {THREADS_BROWSER_PROFILE_DIR}? [y/N] "
        ).strip().lower()
        if answer not in {"y", "yes"}:
            print("logout_cancelled=true")
            return

    shutil.rmtree(THREADS_BROWSER_PROFILE_DIR)
    print(f"profile_deleted={THREADS_BROWSER_PROFILE_DIR}")


def session_status_error_code(session_status):
    if session_status == "authenticated":
        return None
    if session_status == "login_required":
        return "LOGIN_REQUIRED"
    if session_status == "public_access_only":
        return "PUBLIC_ACCESS_ONLY"
    return "PUBLIC_ACCESS_ONLY"


def main():
    args = parse_args()

    if args.command == "login":
        login(headless=args.headless, wait_timeout_seconds=args.wait_timeout_seconds)
        return

    if args.command == "check":
        check(debug=args.debug)
        return

    logout(yes=args.yes)


if __name__ == "__main__":
    main()
