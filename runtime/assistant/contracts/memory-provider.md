# Memory Provider Contract

Purpose: define the assistant memory boundary for Phase 1.

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

## Phase 1 providers

- `local` is the default JSONL-backed fallback and lives at `runtime/assistant/memory/local.jsonl` unless configured otherwise.
- `mnemosyne` is a placeholder provider for contract clarity only and does not require an external service.

## Selection rules

- Provider selection is config-driven through `runtime/assistant/config.yaml`.
- Diagnostics checks the configured provider first.
- If the configured provider is unavailable, diagnostics falls back to `local` when possible.
- Diagnostics writes the active provider status into `.runtime/runs/assistant/latest.json`.

## Behavior notes

- Missing local JSONL files are treated as empty storage, not as fatal errors.
- `recall()` returns the newest matching entries first.
- Empty query text returns latest items.
- `write()` appends JSONL records with `id`, `content`, `scope`, `created_at`, `source`, and `metadata`.
