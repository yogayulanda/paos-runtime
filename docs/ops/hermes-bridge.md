# Hermes Bridge Runtime Validation

Purpose: validate Hermes can consume PAOS Runtime as a client without coupling PAOS to Hermes.

## Scope

- Hermes consumes PAOS MCP over stdio.
- PAOS has no dependency on Hermes.
- No public HTTP/SSE/API listener is introduced.

## Runtime prechecks (VPS)

1. `cd /home/ubuntu/paos/paos-runtime`
2. `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"`
3. `docker logs --tail 80 paos-hermes || true`
4. `docker logs --tail 80 paos-mnemosyne || true`

## MCP capability checks

Use a local smoke invocation from VPS:

```bash
PYTHONPATH=runtime venv/bin/python - <<'PY'
from assistant.mcp.server import tool_paos_health, tool_paos_context_get, tool_paos_brief_get, tool_paos_opportunities_get, tool_paos_memory_recall
checks = [
    ("paos_health", tool_paos_health(category="ai", include_diagnostics=True)),
    ("paos_context_get", tool_paos_context_get(category="ai", format="json", section="all", max_chars=2400)),
    ("paos_brief_get", tool_paos_brief_get(category="ai", format="json")),
    ("paos_opportunities_get", tool_paos_opportunities_get(category="ai", format="json")),
    ("paos_memory_recall", tool_paos_memory_recall(query="PAOS", category="ai", limit=5)),
]
for name, out in checks:
    print(name, out.get("ok"), out.get("errors"))
PY
```

Expected result: all tools return `ok=true` and empty `errors`.

## Assistant diagnostics

- `venv/bin/python runtime/assistant/jobs/run_assistant_diagnostics.py --category ai`
- Expected status: `success`.

## Hermes consumption contract

Hermes should consume:

- `paos_health`
- `paos_context_get`
- `paos_brief_get`
- `paos_opportunities_get`
- `paos_memory_recall`

No dedicated `paos_dashboard` or `paos_daily` MCP tools currently exist.
Dashboard/daily-equivalent summaries are composed from brief/context/opportunities.

## Guardrails

- Do not bypass PAOS `MemoryProvider`.
- Do not mutate Mnemosyne directly.
- Do not add public listeners.
- Do not add scheduler changes for Hermes.
- Do not trigger controlled write apply from Hermes bridge validation.

## Swappable LLM provider config

Canonical Hermes provider variables (source of truth in `data/hermes/.env`):

- `HERMES_LLM_BASE_URL`
- `HERMES_LLM_API_KEY`
- `HERMES_LLM_MODEL`

PAOS/local summarize aliases (kept for runtime compatibility):

- `LLM_BASE_URL=$HERMES_LLM_BASE_URL`
- `LLM_API_KEY=$HERMES_LLM_API_KEY`
- `LLM_MODEL=$HERMES_LLM_MODEL`

Hermes current-build compatibility layer (runtime-only):

- `OPENAI_BASE_URL=$HERMES_LLM_BASE_URL`
- `OPENAI_API_KEY=$HERMES_LLM_API_KEY`
- `model.provider=openai-api`
- `model.default=$HERMES_LLM_MODEL`
- `model.api_mode=chat_completions`

Notes:

- `openai-api` here means OpenAI-compatible protocol routing, not a hard dependency on OpenAI.
- Provider swaps should only require changing `HERMES_LLM_BASE_URL`, `HERMES_LLM_API_KEY`, and `HERMES_LLM_MODEL`.
- PAOS application code should not require provider-specific variable names.
- `PAOS_HERMES_*` variables are PAOS runtime/orchestration controls, not provider credentials.
- `OPENAI_*` should be exported by the Hermes wrapper at runtime and not manually maintained as permanent `.env` source-of-truth keys.
- Wrapper path in container: `/workspace/paos-runtime/runtime/assistant/hermes/run_hermes.sh`
