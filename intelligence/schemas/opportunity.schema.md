# Opportunity Schema

Opportunities capture possible uses derived from raw intelligence or digests.

## Location

```text
intelligence/opportunities/YYYY-MM-DD-<topic>.md
```

## Frontmatter

```yaml
id: 2026-05-29-paos-intelligence-opportunity
created_at: 2026-05-29T12:00:00+08:00
type: intelligence_opportunity
status: candidate
derived_from: []
tags: []
```

## Field Notes

* `id` should match the opportunity filename without `.md`.
* `derived_from` can reference digest ids, raw intelligence ids, or file paths.
* `status` starts as `candidate`.
* `tags` is a YAML list.

## Body

```markdown
# Opportunity

# Audience

# Evidence

# Possible Output
```
