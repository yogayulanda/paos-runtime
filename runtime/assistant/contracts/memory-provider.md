# Memory Provider Contract

Purpose: define the assistant memory boundary for Phase 3C.

## Interface

- `healthcheck()`
- `recall(query)`
- `write(item)`

## Minimal models

- `MemoryHealth`
- `MemoryQuery`
- `MemoryItem`
- `MemoryWrite`
- `MemoryWriteResult`

## Providers

- `local` is the default JSONL-backed fallback and lives at `runtime/assistant/memory/local.jsonl` unless configured otherwise.
- `mnemosyne` is a local-only SDK adapter behind the same interface.
  - It uses `mnemosyne-memory` Python SDK and local data directory configuration.
  - It does not expose or require direct REST, MCP SSE, or public network access.

## Selection rules

- Provider selection is config-driven through `runtime/assistant/config.yaml`.
- Diagnostics checks the configured provider first.
- If the configured provider is unavailable, diagnostics falls back to `local` when possible.
- Diagnostics writes the active provider status into `.runtime/runs/assistant/latest.json`.

## Behavior notes

- Missing local JSONL files are treated as empty storage, not as fatal errors.
- Missing Mnemosyne package or SDK initialization failures mark provider unavailable and trigger fallback selection when configured.
- `recall()` returns the newest matching entries first.
- Empty query text returns latest items.
- `write()` appends JSONL records with `id`, `content`, `scope`, `created_at`, `source`, and `metadata`.
- Mnemosyne healthcheck is SDK-focused and may optionally run a strict lightweight remember/recall probe when enabled.
- Mnemosyne `backup`/`verify` commands are operational tools and not used as provider health gates.

## Out of scope

- Direct Mnemosyne REST integration.
- Direct Mnemosyne MCP SSE integration.
- Public Mnemosyne endpoint exposure.
- Any MCP tool bypassing `MemoryProvider`.
