# Hermes Free-Text Orchestration Contract

Purpose: define Hermes-first behavior for Telegram free-text while preserving PAOS deterministic command surfaces.

Scope:
- Applies only to non-command Telegram text.
- Slash commands remain PAOS direct:
  - `/dashboard`
  - `/daily`
  - `/context`
  - `/memory`
  - `/status`
  - `/ops`
  - `/help`
  - `/handoff hermes`
  - existing command set

Routing:
1. Try Hermes first through non-interactive CLI invocation (`hermes -z`) inside `paos-hermes`.
2. If Hermes returns usable text, return that text to Telegram.
3. If Hermes is unavailable/errors/times out, fall back to PAOS deterministic free-text intent router.
4. If PAOS router cannot classify intent, return existing fallback/help text.

Guardrails:
- Read-only Telegram flow.
- No `paos_memory_write` invocation.
- No controlled write apply.
- No scheduler changes.
- No GitHub source mutation.
- No public HTTP/SSE/API introduced for this bridge.

Implementation notes:
- Hermes timeout should stay bounded (30-60 seconds).
- Invocation must be internal only (`docker exec` into `paos-hermes`).
- Errors from Hermes should not leak secrets and should not break Telegram handling.
- Feature gate:
  - `PAOS_HERMES_ORCHESTRATION_ENABLED` defaults to `false`.
  - Truthy values: `1`, `true`, `yes`, `on` (case-insensitive).
  - `PAOS_HERMES_TIMEOUT_SECONDS` defaults to `45`.
