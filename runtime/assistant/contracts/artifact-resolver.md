# Artifact Resolver Contract

Purpose: resolve latest assistant-facing artifacts for a category.

## Resolution rules

- Digest source: `intelligence/digests/<date>/<category>.md`
- Insight source: `intelligence/insights/<date>/<category>.md`
- Prefer current local date when available.
- Fallback to latest available date folder when today's file is absent.
- Runtime statuses source: `.runtime/runs/*/latest.json`

## Returned metadata

Each resolved artifact includes:

- `path`
- `exists`
- `date`
- `modified_at`
- `size_bytes`

Missing optional digest/insight artifacts must return `exists=false` instead of raising.
