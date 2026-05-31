# Assistant Handoff Contract

Purpose: generate copy-paste-ready handoff summaries from Telegram `/handoff`.

Supported commands:
- `/handoff`
- `/handoff codex`
- `/handoff claude`

Required sections:
- Task summary
- Current state
- Decisions
- Next action
- Files/context to inspect
- Validation needed
- Guardrails

Rules:
- Read-only.
- Deterministic formatting (no new LLM calls).
- May use latest assistant brief/context/opportunities artifacts.
- Include continuation target hints for codex/claude variants.
