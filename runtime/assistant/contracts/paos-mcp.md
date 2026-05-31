# PAOS MCP Contract

Purpose: define the Phase 3B/3C MCP bridge for cross-tool working memory and assistant context.

## Architecture

- Claude Code / Codex
- `->` SSH stdio command
- `->` `runtime/assistant/jobs/run_paos_mcp.py`
- `->` PAOS MCP tools
- `->` `MemoryProvider`
- `->` `local` or `mnemosyne` backend

PAOS MCP must not import Mnemosyne directly; backend selection remains in `MemoryProvider`.

## Transport

- Supported transport: `stdio` only.
- Public HTTP/SSE listeners are out of scope.

## Server entrypoint

- `venv/bin/python runtime/assistant/jobs/run_paos_mcp.py`

## Tool: `paos_health`

Input:

- `category` (optional)
- `include_diagnostics` (optional, default `true`)

Output:

- `ok`
- `category`
- `category_source`
- `memory_provider`
- `diagnostics_status`
- `warnings`
- `errors`

## Tool: `paos_memory_write`

Input:

- `content` (required, non-empty, bounded)
- `scope` (optional)
- `category` (optional)
- `metadata` (optional object, bounded)

Output:

- `ok`
- `category`
- `category_source`
- `memory_provider`
- `result`
- `warnings`
- `errors`

Behavior:

- Mutates memory only through `MemoryProvider.write()`.

## Tool: `paos_memory_recall`

Input:

- `query` (optional, default empty)
- `scope` (optional)
- `category` (optional)
- `limit` (optional, default `10`, max `50`)

Output:

- `ok`
- `category`
- `category_source`
- `memory_provider`
- `items`
- `warnings`
- `errors`

Behavior:

- Reads memory only through `MemoryProvider.recall()`.

## Tool: `paos_context_get`

Input:

- `category` (optional)
- `format` (`json|markdown`, default `json`)
- `section` (`all|profile|memory|runtime|intelligence`, default `all`)
- `max_chars` (default `12000`, bounded)

Output:

- `ok`
- `category`
- `category_source`
- `format`
- `section`
- `max_chars`
- `content`
- `warnings`
- `errors`

Behavior:

- Uses official context consumption command:
  - `runtime/assistant/jobs/print_assistant_context.py`

## Tool: `paos_brief_get`

Input:

- `category` (optional)
- `format` (`json|markdown`, default `json`)

Output:

- `ok`
- `category`
- `category_source`
- `format`
- `content`
- `brief`
- `warnings`
- `errors`

Behavior:

- Reads latest assistant brief artifact from `assistant/briefs/<YYYY-MM-DD>/assistant-brief.{json|md}`.
- Read-only operation; does not mutate memory.
- Must not import Mnemosyne directly.

## Tool: `paos_opportunities_get`

Input:

- `category` (optional)
- `format` (`json|markdown`, default `json`)

Output:

- `ok`
- `category`
- `category_source`
- `format`
- `content`
- `opportunities`
- `warnings`
- `errors`

Behavior:

- Reads latest assistant opportunities artifact from `assistant/opportunities/<YYYY-MM-DD>/opportunities.{json|md}`.
- Read-only operation; does not mutate memory.
- Must not import Mnemosyne directly.

## Security constraints

- SSH key auth required for remote usage.
- No public listener.
- No raw DB/file API.
- No direct Mnemosyne endpoint exposure.
- No secrets in tool responses.

## Phase 5 Action Loop Tools

Tools are local-persistence only and must not execute external actions:
- `paos_action_list(state?, limit?)`
- `paos_action_get(action_id)`
- `paos_action_event_list(action_id?)`
- `paos_daily_action_generate(category?, persist?)`
- `paos_action_resolve(reference?, ordinal?, query?)`
- `paos_action_state_transition(action_id, transition, note?)`

Invariants:
- `accepted != executed`
- `approved != applied`
- local action-loop writes only (`assistant/action-loop/*`)
- every state-changing flow remains no-apply/no-external-write

## Mnemosyne scope

- Mnemosyne support is local SDK backend only.
- Direct Mnemosyne REST and MCP SSE are out of scope.
- `fallback_provider: local` remains mandatory.

## Failure behavior

- Tools return structured `ok=false`, `warnings`, `errors`.
- Provider fallback behavior remains owned by `MemoryProvider` factory.
