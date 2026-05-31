# Assistant Daily Planner Contract

## Purpose

The Daily Planner provides a compact, actionable daily plan derived from existing assistant artifacts. It answers: "What should I do today?"

## Sections

1. **Priorities Today** (max 3) — Derived from brief focus + build opportunities + structured opportunities
2. **Defer/Ignore** (1 item) — Lowest priority item or a non-critical risk to consciously skip
3. **Next Action** (1 item) — The single most important next step
4. **Context Update** (1 suggestion) — Whether context/brief needs refresh based on staleness
5. **Freshness** — Compact status of all artifact dates

## Data Sources

- `assistant/briefs/{date}/assistant-brief.json`
- `assistant/opportunities/{date}/opportunities.json`
- `assistant/context/{date}/assistant-context.json` (date only)
- `intelligence/digests/{date}/ai.md` (date only)
- `intelligence/insights/{date}/ai.md` (date only)

## Behavior

- Read-only. Never triggers pipeline runs.
- Degrades gracefully if artifacts are missing.
- Output is compact and safe for Telegram (max 3900 chars).
- No LLM calls. Deterministic formatting only.
- Priorities are deduplicated and ordered by specificity.

## Telegram Command

`/daily`

## Runtime Module

Bot handler in `bot/commands/assistant_surface.py` — uses file-based resolution directly.
