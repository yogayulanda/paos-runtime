# PAOS Intelligence

PAOS Intelligence stores captured external signals and derived intelligence artifacts.

This layer is file-based by design.

It does not scrape, call APIs, use a database, or run background workers.

---

## Structure

```text
intelligence/
├── raw/
│   ├── manual/
│   └── threads/
├── digests/
├── opportunities/
└── schemas/
```

---

## Raw Capture

Raw intelligence entries are Markdown files with YAML frontmatter and three body sections:

* Raw Content
* Why It Matters
* Possible Use

Use the collector CLI:

```bash
python runtime/intelligence/collector.py --source manual --text "Signal text"
```
