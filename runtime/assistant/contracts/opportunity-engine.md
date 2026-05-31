# Opportunity Engine Contract

Purpose: generate a bounded, deterministic daily opportunity list from the latest Assistant Daily Brief.

## Inputs

- Primary source: `assistant/briefs/<YYYY-MM-DD>/assistant-brief.json`
- Secondary source: `assistant/briefs/<YYYY-MM-DD>/assistant-brief.md` (metadata-only fallback)

Raw intelligence files are out of scope for this phase.

## Outputs

Artifacts under `assistant/opportunities/<YYYY-MM-DD>/`:

- `opportunities.json`
- `opportunities.md`

`opportunities.json` fields:

- `date`
- `category`
- `generated_at`
- `opportunities`
- `source_artifacts`
- `warnings`

Each opportunity item includes:

- `id`
- `type` (`build|learn|content|review|career`)
- `priority` (`high|medium|low`)
- `title`
- `reason`
- `next_action`
- `source` (`assistant_brief`)
- `evidence` (optional)

## Behavior

- Deterministic rule-based transformation only.
- No LLM dependency.
- Target 3-7 opportunities.
- Avoid duplicate opportunities.
- If brief JSON is missing/invalid, fail clearly and include remediation command:
  - `venv/bin/python runtime/assistant/jobs/run_assistant_brief.py --category ai`

## Markdown layout

`opportunities.md` sections:

- `# PAOS Opportunities`
- `## High Priority`
- `## Medium Priority`
- `## Low Priority`
- `## Source Coverage`
- `## Warnings`
