#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== Installing PAOS Runtime =="
cd "$ROOT"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "FAIL: python3 or python is required."
  exit 1
fi

if [ ! -d "$ROOT/venv" ]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$ROOT/venv"
else
  echo "Using existing virtual environment."
fi

VENV_PYTHON="$ROOT/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "FAIL: $VENV_PYTHON is missing or not executable."
  exit 1
fi

echo "Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip

if [ -f "$ROOT/requirements.txt" ]; then
  echo "Installing Python dependencies..."
  "$VENV_PYTHON" -m pip install -r "$ROOT/requirements.txt"
else
  echo "WARN: requirements.txt not found; skipping dependency install."
fi

mkdir -p \
  "$ROOT/intelligence" \
  "$ROOT/intelligence/raw" \
  "$ROOT/intelligence/candidates" \
  "$ROOT/intelligence/signals" \
  "$ROOT/intelligence/digests" \
  "$ROOT/intelligence/insights" \
  "$ROOT/.runtime" \
  "$ROOT/.runtime/runs"

if [ ! -f "$ROOT/.env" ]; then
  if [ -f "$ROOT/.env.example" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "Created .env from .env.example"
  else
    echo "WARN: .env.example not found; .env was not created."
  fi
else
  echo ".env already exists; leaving it unchanged."
fi

chmod +x "$ROOT/install.sh" "$ROOT/doctor.sh" 2>/dev/null || true

echo
echo "Install complete."
echo "Next steps:"
echo "  1. Edit .env if needed."
echo "  2. Run: bash doctor.sh"
echo "  3. Run a pipeline: venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai"
