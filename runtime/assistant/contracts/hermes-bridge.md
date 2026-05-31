# Hermes Bridge Contract

Purpose: define the runtime-safe Hermes consumption boundary for PAOS Assistant surfaces.

## 1. Purpose

- Hermes is an external consumer of PAOS Assistant and MCP-facing capabilities.
- PAOS remains the Assistant OS layer and must not become Hermes-specific runtime logic.
- Hermes is a client/consumer only. PAOS runtime must continue to operate without Hermes.

## 2. Consumption model

Hermes consumes PAOS through official bounded interfaces:

- PAOS MCP server entrypoint:
  - `venv/bin/python runtime/assistant/jobs/run_paos_mcp.py`
- Read-only assistant context command:
  - `runtime/assistant/jobs/print_assistant_context.py`
- Generated artifacts:
  - `assistant/context/<YYYY-MM-DD>/assistant-context.{md,json}`
  - `assistant/briefs/<YYYY-MM-DD>/assistant-brief.{md,json}`
  - `assistant/opportunities/<YYYY-MM-DD>/opportunities.{md,json}`

Rules:

- Hermes should not read random internal PAOS folders directly for context assembly.
- Hermes should rely on bounded outputs from official interfaces only.

## 3. Memory boundary

- Hermes must not bypass `MemoryProvider`.
- Recall/write behavior must go through PAOS MCP tools only.
- Mnemosyne remains temporary/global working memory behind `MemoryProvider`.
- PAOS repository remains the durable source of truth.

## 4. Allowed future bridge shape

- Hermes should use a thin adapter over existing PAOS MCP tools.
- No direct coupling from assistant core internals to Hermes-specific implementation details.

## 5. Non-goals (current phase)

- No scheduler/cron integration.
- No intelligence pipeline change.
- No Telegram UX change.
- No Candidate/Signal/Digest contract change.

## 6. Failure behavior

- If artifacts are missing, Hermes should fail clearly with actionable errors.
- If configured memory provider is unavailable, PAOS fallback status from `memory_provider` must be surfaced.
- Hermes should not silently mutate PAOS runtime or memory state.

## 7. Future acceptance criteria

- Hermes can call these MCP tools over stdio:
  - `paos_health`
  - `paos_context_get`
  - `paos_brief_get`
  - `paos_opportunities_get`
  - `paos_memory_recall`
- Optional write tool usage (`paos_memory_write`) is out of scope for this runtime validation.
- Bridge remains replaceable and minimal.
- PAOS remains tool-agnostic and durable-source oriented.
