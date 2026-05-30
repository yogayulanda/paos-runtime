# PAOS Runtime

PAOS Runtime is the execution layer for personal intelligence workflows in PAOS.

It is intentionally separate from:
- `personal-context` as the long-term source of truth
- Mnemosyne as temporary working memory

## Intelligence Architecture

```text
Collectors
-> Raw Intelligence Storage
-> Candidate Pool
-> Signal Builder
-> Digest
-> Insight Engine
-> Telegram Delivery
```

## Supported Sources (Current)

- Threads account collection
- RSS feed collection

The pipeline is source-driven:
- trusted sources are prioritized for signal quality
- discovery sources can still be included by policy
- current validated source families are Threads and RSS

## Candidate Pool

Candidate Pool:
- loads raw items from source families
- applies policy-based batching by source type
- uses noise-only filtering for Threads account items
- uses feed policy for RSS items
- runs shared dedupe after policy batching

## Signal Layer

Signal Builder:
- extracts higher-level signals from candidate items
- supports AI mode generation
- preserves explicit source attribution for each signal:
  - `platform`
  - `source_type`
  - `source_name`
  - `url`

## Digest Layer

Digest Builder:
- renders markdown digests from signals
- enforces a freshness guard
- refuses stale digest rendering when signal artifacts are older than candidate artifacts
- returns a remediation command when freshness fails

## Insight Engine

Insight Engine:
- converts signals into actionable insights
- writes JSONL and Markdown artifacts
- selects editorial briefing output for Telegram delivery

Current editorial style:
- Indonesian output
- concise personal intelligence briefing
- top-priority insight selection
- aha moment generation
- opinionated observations
- ready-to-post content blocks
- weak section suppression

## Telegram Delivery

PAOS can send daily intelligence briefings to Telegram.

Required env vars:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Credential behavior:
- reads from process env first
- falls back to repo `.env` via context loader when available
- does not print secrets to logs

## Common Commands

```bash
# Collect RSS
venv/bin/python runtime/intelligence/jobs/run_rss_collector.py --category ai

# Build candidates
venv/bin/python runtime/intelligence/jobs/run_candidate_pool.py --category ai

# Build signals
venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category ai --mode ai

# Build digest
venv/bin/python runtime/intelligence/jobs/run_digest.py --category ai

# Build insights and send Telegram
venv/bin/python runtime/intelligence/jobs/run_insights.py --category ai
```

## Current Validated State

- Threads + RSS mixed-source pipeline validated
- Candidate Pool source-family loading validated
- Signal attribution validated
- Digest freshness guard validated
- Insight Engine + Telegram delivery validated
- Editorial Telegram UX validated as usable daily briefing

## Documentation

- `docs/architecture.md`
- `docs/intelligence-layer.md`
- `docs/roadmap.md`
- `intelligence/README.md`
