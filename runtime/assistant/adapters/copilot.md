# Copilot Adapter Guide

Purpose: lightweight/manual PAOS Assistant Context consumption for Copilot workflows.

## Recommended pattern

Use the official command and prefer selected sections because Copilot context windows may be limited.

Base command:

`venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai`

## Practical section usage

- Start with `--section profile` for user/project operating context.
- Use `--section runtime` when checking latest runtime or diagnostics condition.
- Use `--section intelligence` when digest/insight context is needed.
- Use `--section memory` only when temporary working memory is relevant.
- Avoid `--section all` unless broad bootstrap context is necessary.

## Bounded context usage

- Keep `--max-chars` small for snippet-friendly consumption.
- Pull multiple focused reads instead of one oversized read.
- If truncated, rerun with narrower section and lower bound.

## Source and memory boundaries

- PAOS repository remains durable source of truth.
- Assistant context is a bounded helper snapshot.
- Memory access must stay behind `MemoryProvider`.
- Mnemosyne is temporary/global working memory behind `MemoryProvider`.

## Guardrails

- Do not read internal PAOS folders directly for context assembly.
- Do not bypass `MemoryProvider`.
- Do not mutate runtime/memory through context consumption.
