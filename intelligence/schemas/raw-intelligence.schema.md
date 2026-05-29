# Raw Intelligence Schema

Raw intelligence captures external signals before interpretation.

## Location

```text
intelligence/raw/<source>/YYYY-MM-DD-HHMMSS-<source>.md
```

## Supported Sources

* manual
* threads

## Frontmatter

```yaml
id: 2026-05-29-120000-manual
source: manual
captured_at: 2026-05-29T12:00:00+08:00
type: raw_intelligence
author: ""
url: ""
tags: []
signal_strength: unreviewed
promotion_status: raw
```

## Body

```markdown
# Raw Content

# Why It Matters

# Possible Use
```

## Field Notes

* `id` should match the filename without `.md`.
* `source` must be `manual` or `threads`.
* `captured_at` is an ISO 8601 timestamp.
* `tags` is a YAML list.
* `signal_strength` starts as `unreviewed`.
* `promotion_status` starts as `raw`.
