# Claude Code Adapter Guide

Purpose: consistent Claude Code consumption of PAOS Assistant Context using the official read-only command.

## Recommended entrypoint

Run before starting repo work in a session:

`venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section all --max-chars 12000`

If the response is too large, switch to sectioned reads.

## Section usage during long sessions

- Start with `--section all` when bounded enough.
- During implementation/debug cycles, prefer specific sections:
  - `--section profile` for operating constraints and project context.
  - `--section runtime` for latest run and diagnostics state.
  - `--section intelligence` for latest digest/insight references.
  - `--section memory` for temporary working memory.

## Bounded context practice

- Keep `--max-chars` explicit.
- Use smaller bounds for iterative loops and targeted tasks.
- Re-query a narrow section rather than reloading full context repeatedly.

## Validation discipline

- Do not treat generated assistant context as code source.
- Validate implementation decisions against actual repository files.
- Use assistant context as operating guidance, then verify in repo.

## Guardrails

- Read-only consumption only.
- Do not read internal PAOS folders directly for ad-hoc context assembly.
- Do not bypass `MemoryProvider`.
- Do not mutate runtime or memory through context-consumption flow.
