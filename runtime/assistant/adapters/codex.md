# Codex Adapter Guide

Purpose: guide Codex to consume PAOS Assistant Context consistently before and during implementation work.

## Recommended usage

Before implementation tasks, load bounded context via official command:

`venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section all --max-chars 12000`

Then combine with direct repository inspection.

## Working pattern

- Use assistant context to align constraints and operating guidance.
- Confirm details by inspecting source files, contracts, and current git state.
- Keep staging boundary explicit for each change set.

## Section-focused reads

- `profile`: implementation constraints and project orientation.
- `runtime`: latest execution/diagnostics status.
- `intelligence`: latest digest/insight context for bounded awareness.
- `memory`: temporary working memory when relevant.

## Bounded context rule

- Prefer targeted section reads over repeatedly loading full context.
- Set `--max-chars` based on task scope and context budget.
- Re-run with narrower section if truncation occurs.

## Source and memory boundaries

- PAOS repo is durable source of truth.
- Assistant context is supporting guidance, not replacement for repo evidence.
- Memory boundary is `MemoryProvider` only.
- Mnemosyne remains temporary/global working memory behind `MemoryProvider`.

## Guardrails

- Use the official command only for context consumption.
- Do not read random internal PAOS runtime folders directly.
- Do not bypass `MemoryProvider`.
- Do not mutate runtime/memory from context-consumption workflow.
