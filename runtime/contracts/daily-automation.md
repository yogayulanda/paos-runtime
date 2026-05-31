Purpose: define Task 5B daily automation/scheduler MVP for PAOS runtime.

Scope:
- One-shot deterministic runner for existing daily PAOS pipeline.
- Runner executes existing job scripts only; no pipeline logic rewrite.
- Telegram surfaces remain read-only and consume latest artifacts only.
- Scheduler runs outside Telegram bot process.

Runner:
- Path: `runtime/jobs/run_daily_paos.py`
- Required order:
  1. collectors (`run_rss_collector.py`, `run_threads_keyword.py`)
  2. candidate pool (`run_candidate_pool.py`)
  3. signal builder (`run_signal_builder.py`)
  4. digest (`run_digest.py`)
  5. insight (`run_insights.py`)
  6. assistant context (`run_assistant_context.py`)
  7. assistant brief (`run_assistant_brief.py`)
  8. opportunities (`run_assistant_opportunities.py`)
  9. assistant diagnostics (`run_assistant_diagnostics.py`)

CLI:
- `--category ai` default `ai`
- `--date YYYY-MM-DD` optional; passed only to date-aware jobs
- `--continue-on-collector-warning true|false` default `true`
- `--dry-run` optional
- `--notify-telegram` optional reserved flag; no sender wired in MVP

Status artifacts:
- `.runtime/runs/daily-paos/latest.json`
- `.runtime/runs/daily-paos/YYYY-MM-DD.json`

Status payload keys:
- `status`: `success | success_with_warnings | failed`
- `category`
- `started_at`
- `finished_at`
- `duration_seconds`
- `steps[]`: `name`, `command`, `status`, `returncode`, `duration_seconds`, `stdout_tail`, `stderr_tail`, `status_path`
- `artifacts`: `digest`, `insight`, `assistant_context`, `assistant_brief`, `opportunities`
- `warnings[]`
- `errors[]`

Failure behavior:
- Critical step failure stops run and marks `failed`.
- Collector non-zero exit can continue as warning when `--continue-on-collector-warning=true`.
- Diagnostics non-zero exit is warning by default (`success_with_warnings`) unless another critical error fails the run.
- Missing expected artifacts after run are treated as errors.
- Runner never deletes artifacts.
