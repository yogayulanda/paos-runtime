# PAOS Architecture

## High Level

```text
User
 ↓
Telegram
 ↓
PAOS Runtime
 ├── Commands
 ├── Workers
 ├── Collectors
 ├── Memory Adapter
 └── Context Router
          ↓
    Personal Context
```

---

## Runtime + Context

```text
PAOS Runtime
      ↓
PAOS_CONTEXT_PATH
      ↓
Personal Context
```

Runtime contains logic.

Personal Context contains knowledge.

---

## Memory Flow

```text
Telegram
↓
Mnemosyne
↓
Candidate Memory
↓
Review
↓
Personal Context
```

Mnemosyne is working memory.

Personal Context is long-term memory.

---

## Digest Flow

```text
Sources
↓
Collection
↓
Storage
↓
Summary
↓
Analysis
```

Current Sources:

* RSS

Future Sources:

* Threads
* X
* Reddit
* News
* Market Data

---

## Repository Separation

```text
paos-runtime
```

Contains:

* logic
* automation
* workers
* integrations

```text
personal-context
```

Contains:

* identity
* projects
* domains
* knowledge
