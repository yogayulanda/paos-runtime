# Assistant Diagnostics Contract

Purpose: baseline health check for Phase 1 assistant foundation.

## Checks

- Assistant config file is present and readable.
- Latest digest artifact resolution executes.
- Latest insight artifact resolution executes.
- Runtime status directory readability check executes.
- Latest assistant context artifact resolution executes.
- Latest assistant brief artifact resolution executes.
- Latest assistant opportunities artifact resolution executes.

## Status semantics

- `success`: all required checks passed; no warnings.
- `success_with_warnings`: required checks passed; optional artifacts missing.
- `failed`: one or more required checks failed.

## Output

Diagnostics writes `.runtime/runs/assistant/latest.json` with:

- `status`
- `category`
- `generated_at`
- `checks`
- `warnings`
- `errors`
- `assistant_context`
- `assistant_brief`
- `assistant_opportunities`
- `resolved_artifacts`

`assistant_brief` includes markdown/json metadata:

- `path`
- `exists`
- `date`
- `modified_at`
- `size_bytes`
- `empty`
- `parseable` (JSON artifact)
- warnings for missing/stale/empty/parse-failure

`assistant_opportunities` includes the same markdown/json metadata:

- `path`
- `exists`
- `date`
- `modified_at`
- `size_bytes`
- `empty`
- `parseable` (JSON artifact)
- warnings for missing/stale/empty/parse-failure
