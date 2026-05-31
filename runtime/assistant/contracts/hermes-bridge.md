# Hermes Bridge Contract (Design Only)

Purpose: define the design boundary for a future Hermes bridge without implementing runtime behavior in this phase.

## 1. Purpose

- Hermes is an external consumer of PAOS Assistant Context and MemoryProvider-facing capabilities.
- PAOS remains the Assistant OS Layer and must not become Hermes-specific runtime logic.
- This contract is design-only and does not mean Hermes bridge implementation exists yet.

## 2. Consumption model

Hermes consumes assistant context through official bounded interfaces:

- `runtime/assistant/jobs/print_assistant_context.py`
- Latest generated assistant context artifact at `assistant/context/<YYYY-MM-DD>/assistant-context.{md,json}`

Rules:

- Hermes should not read random internal PAOS folders directly for context assembly.
- Hermes should rely on source metadata and bounded output from official interfaces.

## 3. Memory boundary

- Hermes must not bypass `MemoryProvider`.
- Future Hermes recall/write behavior must go through MemoryProvider-facing interface only.
- Mnemosyne remains temporary/global working memory behind MemoryProvider.
- PAOS repository remains the durable source of truth.

## 4. Allowed future bridge shape

- Thin wrapper or command adapter around official PAOS assistant interfaces.
- MCP exposure is allowed later only when explicitly implemented.
- No direct coupling from assistant core internals to Hermes-specific implementation details.

## 5. Non-goals (current phase)

- No Hermes runtime implementation now.
- No MCP server now.
- No scheduler/cron integration.
- No intelligence pipeline change.
- No Telegram UX change.
- No Candidate/Signal/Digest contract change.

## 6. Failure behavior

- If assistant context artifact is missing, Hermes should fail clearly with actionable error output.
- If memory provider is unavailable, fallback/local diagnostics visibility should be preserved.
- Hermes should not silently mutate PAOS runtime or memory state.

## 7. Future acceptance criteria

- Hermes can load bounded assistant context through official consumption interfaces.
- Hermes can request memory recall/write only through MemoryProvider boundary.
- Bridge remains replaceable and minimal.
- PAOS remains tool-agnostic and durable-source oriented.
