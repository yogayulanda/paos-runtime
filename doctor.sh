#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== PAOS Runtime Doctor =="
echo "Runtime: $ROOT"
echo

check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "✓ $1"
  else
    echo "✗ $1 missing"
  fi
}

check_path() {
  if [ -e "$1" ]; then
    echo "✓ $1"
  else
    echo "✗ $1 missing"
  fi
}

check_cmd python3
check_cmd git
check_cmd curl
check_cmd docker

echo
echo "== Files =="
check_path "$ROOT/.env.example"
check_path "$ROOT/requirements.txt"
check_path "$ROOT/bot/telegram-bot.py"
check_path "$ROOT/workers/ai-digest.py"
check_path "$ROOT/workers/rss-worker.py"

echo
echo "== Local Runtime =="
check_path "$ROOT/.env"
check_path "$ROOT/venv/bin/python"

echo
echo "== Env =="
if [ -f "$ROOT/.env" ]; then
  grep -q "^PAOS_CONTEXT_PATH=" "$ROOT/.env" && echo "✓ PAOS_CONTEXT_PATH" || echo "✗ PAOS_CONTEXT_PATH missing"
  grep -q "^TELEGRAM_BOT_TOKEN=" "$ROOT/.env" && echo "✓ TELEGRAM_BOT_TOKEN" || echo "✗ TELEGRAM_BOT_TOKEN missing"
  grep -q "^LLM_BASE_URL=" "$ROOT/.env" && echo "✓ LLM_BASE_URL" || echo "✗ LLM_BASE_URL missing"
else
  echo "✗ .env missing"
fi

echo
echo "== Done =="