# PAOS Assistant Adapters

Purpose: operator guide for cross-tool context + memory access through PAOS MCP.

## Architecture

- Claude Code / Codex (WSL/PC)
- `->` SSH stdio command
- `->` PAOS MCP server (`run_paos_mcp.py`)
- `->` `MemoryProvider`
- `->` `local` or `mnemosyne` backend

## MCP server command

- `cd /home/ubuntu/paos/paos-runtime && exec venv/bin/python runtime/assistant/jobs/run_paos_mcp.py`

## Core MCP tools

- `paos_health`
- `paos_memory_write`
- `paos_memory_recall`
- `paos_context_get`
- `paos_brief_get`
- `paos_opportunities_get`

## Quick validation sequence

1. `paos_health` with `{"category":"ai"}`
2. `paos_memory_write` with test content
3. `paos_memory_recall` with same query
4. `paos_context_get` with `{"section":"memory","format":"json"}`
5. `paos_brief_get` with `{"category":"ai","format":"json"}`
6. `paos_opportunities_get` with `{"category":"ai","format":"json"}`

## Mnemosyne backend notes

- Default provider remains `local` unless config is explicitly changed.
- Use `provider: mnemosyne` with `fallback_provider: local` for validation.
- Mnemosyne runs local on VPS behind `MemoryProvider` only.
- Direct Mnemosyne REST/MCP SSE/public endpoint use is out of scope.

## Security baseline

- Use SSH key auth.
- Do not open public MCP ports.
- Do not expose Mnemosyne directly.
- Do not expose raw DB files.
