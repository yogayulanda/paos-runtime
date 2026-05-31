# Assistant Context Consumption Contract

Purpose: define the official bounded, read-only assistant context consumption interface for external AI tools in Phase 2.

## Official command

- `venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category <category>`

## Supported options

- `--format markdown|json` (default: `markdown`)
- `--section all|profile|memory|runtime|intelligence` (default: `all`)
- `--max-chars <number>` (default: `12000`)

## Resolution rules

- Command resolves the latest generated assistant context from `assistant/context/<YYYY-MM-DD>/assistant-context.json`.
- Resolution is filtered by requested `--category`.
- Only the latest matching artifact is consumed.
- Historical artifacts are not dumped as output.

## Read-only behavior

- Command is strictly read-only.
- Command must not write to:
  - `.runtime/*`
  - `assistant/context/*`
  - `runtime/assistant/memory/*`
- Command must not mutate MemoryProvider state.

## Sectioning rules

- `profile`: identity, working style, active projects, and related source metadata.
- `memory`: temporary memory and memory source metadata.
- `runtime`: runtime state and runtime source metadata.
- `intelligence`: latest intelligence summary and artifact source metadata.
- `all`: union of all sections plus guidance/diagnostics context.

## Max size and truncation

- Output is bounded by `--max-chars`.
- If output exceeds `--max-chars`, output is truncated.
- Truncation must be explicit with a marker containing:
  - configured max chars
  - omitted character count
  - source JSON path

## Source visibility

Output must include source metadata:

- source date folder (`YYYY-MM-DD`)
- source category
- source generated timestamp
- source JSON path
- source Markdown path (or missing)

## Consumer expectations

- Consumer should treat output as a bounded snapshot, not durable truth.
- Durable source of truth remains repository files and contracts.
- Temporary memory is advisory and short-lived.
- Missing optional data should be handled as warnings, not hard failure, when context exists.

## Guardrails for AI tools

- Do not mutate PAOS runtime/memory from this consumption interface.
- Do not infer historical trend from a single bounded snapshot.
- Do not treat temporary memory as authoritative without repo/runtime corroboration.
- Do not use this interface to trigger scheduler, GitHub collection, or Telegram workflow changes.
