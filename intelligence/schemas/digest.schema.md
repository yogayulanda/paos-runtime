# Digest Schema

Digests summarize related raw intelligence entries.

## Location

```text
intelligence/digests/YYYY-MM-DD.md
```

## Frontmatter

```yaml
id: 2026-05-29
created_at: 2026-05-29T12:00:00+08:00
type: intelligence_digest
generated_from: []
sources: []
tags: []
```

## Field Notes

* `id` should match the digest filename without `.md`.
* `generated_from` references raw intelligence ids or file paths.
* `sources` is a YAML list of source names included in the digest.
* `tags` is a YAML list of aggregated tags.

## Body

```markdown
# Summary

# Signals

# Pattern

# Next Actions
```
