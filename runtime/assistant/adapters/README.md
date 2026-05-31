# PAOS Assistant Adapters

Purpose: provide lightweight consumption guidance for external AI tools to read PAOS Assistant Context through one stable command.

## Official command

Use only the official context consumption command:

`venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai`

Supported options:

- `--format markdown|json`
- `--section all|profile|memory|runtime|intelligence`
- `--max-chars <number>`

## Common usage examples

- Session bootstrap (broad context):
  - `venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section all --max-chars 12000`
- Profile-only context:
  - `venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section profile --max-chars 6000`
- Runtime status check:
  - `venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section runtime --max-chars 4000`
- Intelligence-only:
  - `venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai --section intelligence --format json --max-chars 5000`

## Section guide

- `all`: session bootstrap and broad planning.
- `profile`: user/repo/project operating context.
- `memory`: temporary working memory.
- `runtime`: latest runtime and diagnostics state.
- `intelligence`: latest digest and insight context.

## Bounded context rule

- Prefer bounded section reads for focused tasks.
- Use `--max-chars` to keep context within tool limits.
- Use `--section all` only when broad context is required.
- If output is truncated, request a narrower section and/or lower scope.

## Source-of-truth and memory boundaries

- PAOS repository files remain the durable source of truth.
- Assistant context output is a bounded snapshot for consumption, not a replacement for repo evidence.
- Memory access boundary is only through `MemoryProvider`.
- Mnemosyne is temporary/global working memory behind `MemoryProvider` and must remain replaceable.

## Consumer guardrails

- Consume assistant context only through the official command.
- Do not read random internal PAOS folders directly for context assembly.
- Do not bypass `MemoryProvider` for memory access.
- Do not mutate runtime/memory state from context consumption workflows.
