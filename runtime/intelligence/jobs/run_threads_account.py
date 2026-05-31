import argparse
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from collectors.threads.extractor import THREADS_BROWSER_PROFILE_DIR
from collectors.threads.extractor import resolve_adapter_with_auth
from collectors.threads.public_account import collect_account_feed
from config import resolve_category
from notify.telegram import send_telegram_message
from threads_auth import check_session_state
from threads_auth import session_status_error_code


ROOT = INTELLIGENCE_DIR.parents[1]
RUNTIME_DIR = ROOT / ".runtime"
LOCK_PATH = RUNTIME_DIR / "locks" / "threads-account.lock"
RUNS_PATH = RUNTIME_DIR / "runs" / "threads-account" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run authenticated Threads account collection safely."
    )
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--extraction-mode",
        choices=["fast", "deep"],
        default="fast",
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["playwright", "official", "scraper"],
        default="playwright",
    )
    return parser.parse_args()


def now_iso():
    return datetime.now().astimezone().isoformat()


def ensure_runtime_dirs():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    THREADS_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def pid_active(pid):
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_lock():
    if not LOCK_PATH.exists():
        return {}

    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(status):
    RUNS_PATH.write_text(
        json.dumps(status, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def build_status(
    started_at,
    status,
    error_code=None,
    error_message=None,
    items_collected=0,
    paths=None,
    extraction_mode=None,
    category=None,
    category_source=None,
    diagnostics=None,
):
    finished_at = now_iso()
    duration = max(
        0.0,
        datetime.fromisoformat(finished_at).timestamp()
        - datetime.fromisoformat(started_at).timestamp(),
    )
    return {
        "job": "threads-account",
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "category": category,
        "category_source": category_source,
        "error_code": error_code,
        "error_message": error_message,
        "items_collected": items_collected,
        "paths": paths or [],
        "extraction_mode": extraction_mode,
        "diagnostics": diagnostics or {},
        "duration_seconds": round(duration, 2),
    }


def acquire_lock(started_at):
    ensure_runtime_dirs()
    lock_data = read_lock()
    existing_pid = int(lock_data.get("pid") or 0)

    if LOCK_PATH.exists() and pid_active(existing_pid):
        return False, lock_data

    if LOCK_PATH.exists():
        LOCK_PATH.unlink()

    payload = {
        "pid": os.getpid(),
        "started_at": started_at,
    }
    LOCK_PATH.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return True, payload


def release_lock():
    lock_data = read_lock()
    if int(lock_data.get("pid") or 0) == os.getpid() and LOCK_PATH.exists():
        LOCK_PATH.unlink()


class JobTimeoutError(RuntimeError):
    pass


def alarm_handler(signum, frame):
    raise JobTimeoutError("Threads account job exceeded timeout.")


def format_failure_message(status):
    if status["error_code"] in {
        "AUTH_NOT_VERIFIED",
        "LOGIN_REQUIRED",
        "PUBLIC_ACCESS_ONLY",
        "UNKNOWN_AUTH_STATE",
    }:
        return (
            "PAOS Intelligence job failed\n\n"
            "Job: threads-account\n"
            "Error: AUTH_NOT_VERIFIED\n"
            "Message: Threads login is not verified. Run manual login first.\n"
            f"Time: {status['finished_at']}\n"
            "Action: venv/bin/python runtime/intelligence/threads_auth.py login"
        )

    return (
        "PAOS Intelligence job failed\n\n"
        "Job: threads-account\n"
        f"Error: {status['error_code']}\n"
        f"Message: {status['error_message']}\n"
        f"Time: {status['finished_at']}\n"
        "Action: run venv/bin/python runtime/intelligence/threads_auth.py login"
    )


def main():
    args = parse_args()
    started_at = now_iso()
    resolved_category = resolve_category(args.category)
    locked, lock_data = acquire_lock(started_at)

    if not locked:
        status = build_status(
            started_at=started_at,
            status="skipped",
            error_code="LOCKED",
            error_message=(
                "Threads account job is already running."
                f" pid={lock_data.get('pid')}"
            ),
            extraction_mode=args.extraction_mode,
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        write_status(status)
        print(status["error_message"])
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(max(1, args.timeout_seconds))

    try:
        session = check_session_state(headless=True)
        if session["session_status"] != "authenticated":
            status = build_status(
                started_at=started_at,
                status="failed",
                error_code=session_status_error_code(session["session_status"]),
                error_message=(
                    "Threads login is not verified. Run manual login first."
                    f" session_status={session['session_status']}"
                ),
                extraction_mode=args.extraction_mode,
                category=resolved_category.value,
                category_source=resolved_category.source,
            )
            write_status(status)
            send_telegram_message(format_failure_message(status))
            print(json.dumps(status, ensure_ascii=True, indent=2))
            return

        adapter = resolve_adapter_with_auth(
            provider=args.provider,
            debug=args.debug,
            authenticated=True,
            timeout_seconds=args.timeout_seconds,
            extraction_mode=args.extraction_mode,
        )
        result = collect_account_feed(
            adapter=adapter,
            limit=args.limit,
            category=resolved_category.value,
            debug=args.debug,
            authenticated=True,
        )

        errors = result.get("errors") or []
        paths = [str(path) for path in result.get("paths") or []]
        items_collected = len(result.get("items") or [])
        diagnostics = result.get("diagnostics") or {}
        accounts_total = int(diagnostics.get("accounts_total") or 0)
        accounts_succeeded = int(diagnostics.get("accounts_succeeded") or 0)
        accounts_empty = int(diagnostics.get("accounts_empty") or 0)
        accounts_failed = int(diagnostics.get("accounts_failed") or 0)
        accounts_processable = max(0, accounts_total - int((result.get("stats") or {}).get("skipped_accounts") or 0))

        if accounts_processable <= 0:
            status = build_status(
                started_at=started_at,
                status="failed",
                error_code="NO_ACCOUNTS_PROCESSABLE",
                error_message="No enabled Threads accounts could be processed.",
                items_collected=items_collected,
                paths=paths,
                extraction_mode=args.extraction_mode,
                category=resolved_category.value,
                category_source=resolved_category.source,
                diagnostics=diagnostics,
            )
            write_status(status)
            send_telegram_message(format_failure_message(status))
            print(json.dumps(status, ensure_ascii=True, indent=2))
            return

        if accounts_succeeded <= 0 and accounts_failed > 0 and items_collected <= 0:
            first = errors[0] if errors else {}
            status = build_status(
                started_at=started_at,
                status="failed",
                error_code=first.get("code", "ALL_ACCOUNTS_FAILED"),
                error_message=first.get(
                    "message",
                    "All enabled Threads accounts failed to produce usable items due to errors.",
                ),
                items_collected=items_collected,
                paths=paths,
                extraction_mode=args.extraction_mode,
                category=resolved_category.value,
                category_source=resolved_category.source,
                diagnostics=diagnostics,
            )
            write_status(status)
            send_telegram_message(format_failure_message(status))
            print(json.dumps(status, ensure_ascii=True, indent=2))
            return

        final_status = "success"
        if accounts_failed > 0 or accounts_empty > 0:
            final_status = "success_with_warnings"
        status = build_status(
            started_at=started_at,
            status=final_status,
            items_collected=items_collected,
            paths=paths,
            extraction_mode=args.extraction_mode,
            category=resolved_category.value,
            category_source=resolved_category.source,
            diagnostics=diagnostics,
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=True, indent=2))
    except JobTimeoutError as exc:
        status = build_status(
            started_at=started_at,
            status="failed",
            error_code="BROWSER_TIMEOUT",
            error_message=str(exc),
            extraction_mode=args.extraction_mode,
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        write_status(status)
        send_telegram_message(format_failure_message(status))
        print(json.dumps(status, ensure_ascii=True, indent=2))
    except Exception as exc:
        status = build_status(
            started_at=started_at,
            status="failed",
            error_code="UNKNOWN_ERROR",
            error_message=str(exc),
            extraction_mode=args.extraction_mode,
            category=resolved_category.value,
            category_source=resolved_category.source,
        )
        write_status(status)
        send_telegram_message(format_failure_message(status))
        print(json.dumps(status, ensure_ascii=True, indent=2))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        release_lock()


if __name__ == "__main__":
    main()
