# Assistant Dashboard Contract

## Purpose

The PAOS Dashboard is the Assistant OS home screen. It provides a combined, read-only view of the assistant's current state, priorities, and health.

## Distinction

The dashboard is NOT the same as:
- `/brief` — which shows the raw assistant brief artifact
- `/today` — which shows a focused daily summary
- `/insight` — which shows the intelligence dashboard
- `/opportunities` — which shows the full opportunity list

The dashboard COMBINES information from all of these into a single home screen.

## Sections

1. **Fokus Hari Ini** — Extracted from the latest brief focus + build opportunities
2. **Current State** — Artifact availability and freshness for brief, opportunities, context, digest, insight
3. **Relevant Intelligence** — Latest digest/insight artifact dates if available
4. **Top Opportunities** — Top 3 structured opportunities by priority
5. **Recommended Actions** — Suggested next actions derived from brief + missing artifact gaps
6. **Context Health** — Whether context/brief/opportunities are loaded, runtime job count
7. **Source Status** — Runtime job statuses (compact)

## Data Sources

- `assistant/briefs/{date}/assistant-brief.json`
- `assistant/opportunities/{date}/opportunities.json`
- `assistant/context/{date}/assistant-context.json`
- `intelligence/digests/{date}/ai.md`
- `intelligence/insights/{date}/ai.md`
- `.runtime/runs/*/latest.json`

## Behavior

- Read-only. Never triggers pipeline runs.
- Degrades gracefully if artifacts are missing or stale.
- Output is compact and safe for Telegram (max 3900 chars).
- No LLM calls. Deterministic formatting only.

## Telegram Command

`/dashboard`

## Runtime Module

Bot handler in `bot/commands/assistant_surface.py` — uses file-based resolution directly.
