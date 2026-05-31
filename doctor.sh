#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILURES=0

echo "== PAOS Runtime Doctor =="
echo "Runtime: $ROOT"
echo

report_ok() {
  echo "OK   $1"
}

report_warn() {
  echo "WARN $1"
}

report_fail() {
  echo "FAIL $1"
  FAILURES=$((FAILURES + 1))
}

check_file() {
  local path="$1"
  local label="$2"
  if [ -f "$path" ]; then
    report_ok "$label"
  else
    report_fail "$label missing: $path"
  fi
}

check_dir() {
  local path="$1"
  local label="$2"
  if [ -d "$path" ]; then
    report_ok "$label"
  else
    report_fail "$label missing: $path"
  fi
}

check_env_value() {
  local name="$1"
  local value="$2"
  local required="${3:-false}"
  local label="$4"

  if [ -n "$value" ]; then
    report_ok "$label"
    return
  fi

  if [ "$required" = "true" ]; then
    report_fail "$label missing"
  else
    report_warn "$label missing"
  fi
}

PYTHON_BIN=""
if [ -x "$ROOT/venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  report_fail "Python interpreter not found"
fi

echo "== Runtime =="
if [ -x "$ROOT/venv/bin/python" ]; then
  report_ok "virtual environment"
else
  report_fail "virtual environment missing: $ROOT/venv/bin/python"
fi

echo
echo "== Files =="
check_file "$ROOT/requirements.txt" "requirements.txt"
check_file "$ROOT/runtime/intelligence/config.yaml" "runtime/intelligence/config.yaml"
check_file "$ROOT/runtime/intelligence/sources/rss.yaml" "runtime/intelligence/sources/rss.yaml"
check_file "$ROOT/runtime/intelligence/sources/threads.yaml" "runtime/intelligence/sources/threads.yaml"
check_file "$ROOT/runtime/intelligence/sources/keyword.yaml" "runtime/intelligence/sources/keyword.yaml"

echo
echo "== Directories =="
check_dir "$ROOT/intelligence/raw" "intelligence/raw"
check_dir "$ROOT/intelligence/candidates" "intelligence/candidates"
check_dir "$ROOT/intelligence/signals" "intelligence/signals"
check_dir "$ROOT/intelligence/digests" "intelligence/digests"
check_dir "$ROOT/intelligence/insights" "intelligence/insights"
check_dir "$ROOT/.runtime/runs" ".runtime/runs"

echo
echo "== Imports =="
if [ -n "${PYTHON_BIN:-}" ]; then
  if "$PYTHON_BIN" -c "import feedparser, requests, openai, yaml, telegram; import runtime.intelligence.config; import context.loader; import runtime.intelligence.jobs.run_daily_intelligence; import runtime.intelligence.jobs.run_rss_collector; import runtime.intelligence.jobs.run_candidate_pool; import runtime.intelligence.jobs.run_digest" >/dev/null 2>&1; then
    report_ok "core Python modules import"
  else
    report_fail "core Python modules import"
  fi
else
  report_fail "core Python modules import skipped"
fi

echo
echo "== Env =="
if [ -f "$ROOT/.env" ]; then
  report_ok ".env present"

  PAOS_RUNTIME_PATH=""
  PAOS_CONTEXT_PATH=""
  TELEGRAM_BOT_TOKEN=""
  LLM_BASE_URL=""
  LLM_API_KEY=""
  LLM_MODEL=""

  PAOS_RUNTIME_PATH="$(grep -E '^PAOS_RUNTIME_PATH=' "$ROOT/.env" | head -n1 | cut -d= -f2- || true)"
  PAOS_CONTEXT_PATH="$(grep -E '^PAOS_CONTEXT_PATH=' "$ROOT/.env" | head -n1 | cut -d= -f2- || true)"
  TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ROOT/.env" | head -n1 | cut -d= -f2- || true)"
  LLM_BASE_URL="$(grep -E '^LLM_BASE_URL=' "$ROOT/.env" | head -n1 | cut -d= -f2- || true)"
  LLM_API_KEY="$(grep -E '^LLM_API_KEY=' "$ROOT/.env" | head -n1 | cut -d= -f2- || true)"
  LLM_MODEL="$(grep -E '^LLM_MODEL=' "$ROOT/.env" | head -n1 | cut -d= -f2- || true)"

  check_env_value "PAOS_RUNTIME_PATH" "${PAOS_RUNTIME_PATH:-}" true "PAOS_RUNTIME_PATH"
  check_env_value "PAOS_CONTEXT_PATH" "${PAOS_CONTEXT_PATH:-}" true "PAOS_CONTEXT_PATH"
  check_env_value "TELEGRAM_BOT_TOKEN" "${TELEGRAM_BOT_TOKEN:-}" false "TELEGRAM_BOT_TOKEN"

  if [ -n "${LLM_BASE_URL:-}" ] && [ -n "${LLM_API_KEY:-}" ] && [ -n "${LLM_MODEL:-}" ]; then
    report_ok "AI endpoint config"
  else
    report_warn "AI endpoint config missing or incomplete"
  fi
else
  report_warn ".env missing"
  report_warn "TELEGRAM_BOT_TOKEN missing"
  report_warn "AI endpoint config missing or incomplete"
fi

echo
echo "== Done =="

if [ "$FAILURES" -gt 0 ]; then
  exit 1
fi
