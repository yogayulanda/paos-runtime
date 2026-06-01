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
1. For Phase 5 action-loop intents (`buat action hari ini`, `pending`, `pilih nomor`, `focus`, `tunda/tolak/accept`), use PAOS deterministic local action-loop route first.
2. For other free-text intents, try Hermes through non-interactive CLI invocation (`hermes -z`) inside `paos-hermes`.
3. Before Hermes invocation, PAOS may prefetch compact read-only evidence (context/status/dashboard/daily/handoff/source/action-loop) and inject it as `PAOS_READ_EVIDENCE`.
4. If Hermes returns usable text, return that text to Telegram.
5. If Hermes is unavailable/errors/times out, fall back to PAOS deterministic free-text intent router.
6. If PAOS router cannot classify intent, return existing fallback/help text.

Guardrails:
- Read-only Telegram flow.
- No `paos_memory_write` invocation.
- No controlled write apply.
- No scheduler changes.
- No GitHub source mutation.
- No public HTTP/SSE/API introduced for this bridge.
- Mutation-like requests must stop at draft + approval boundary.
- Blocked requests must be refused safely without executable commands.

Response policy for free-text:
- Default response language: Indonesian.
- Keep responses concise and action-oriented.
- For PAOS state/runtime/dashboard/context questions, prefer:
  - `paos_operating_summary_get`
  - `paos_runtime_status_get`
  - `paos_dashboard_get`
  - `paos_context_health_get`
- For daily/focus questions, prefer:
  - `paos_operating_summary_get`
  - `paos_daily_plan_get`
  - `paos_daily_get`
  - `paos_opportunities_get`
- For handoff questions, prefer:
  - `paos_handoff_get`
- For draft/policy/approval-boundary questions, prefer:
  - `paos_action_policy_get`
  - `paos_action_draft_create`
- For source/intelligence status questions, prefer:
  - `paos_source_status_get`
- For source intelligence expansion questions, prefer:
  - `paos_source_digest_get`
  - `paos_source_insight_get`
  - `paos_source_candidates_get`
  - `paos_source_recommendation_get`
  - `paos_source_action_draft_create`
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
- Completed: provider activation, Telegram Hermes-first orchestration, prompt/policy tuning, Phase 3 MCP read surfaces, Phase 4 draft boundary, and Phase 5 persistent action loop.
- Current status: Phase 8 stabilization & daily operating loop hardening.
- Primary UX: natural-language Telegram orchestration, not command memorization.
- Hermes may use local action-loop MCP tools for create/list/resolve/state-transition.
- Accepted action means approved direction/focus only, not executed/applied.
- Every state-changing response must preserve: "No external action was applied."
- Do not suggest slash commands unless fallback/debug is needed.
- Do not dump raw memory; summarize evidence compactly.
- Gateway must remain stopped; never propose/attempt gateway start.

Phase 5 tools:
- `paos_action_list`
- `paos_action_get`
- `paos_action_event_list`
- `paos_daily_action_generate`
- `paos_action_resolve`
- `paos_action_state_transition`

Phase 5 boundaries:
- No `paos_memory_write`.
- No controlled write apply.
- No scheduler/GitHub/repo mutation.
- No memory write (`paos_memory_write`) in free-text flow.
- No public API/tunnel/gateway enable.
- Local action-loop persistence only.

Implementation notes:
- Hermes timeout should stay bounded (30-60 seconds).
- Invocation must be internal only (`docker exec` into `paos-hermes`).
- Errors from Hermes should not leak secrets and should not break Telegram handling.
- Feature gate:
  - `PAOS_HERMES_ORCHESTRATION_ENABLED` defaults to `false`.
  - Truthy values: `1`, `true`, `yes`, `on` (case-insensitive).
  - `PAOS_HERMES_TIMEOUT_SECONDS` defaults to `45`.

## Phase 9 Addendum (Runtime-Stable External Agent Orchestration)

- For broad readiness/status questions, prefer:
  - `paos_runtime_status_get`
  - `paos_operating_summary_get`
  - `paos_daily_plan_get`
- For external agent handoff/prompt generation, prefer:
  - `paos_agent_handoff_create`
  - `paos_agent_handoff_get`
  - `paos_agent_handoff_list`
- For external agent result review/integration, prefer:
  - `paos_agent_result_review`
  - `paos_agent_next_action_draft`
  - `paos_agent_memory_candidate_create`
- Do not ask users to memorize commands.
- Do not auto-dispatch external agents unless approved connector exists.
- Do not mutate GitHub/repo/scheduler and do not write memory silently.
- Gateway must remain stopped.
- Preserve semantics: accepted action != executed; handoff != execution.
