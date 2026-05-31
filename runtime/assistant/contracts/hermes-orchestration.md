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
2. Before invocation, PAOS may prefetch compact read-only evidence for high-value intents (context/status/dashboard/daily/handoff/source) and inject it into prompt as `PAOS_READ_EVIDENCE`.
3. If Hermes returns usable text, return that text to Telegram.
4. If Hermes is unavailable/errors/times out, fall back to PAOS deterministic free-text intent router.
5. If PAOS router cannot classify intent, return existing fallback/help text.

Guardrails:
- Read-only Telegram flow.
- No `paos_memory_write` invocation.
- No controlled write apply.
- No scheduler changes.
- No GitHub source mutation.
- No public HTTP/SSE/API introduced for this bridge.

Response policy for free-text:
- Default response language: Indonesian.
- Keep responses concise and action-oriented.
- For PAOS state/runtime/dashboard/context questions, prefer:
  - `paos_runtime_status_get`
  - `paos_dashboard_get`
  - `paos_context_health_get`
- For daily/focus questions, prefer:
  - `paos_daily_get`
  - `paos_opportunities_get`
- For handoff questions, prefer:
  - `paos_handoff_get`
- For source/intelligence status questions, prefer:
  - `paos_source_status_get`
- Primitive read tools (fallback/composition):
  - `paos_health`
  - `paos_context_get`
  - `paos_brief_get`
  - `paos_opportunities_get`
  - `paos_memory_recall`
- Do not claim tools are unavailable unless MCP/tool call actually fails.
- Do not provide generic roadmap advice when current PAOS state can be inspected.
- Avoid open-ended endings like "Kalau mau..." / "Aku bisa...".
- For "next apa?" style questions, structure answer with:
  1. Current status
  2. One recommended next step
  3. Why
  4. Concrete validation/action

Known roadmap anchor:
- Completed: provider activation, Telegram Hermes-first orchestration, prompt/policy tuning, and Phase 3 MCP read surfaces.
- Current next recommended phase: Phase 4 Agentic Draft + Approval Boundary.
- Then: persistence, daily automation, GitHub source activation, intelligence expansion, memory upgrade.

Implementation notes:
- Hermes timeout should stay bounded (30-60 seconds).
- Invocation must be internal only (`docker exec` into `paos-hermes`).
- Errors from Hermes should not leak secrets and should not break Telegram handling.
- Feature gate:
  - `PAOS_HERMES_ORCHESTRATION_ENABLED` defaults to `false`.
  - Truthy values: `1`, `true`, `yes`, `on` (case-insensitive).
  - `PAOS_HERMES_TIMEOUT_SECONDS` defaults to `45`.
