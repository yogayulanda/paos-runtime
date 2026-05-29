#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== Installing PAOS Runtime =="
cd "$ROOT"

python3 -m venv venv
"$ROOT/venv/bin/pip" install --upgrade pip
"$ROOT/venv/bin/pip" install -r requirements.txt

mkdir -p data logs state tmp

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example"
  echo "Please edit .env before running PAOS."
else
  echo ".env already exists"
fi

chmod +x doctor.sh
chmod +x scripts/*.sh 2>/dev/null || true

echo
"$ROOT/doctor.sh"