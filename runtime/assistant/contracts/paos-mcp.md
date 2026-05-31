# PAOS MCP Contract

Purpose: define the minimal Phase 3B stdio MCP bridge for cross-tool memory/context access.

## Transport

- Supported transport: `stdio` only.
- Public HTTP/SSE listeners are out of scope for this phase.

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

Behavior:

- Resolves category via assistant config resolution rules.
- Uses assistant diagnostics and memory provider selection.

## Tool: `paos_memory_write`

Input:

- `content` (required, non-empty, bounded length)
- `scope` (optional)
- `category` (optional)
- `metadata` (optional object, bounded serialized size)

Output:

- `ok`
- `category`
- `category_source`
- `memory_provider`
- `result`
- `warnings`
- `errors`

Behavior:

- Uses `load_memory_provider()` and `MemoryWrite` contract.
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

- Uses `load_memory_provider()` and `MemoryQuery` contract.
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

- Executes official context consumption command:
  - `runtime/assistant/jobs/print_assistant_context.py`
- Preserves existing context resolution and truncation behavior.

## Security constraints

- No public network listener.
- No direct Mnemosyne endpoint exposure.
- No raw DB/file API.
- No secrets in tool responses.

## Failure behavior

- Tool failures return structured payloads with `ok=false`, `warnings`, and `errors`.
- Provider fallback behavior remains owned by MemoryProvider factory.
