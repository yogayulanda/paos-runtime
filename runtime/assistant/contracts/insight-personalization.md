# Insight Personalization Contract (Task 4 MVP)

Purpose: provide compact deterministic personalization for insight-related assistant surfaces.

Inputs (read-only):
- latest intelligence insight artifact (`intelligence/insights/<date>/ai.md`)
- latest digest artifact (`intelligence/digests/<date>/ai.md`) as fallback
- latest assistant context snapshot (`assistant/context/<date>/assistant-context.json`) when available

Output sections:
- Relevant Insight
- Why it matters to you
- PAOS / Forge relevance
- Work / career relevance
- Content opportunity
- Recommended action

Behavior:
- Deterministic keyword/rule-based relevance scoring only.
- No LLM API calls.
- Degrade gracefully when context is missing; keep insight visible with limited personalization note.
- Keep Telegram output compact.

Guardrails:
- No scheduler.
- No GitHub source collector changes.
- No Hermes bridge.
- No controlled write.
- No writes to repo `paos`.
- No memory writes (including Mnemosyne).
- No Candidate Pool changes.
- No pipeline runs triggered from Telegram insight personalization path.
