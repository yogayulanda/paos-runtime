# Query Engine Contract (Task 3 MVP)

Purpose: provide read-only free-text routing for Telegram non-command messages.

Supported intents:
- daily
- dashboard
- insight_relevance
- memory
- handoff
- context_update
- context_health
- opportunities
- status
- unknown

Routing behavior:
- Slash commands remain source of truth.
- Non-command text uses deterministic keyword/rule-based intent routing.
- Each intent should delegate to existing read-only command surfaces where practical.
- Unknown intent returns compact fallback with examples.

Guardrails:
- No scheduler.
- No GitHub source.
- No Hermes bridge.
- No controlled write.
- No memory write.
- No promotion write.
- No pipeline run trigger from Telegram.
- No LLM API calls.
