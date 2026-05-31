Purpose: define Task 5C GitHub Source Foundation as bounded external intelligence.

Scope:
- Public GitHub source only.
- Read-only collection of configured public repository releases.
- No OAuth/login flow.
- No GitHub App.
- No write actions (no issue/PR creation).
- No private repository crawling.
- No deep full-repo code analysis.

Config:
- Path: `runtime/intelligence/sources/github.yaml`
- Category-scoped repositories under `categories.<category>.repositories`.
- Each repository supports:
  - `repo` (owner/name)
  - `enabled`
  - `source_type` (`release` for MVP)
  - `limit`
  - optional `tags`, `reason`, `name`

Collector:
- Module: `runtime/intelligence/collectors/github/collector.py`
- Job entrypoint: `runtime/intelligence/jobs/run_github_collector.py`
- Uses GitHub public API:
  - `GET /repos/{owner}/{repo}/releases`
- Optional token support through `GITHUB_TOKEN` env var.

Collected item envelope:
- `platform: github`
- `source_type`
- `source_name`
- `category`
- `title`
- `url`
- `created_at` (release publish/create time when available)
- `collected_at`
- `content` (bounded summary/snippet)
- `tags`

Raw output:
- `intelligence/raw/github/YYYY-MM-DD/<category>.jsonl`

Collector status artifact:
- `.runtime/runs/github-collector/latest.json`
- Includes:
  - `status`
  - `started_at`
  - `finished_at`
  - `sources_processed`
  - `items_collected`
  - `warnings`
  - `errors`

Candidate Pool integration:
- Policy: `runtime/intelligence/candidate_pool/policies/github.py`
- Resolver routes all `platform=github` items to GitHub policy.
- Deduplication is URL-first through shared candidate deduper.

Boundary notes:
- GitHub source is external intelligence only.
- Assistant context/durable personal context remains separate.
- This foundation does not modify scheduler behavior or Telegram UX.
