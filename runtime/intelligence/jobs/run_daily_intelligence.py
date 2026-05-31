import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
ROOT = INTELLIGENCE_DIR.parents[1]
RUNS_PATH = ROOT / ".runtime" / "runs" / "daily-intelligence" / "latest.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run PAOS daily intelligence pipeline."
    )
    parser.add_argument("--category", default="ai")
    parser.add_argument("--date", default="today")
    parser.add_argument(
        "--with-threads",
        action="store_true",
        help="Include Threads account collector with timeout guard.",
    )
    parser.add_argument("--threads-timeout-seconds", type=int, default=120)
    return parser.parse_args()


def now_iso():
    return datetime.now().astimezone().isoformat()


def write_status(payload):
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def run_step(step, command, timeout_seconds=None):
    started_at = now_iso()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "step": step,
            "status": "failed",
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": None,
            "timeout_seconds": timeout_seconds,
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or "").strip(),
            "error": f"Timed out after {timeout_seconds}s",
        }

    return {
        "step": step,
        "status": "success" if completed.returncode == 0 else "failed",
        "started_at": started_at,
        "finished_at": now_iso(),
        "returncode": completed.returncode,
        "timeout_seconds": timeout_seconds,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
        "error": None if completed.returncode == 0 else "Command failed",
    }


def extract_insight_markdown_path(step):
    stdout = (step or {}).get("stdout", "")
    if not stdout:
        return None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("markdown_path:"):
            candidate = line.split(":", 1)[1].strip()
            if candidate:
                return candidate

    for raw_line in reversed(stdout.splitlines()):
        line = raw_line.strip()
        if line.endswith(".md") and "/intelligence/insights/" in line:
            return line
    return None


def extract_digest_markdown_path(step):
    stdout = (step or {}).get("stdout", "")
    if not stdout:
        return None
    for raw_line in reversed(stdout.splitlines()):
        line = raw_line.strip()
        if line.endswith(".md") and "/intelligence/digests/" in line:
            return line
    return None


def main():
    args = parse_args()
    started_at = now_iso()
    steps = []

    base_steps = [
        (
            "rss",
            [
                sys.executable,
                str(INTELLIGENCE_DIR / "jobs" / "run_rss_collector.py"),
                "--category",
                args.category,
            ],
            None,
        ),
        (
            "threads_keyword",
            [
                sys.executable,
                str(INTELLIGENCE_DIR / "jobs" / "run_threads_keyword.py"),
                "--category",
                args.category,
                "--timeout-seconds",
                "120",
                "--limit",
                "4",
            ],
            None,
        ),
        (
            "candidate",
            [
                sys.executable,
                str(INTELLIGENCE_DIR / "jobs" / "run_candidate_pool.py"),
                "--category",
                args.category,
                "--date",
                args.date,
            ],
            None,
        ),
        (
            "signal",
            [
                sys.executable,
                str(INTELLIGENCE_DIR / "jobs" / "run_signal_builder.py"),
                "--category",
                args.category,
                "--date",
                args.date,
                "--mode",
                "ai",
            ],
            None,
        ),
        (
            "digest",
            [
                sys.executable,
                str(INTELLIGENCE_DIR / "jobs" / "run_digest.py"),
                "--category",
                args.category,
                "--date",
                args.date,
            ],
            None,
        ),
        (
            "insight",
            [
                sys.executable,
                str(INTELLIGENCE_DIR / "jobs" / "run_insights.py"),
                "--category",
                args.category,
                "--date",
                args.date,
                "--mode",
                "ai",
            ],
            None,
        ),
    ]

    if args.with_threads:
        steps.append(
            run_step(
                step="threads",
                command=[
                    sys.executable,
                    str(INTELLIGENCE_DIR / "jobs" / "run_threads_account.py"),
                    "--category",
                    args.category,
                    "--timeout-seconds",
                    str(max(1, args.threads_timeout_seconds)),
                ],
                timeout_seconds=max(1, args.threads_timeout_seconds),
            )
        )
        if steps[-1]["status"] != "success":
            payload = {
                "job": "daily-intelligence",
                "status": "failed",
                "category": args.category,
                "date": args.date,
                "with_threads": True,
                "started_at": started_at,
                "finished_at": now_iso(),
                "steps": steps,
            }
            write_status(payload)
            print(json.dumps(payload, ensure_ascii=True, indent=2))
            raise SystemExit(1)

    for step_name, command, timeout_seconds in base_steps:
        step = run_step(step=step_name, command=command, timeout_seconds=timeout_seconds)
        steps.append(step)
        if step["status"] != "success":
            payload = {
                "job": "daily-intelligence",
                "status": "failed",
                "category": args.category,
                "date": args.date,
                "with_threads": args.with_threads,
                "started_at": started_at,
                "finished_at": now_iso(),
                "steps": steps,
            }
            write_status(payload)
            print(json.dumps(payload, ensure_ascii=True, indent=2))
            raise SystemExit(1)

    digest_step = next((step for step in steps if step.get("step") == "digest"), {})
    insight_step = next((step for step in steps if step.get("step") == "insight"), {})
    digest_path = extract_digest_markdown_path(digest_step)
    insight_path = extract_insight_markdown_path(insight_step)
    if not digest_path:
        digest_path = str(ROOT / "intelligence" / "digests" / args.date / f"{args.category}.md")
    if not insight_path:
        insight_path = str(ROOT / "intelligence" / "insights" / args.date / f"{args.category}.md")
    payload = {
        "job": "daily-intelligence",
        "status": "success",
        "category": args.category,
        "date": args.date,
        "with_threads": args.with_threads,
        "started_at": started_at,
        "finished_at": now_iso(),
        "digest_path": str(digest_path),
        "insight_path": str(insight_path),
        "steps": steps,
    }
    write_status(payload)
    print(json.dumps(payload, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
