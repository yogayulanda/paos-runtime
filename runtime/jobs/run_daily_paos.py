import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / ".runtime" / "runs" / "daily-paos"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PAOS daily automation pipeline.")
    parser.add_argument("--category", default="ai")
    parser.add_argument("--date", default=None, help="Optional YYYY-MM-DD passed to date-aware jobs.")
    parser.add_argument(
        "--continue-on-collector-warning",
        default="true",
        choices=("true", "false"),
        help="If true, collector non-zero exit marks warning and pipeline continues.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--notify-telegram",
        action="store_true",
        help="Reserved flag. No notifier is invoked in this MVP.",
    )
    return parser.parse_args()


def _tail(text: str, max_chars: int = 1200) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _write_status(payload: dict) -> None:
    date_key = datetime.now().astimezone().date().isoformat()
    dated_path = RUNS_DIR / f"{date_key}.json"
    latest_path = RUNS_DIR / "latest.json"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=True, indent=2)
    dated_path.write_text(serialized, encoding="utf-8")
    latest_path.write_text(serialized, encoding="utf-8")


def _resolve_latest_file(root_dir: Path, filename: str) -> Path | None:
    if not root_dir.exists():
        return None
    candidates = sorted(
        [path for path in root_dir.glob(f"*/{filename}") if path.is_file()],
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _status_path_for_step(name: str) -> str | None:
    mapping = {
        "collectors_rss": ROOT / ".runtime" / "runs" / "rss-collector" / "latest.json",
        "collectors_threads_keyword": ROOT / ".runtime" / "runs" / "threads-keyword" / "latest.json",
        "candidate_pool": ROOT / ".runtime" / "runs" / "candidate-pool" / "latest.json",
        "signal_builder": ROOT / ".runtime" / "runs" / "signal-builder" / "latest.json",
        "digest": ROOT / ".runtime" / "runs" / "digest" / "latest.json",
        "insight": ROOT / ".runtime" / "runs" / "insights" / "latest.json",
        "assistant_context": ROOT / ".runtime" / "runs" / "assistant-context" / "latest.json",
        "assistant_brief": ROOT / ".runtime" / "runs" / "assistant-brief" / "latest.json",
        "opportunities": ROOT / ".runtime" / "runs" / "assistant-opportunities" / "latest.json",
        "assistant_diagnostics": ROOT / ".runtime" / "runs" / "assistant" / "latest.json",
    }
    path = mapping.get(name)
    return str(path) if path else None


def _run_step(name: str, command: list[str], dry_run: bool) -> dict:
    started = datetime.now().timestamp()
    started_at = now_iso()
    if dry_run:
        return {
            "name": name,
            "command": " ".join(command),
            "status": "skipped",
            "returncode": None,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
            "status_path": _status_path_for_step(name),
            "started_at": started_at,
            "finished_at": now_iso(),
        }

    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    finished = datetime.now().timestamp()
    return {
        "name": name,
        "command": " ".join(command),
        "status": "success" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "duration_seconds": round(max(0.0, finished - started), 3),
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
        "status_path": _status_path_for_step(name),
        "started_at": started_at,
        "finished_at": now_iso(),
    }


def _artifact_snapshot() -> dict:
    digest = _resolve_latest_file(ROOT / "intelligence" / "digests", "ai.md")
    insight = _resolve_latest_file(ROOT / "intelligence" / "insights", "ai.md")
    assistant_context = _resolve_latest_file(ROOT / "assistant" / "context", "assistant-context.json")
    assistant_brief = _resolve_latest_file(ROOT / "assistant" / "briefs", "assistant-brief.json")
    opportunities = _resolve_latest_file(ROOT / "assistant" / "opportunities", "opportunities.json")
    return {
        "digest": str(digest) if digest else None,
        "insight": str(insight) if insight else None,
        "assistant_context": str(assistant_context) if assistant_context else None,
        "assistant_brief": str(assistant_brief) if assistant_brief else None,
        "opportunities": str(opportunities) if opportunities else None,
    }


def _build_steps(category: str, run_date: str | None) -> list[tuple[str, list[str], bool]]:
    python_exe = sys.executable
    common_category = ["--category", category]

    rss_cmd = [python_exe, str(ROOT / "runtime" / "intelligence" / "jobs" / "run_rss_collector.py"), *common_category]
    threads_kw_cmd = [
        python_exe,
        str(ROOT / "runtime" / "intelligence" / "jobs" / "run_threads_keyword.py"),
        *common_category,
        "--timeout-seconds",
        "120",
        "--limit",
        "4",
    ]
    candidate_cmd = [python_exe, str(ROOT / "runtime" / "intelligence" / "jobs" / "run_candidate_pool.py"), *common_category]
    signal_cmd = [
        python_exe,
        str(ROOT / "runtime" / "intelligence" / "jobs" / "run_signal_builder.py"),
        *common_category,
        "--mode",
        "ai",
    ]
    digest_cmd = [python_exe, str(ROOT / "runtime" / "intelligence" / "jobs" / "run_digest.py"), *common_category]
    insight_cmd = [
        python_exe,
        str(ROOT / "runtime" / "intelligence" / "jobs" / "run_insights.py"),
        *common_category,
        "--mode",
        "ai",
    ]
    if run_date:
        candidate_cmd.extend(["--date", run_date])
        signal_cmd.extend(["--date", run_date])
        digest_cmd.extend(["--date", run_date])
        insight_cmd.extend(["--date", run_date])

    assistant_context_cmd = [python_exe, str(ROOT / "runtime" / "assistant" / "jobs" / "run_assistant_context.py"), *common_category]
    assistant_brief_cmd = [python_exe, str(ROOT / "runtime" / "assistant" / "jobs" / "run_assistant_brief.py"), *common_category]
    opportunities_cmd = [python_exe, str(ROOT / "runtime" / "assistant" / "jobs" / "run_assistant_opportunities.py"), *common_category]
    diagnostics_cmd = [python_exe, str(ROOT / "runtime" / "assistant" / "jobs" / "run_assistant_diagnostics.py"), *common_category]

    # bool flag marks collector-stage steps
    return [
        ("collectors_rss", rss_cmd, True),
        ("collectors_threads_keyword", threads_kw_cmd, True),
        ("candidate_pool", candidate_cmd, False),
        ("signal_builder", signal_cmd, False),
        ("digest", digest_cmd, False),
        ("insight", insight_cmd, False),
        ("assistant_context", assistant_context_cmd, False),
        ("assistant_brief", assistant_brief_cmd, False),
        ("opportunities", opportunities_cmd, False),
        ("assistant_diagnostics", diagnostics_cmd, False),
    ]


def main() -> None:
    args = parse_args()
    started_at = now_iso()
    started_ts = datetime.now().timestamp()
    warnings: list[str] = []
    errors: list[str] = []
    steps: list[dict] = []
    continue_on_collector_warning = args.continue_on_collector_warning == "true"
    dry_run = bool(args.dry_run)

    if args.notify_telegram:
        warnings.append("notify_telegram flag requested but no safe sender is wired in this MVP")

    for name, command, is_collector in _build_steps(args.category, args.date):
        step = _run_step(name=name, command=command, dry_run=dry_run)
        steps.append(step)
        if step["status"] == "failed":
            if is_collector and continue_on_collector_warning:
                step["status"] = "warning"
                warnings.append(f"collector warning: {name} failed with returncode {step['returncode']}")
                continue
            if name == "assistant_diagnostics":
                step["status"] = "warning"
                warnings.append("assistant diagnostics returned non-zero; marked warning")
                continue
            errors.append(f"critical step failed: {name} (returncode={step['returncode']})")
            break

    artifacts = _artifact_snapshot() if not dry_run else {
        "digest": None,
        "insight": None,
        "assistant_context": None,
        "assistant_brief": None,
        "opportunities": None,
    }

    if not dry_run:
        for key in ("digest", "insight", "assistant_context", "assistant_brief", "opportunities"):
            if not artifacts.get(key):
                errors.append(f"expected artifact missing after run: {key}")

    finished_at = now_iso()
    duration_seconds = round(max(0.0, datetime.now().timestamp() - started_ts), 3)
    status = "success"
    if errors:
        status = "failed"
    elif warnings:
        status = "success_with_warnings"

    payload = {
        "job": "daily-paos",
        "status": status,
        "category": args.category,
        "run_date": args.date,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "steps": steps,
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": errors,
        "continue_on_collector_warning": continue_on_collector_warning,
        "dry_run": dry_run,
    }
    _write_status(payload)
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    if status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
