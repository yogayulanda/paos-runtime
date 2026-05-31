#!/bin/sh
set -eu

ENV_FILE="/opt/data/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${HERMES_LLM_BASE_URL:?missing HERMES_LLM_BASE_URL in /opt/data/.env}"
: "${HERMES_LLM_API_KEY:?missing HERMES_LLM_API_KEY in /opt/data/.env}"
: "${HERMES_LLM_MODEL:?missing HERMES_LLM_MODEL in /opt/data/.env}"

# Hermes current build compatibility aliases (runtime-only)
export OPENAI_BASE_URL="$HERMES_LLM_BASE_URL"
export OPENAI_API_KEY="$HERMES_LLM_API_KEY"

# Optional runtime-only aliases for code paths that still check LLM_*.
export LLM_BASE_URL="$HERMES_LLM_BASE_URL"
export LLM_API_KEY="$HERMES_LLM_API_KEY"
export LLM_MODEL="$HERMES_LLM_MODEL"

exec /opt/hermes/.venv/bin/hermes "$@"
