# Hermes Adapter Guide

Purpose: runtime guidance for Hermes to consume PAOS safely as an external client.

## Consumption interface

Hermes should consume PAOS through MCP stdio first:

`venv/bin/python runtime/assistant/jobs/run_paos_mcp.py`

Primary tools for Hermes:

- `paos_health`
- `paos_context_get`
- `paos_brief_get`
- `paos_opportunities_get`
- `paos_memory_recall`

Context fallback (if MCP is not wired in Hermes yet):

`venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section all --max-chars 12000`

## Design boundary

- Adapter is thin and read-focused.
- Do not add Hermes-specific behavior inside PAOS core runtime.

## Source and memory model

- PAOS repo is the durable source of truth.
- Assistant context output is a bounded, read-only snapshot.
- Memory boundary is `MemoryProvider` only.
- Mnemosyne remains temporary/global working memory behind `MemoryProvider`.

## Hermes guardrails

- Hermes must not read internal PAOS runtime folders directly.
- Hermes must not bypass `MemoryProvider`.
- Hermes must not mutate runtime/memory through context consumption.
- Hermes should validate repo-affecting conclusions against repository files and contracts.

## Notes for dashboard/daily surfaces

- There is no dedicated MCP tool named `paos_dashboard` or `paos_daily` in current runtime.
- Hermes can assemble dashboard/daily-equivalent summaries from:
  - `paos_context_get` (`section=all|runtime|intelligence|memory`)
  - `paos_brief_get`
  - `paos_opportunities_get`
