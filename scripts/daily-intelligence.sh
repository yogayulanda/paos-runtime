#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/.runtime/logs"
LOG_FILE="$LOG_DIR/daily-intelligence.log"
mkdir -p "$LOG_DIR"

if [[ ! -x "$REPO_ROOT/venv/bin/python" ]]; then
  echo "Missing Python runtime: $REPO_ROOT/venv/bin/python" >&2
  echo "Run install first: bash install.sh" >&2
  exit 1
fi

"$REPO_ROOT/venv/bin/python" \
  "$REPO_ROOT/runtime/intelligence/jobs/run_daily_intelligence.py" \
  --category ai >>"$LOG_FILE" 2>&1
