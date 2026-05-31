# Hermes Adapter Guide

Purpose: design-only guidance for Hermes consumption of PAOS Assistant Context in Phase 2.

## Consumption interface

Hermes should consume assistant context through the official command or its output file stream:

`venv/bin/python runtime/assistant/jobs/print_assistant_context.py --category ai`

Recommended bounded usage:

- Bootstrap: `--section all --max-chars 12000`
- Focused runs: `--section profile|memory|runtime|intelligence` with tighter `--max-chars`

## Design boundary

- This step is documentation only.
- No Hermes bridge implementation is included in this phase step.

## Source and memory model

- PAOS repo is the durable source of truth.
- Assistant context output is a bounded, read-only snapshot.
- Memory boundary is `MemoryProvider` only.
- Mnemosyne remains temporary/global working memory behind `MemoryProvider`.

## Hermes guardrails

- Hermes must not read internal PAOS runtime folders directly.
- Hermes must not bypass `MemoryProvider`.
- Hermes must not mutate runtime/memory through context consumption.
- Hermes should validate repo-affecting conclusions against repository files and contracts.
