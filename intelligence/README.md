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

---

## Threads Auth

PAOS does not store Threads username or password.

Threads login is completed manually in Chromium and the session is saved under:

```text
.runtime/browser-profiles/threads/
```

Use:

```bash
venv/bin/python runtime/intelligence/threads_auth.py login
venv/bin/python runtime/intelligence/threads_auth.py check
```

`check` may return `public_access_only` when Threads pages are reachable without a verified logged-in identity.
