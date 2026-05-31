# Assistant Context Contract

Purpose: define the bounded assistant context envelope for Phase 1.

## Inputs

- Configured durable repo context files
- Latest digest markdown artifact when available
- Latest insight markdown artifact when available
- Runtime status snapshots from `.runtime/runs/*/latest.json`
- Temporary memory from the configured `MemoryProvider`

## Outputs

- Markdown context artifact at `assistant/context/<YYYY-MM-DD>/assistant-context.md`
- JSON context artifact at `assistant/context/<YYYY-MM-DD>/assistant-context.json`

## Sections

- `Identity Context`
- `Working Style`
- `Active Projects`
- `Runtime State`
- `Latest Intelligence`
- `Temporary Memory`
- `Current Assistant Guidance`

## Guarantees

- Context assembly does not mutate intelligence artifacts.
- Missing repo context files are warnings, not hard failures.
- Missing digest/insight artifacts are warnings when context can still be generated.
- Runtime status parse failure for a single file does not abort context generation.
- Memory provider failure uses fallback behavior when possible and is surfaced in diagnostics.
- Generated context is bounded and deterministic; no LLM calls are used.
