# PAOS Runtime Specification

## Purpose

PAOS Runtime is the execution layer of PAOS.

PAOS Runtime executes automation, workflows, collectors, digest generation, context loading, memory integration, and user interfaces.

PAOS Runtime is not the source of truth for user knowledge.

---

## Core Principles

1. Runtime and Context are separate.
2. Personal Context is the source of truth.
3. Memory is temporary.
4. Commands remain minimal.
5. Collect once, derive many times.
6. Human-curated knowledge wins over generated knowledge.

---

## Runtime Responsibilities

Runtime is responsible for:

* Telegram bot
* Commands
* Workers
* Collectors
* Digest generation
* Context loading
* Context routing
* Memory adapters
* Health monitoring

Runtime MUST NOT become the source of truth.

---

## Personal Context Responsibilities

Personal Context is responsible for:

* Identity
* Working style
* Current state
* Domains
* Projects
* Long-term knowledge

Personal Context MUST remain human-readable.

---

## Memory Responsibilities

Memory is temporary working memory.

Memory is responsible for:

* Session continuity
* Temporary captures
* Candidate memories
* Cross-tool continuity

Memory MUST NOT replace Personal Context.

---

## Context Contract

Runtime expects:

```text
personal-context/
├── core/
├── domains/
├── workflows/
└── archive/
```

Required:

```text
core/
domains/
workflows/
```

Optional:

```text
archive/
README.md
USER.md
INDEX.md
```

---

## Command Contract

### /profile

Must return:

* identity summary
* working style summary
* current state summary

Must not load archive by default.

---

### /digest

Must execute digest workflow.

Digest may use:

* RSS
* Threads
* X
* Reddit
* News

---

### /ops

Must return runtime health information.

Examples:

* VPS health
* Docker status
* Git status
* Runtime status

---

### /help

Must return command guidance.

---

## Memory Promotion

Promotion flow:

```text
Capture
↓
Memory
↓
Review
↓
Personal Context
↓
Git Commit
```

Only promoted information becomes long-term knowledge.
