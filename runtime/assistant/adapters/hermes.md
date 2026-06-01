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
- `paos_dashboard_get`
- `paos_daily_get`
- `paos_context_health_get`
- `paos_handoff_get`
- `paos_runtime_status_get`
- `paos_operating_summary_get`
- `paos_daily_plan_get`
- `paos_source_status_get`

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

- Prefer dedicated read tools:
  - `paos_operating_summary_get`
  - `paos_daily_plan_get`
  - `paos_dashboard_get`
  - `paos_daily_get`
  - `paos_context_health_get`
- Fallback composition (when needed):
  - `paos_context_get` (`section=all|runtime|intelligence|memory`)
  - `paos_brief_get`
  - `paos_opportunities_get`

## Phase 5B UX + Safety Policy

- Natural-language first; slash commands are fallback/admin/debug only.
- Prefer action-loop tools for conversational approvals (`1`, `pilih nomor 1`, `accept yang tadi`).
- `paos_memory_write` must not be used in normal free-text orchestration.
- `paos_action_state_transition` changes local state only; no external execution.
- Preserve boundary text for state changes: `No external action was applied.`
