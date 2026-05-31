# PAOS Intelligence Artifacts

`intelligence/` stores generated intelligence outputs only.

## Boundary

- `runtime/intelligence/` contains runtime code/config/jobs.
- `intelligence/` contains generated artifacts.

No executable runtime logic should be added under `intelligence/`.

## Category Convention

The output filename is the category.

Current official categories are defined in `runtime/intelligence/config.yaml`:
- `ai`
- `career`

Source families follow these official categories:
- `threads` = trusted account source
- `rss` = trusted feed source
- `keyword` = discovery source

## Structure

```text
intelligence/
├── raw/
│   ├── threads/YYYY-MM-DD/account/<category>.jsonl
│   ├── threads/YYYY-MM-DD/keyword/<category>.jsonl
│   └── rss/YYYY-MM-DD/feed/<category>.jsonl
├── candidates/YYYY-MM-DD/<category>.jsonl
├── signals/YYYY-MM-DD/<category>.jsonl
├── digests/YYYY-MM-DD/<category>.md
└── insights/YYYY-MM-DD/<category>.{jsonl,md}
```

## Threads Auth

Persistent authenticated profile path:

```text
.runtime/browser-profiles/threads/
```

Commands:

```bash
venv/bin/python runtime/intelligence/threads_auth.py login
venv/bin/python runtime/intelligence/threads_auth.py check
venv/bin/python runtime/intelligence/jobs/run_threads_keyword.py --category ai
```

`check` verifies session status with expected profile evidence + auth-cookie indicators.
`login` opens the same persistent browser profile used by collectors and waits until session becomes authenticated.
