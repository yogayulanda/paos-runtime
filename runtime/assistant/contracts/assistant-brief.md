# Assistant Brief Contract

Purpose: define the deterministic daily assistant brief artifact and generation boundaries for Phase 4.

## Question

The brief answers:

- Based on today's assistant context, digest, insight, memory, and runtime status, what should I focus on next?

## Inputs

Brief generation is read-only and uses existing artifacts:

- Latest assistant context artifact (`assistant/context/<YYYY-MM-DD>/assistant-context.json` preferred)
- Latest digest artifact metadata/content excerpt
- Latest insight artifact metadata/content excerpt
- Runtime status snapshots under `.runtime/runs/*/latest.json`
- MemoryProvider recall (optional advisory input)

## Output artifacts

Per generated date:

- `assistant/briefs/YYYY-MM-DD/assistant-brief.md`
- `assistant/briefs/YYYY-MM-DD/assistant-brief.json`

## JSON fields

Required top-level fields:

- `date`
- `category`
- `generated_at`
- `focus_today`
- `opportunities`
- `risks_or_checks`
- `suggested_next_action`
- `source_artifacts`
- `warnings`

`opportunities` must contain:

- `build`
- `learn`
- `content`
- `review`

## Markdown structure

- `# PAOS Assistant Brief`
- `## Fokus Hari Ini`
- `## Opportunity Ringan`
- `### Build`
- `### Learn`
- `### Content`
- `### Review`
- `## Risiko / Perlu Dicek`
- `## Suggested Next Action`
- `## Source Coverage`

## Behavior rules

- Deterministic and rule-based MVP; no mandatory LLM call.
- Degrade gracefully when some sources are missing; include warnings.
- Fail only if no usable source exists.
- Keep output concise and actionable.
- Generation must not mutate intelligence artifacts.
- MCP read exposure must not write memory and must not import Mnemosyne directly.
