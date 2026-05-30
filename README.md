# PAOS Runtime

PAOS Runtime is the execution layer for personal intelligence workflows.

It is separate from:
- `personal-context` as long-term source of truth
- Mnemosyne as temporary working memory

## Pipeline

```text
Collectors
-> Raw Intelligence Storage
-> Candidate Pool
-> Signal Builder
-> Digest
-> Insight Engine
-> Telegram Delivery
```

## Category Model

`category` = top-level intelligence topic.

Official categories are defined only in:
- `runtime/intelligence/config.yaml`

Current official categories:
- `ai`
- `career`

Category resolution order:
1. CLI `--category`
2. `intelligence.default_category` from `runtime/intelligence/config.yaml`
3. fallback `ai` (only if `ai` is an allowed category)

Unknown categories fail with an explicit allowed list.

## Source Config Model

Sources must follow official categories.

- `runtime/intelligence/sources/threads.yaml`
- `runtime/intelligence/sources/rss.yaml`
- `runtime/intelligence/sources/keyword.yaml`

Source roles:
- `threads` = trusted account source
- `rss` = trusted feed source
- `keyword` = discovery source

Example shape:

```yaml
categories:
  ai:
    accounts: []
  career:
    accounts: []
```

```yaml
categories:
  ai:
    feeds: []
  career:
    feeds: []
```

```yaml
categories:
  ai:
    queries: []
  career:
    queries: []
```

Source files cannot introduce unofficial categories.

## Runtime vs Artifacts

- `runtime/intelligence/` = code, config, jobs, collectors, policies, renderers
- `intelligence/` = generated artifacts only

Current artifact paths keep category in filename:
- `intelligence/raw/threads/YYYY-MM-DD/account/<category>.jsonl`
- `intelligence/raw/rss/YYYY-MM-DD/feed/<category>.jsonl`
- `intelligence/candidates/YYYY-MM-DD/<category>.jsonl`
- `intelligence/signals/YYYY-MM-DD/<category>.jsonl`
- `intelligence/digests/YYYY-MM-DD/<category>.md`
- `intelligence/insights/YYYY-MM-DD/<category>.md`

## Preferred Commands

Use default category:

```bash
venv/bin/python runtime/intelligence/jobs/run_rss_collector.py
venv/bin/python runtime/intelligence/jobs/run_candidate_pool.py
venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --mode ai
venv/bin/python runtime/intelligence/jobs/run_digest.py
venv/bin/python runtime/intelligence/jobs/run_insights.py
```

Override category:

```bash
venv/bin/python runtime/intelligence/jobs/run_insights.py --category career
```

## Safety

Do not commit generated artifacts:
- `intelligence/raw/**`
- `intelligence/candidates/**`
- `intelligence/signals/**`
- `intelligence/digests/**`
- `intelligence/insights/**`
- `.runtime/runs/**`
