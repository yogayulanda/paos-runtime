# Context Health Contract

## Purpose

The Context Health inspector provides a diagnostic view of the assistant's context pipeline state. It answers: "Is my assistant context healthy and up to date?"

## Sections

1. **Artifact Status** — Whether each artifact (context, brief, opportunities, digest, insight) is loaded, with freshness label
2. **Runtime Jobs** — Total count, OK/failed breakdown, failed job names
3. **Warnings** — Collected from context diagnostics payload + staleness checks
4. **Memory Provider** — Status note (read-only, directs to /ops or diagnostics job for full health)

## Data Sources

- `assistant/context/{date}/assistant-context.json` (existence + diagnostics.warnings)
- `assistant/briefs/{date}/assistant-brief.json` (existence + date)
- `assistant/opportunities/{date}/opportunities.json` (existence + date)
- `intelligence/digests/{date}/ai.md` (existence + date)
- `intelligence/insights/{date}/ai.md` (existence + date)
- `.runtime/runs/*/latest.json` (job statuses)

## Behavior

- Read-only. Never triggers pipeline runs.
- Does NOT build memory UX or expose memory internals.
- Degrades gracefully if artifacts are missing.
- Output is compact and safe for Telegram (max 3900 chars).
- No LLM calls. Deterministic formatting only.
- Staleness warnings are generated for artifacts older than today.

## Telegram Command

`/context`

## Runtime Module

Bot handler in `bot/commands/assistant_surface.py` — uses file-based resolution directly.
Diagnostics module at `runtime/assistant/diagnostics/checks.py` provides deeper checks for job/MCP use.
