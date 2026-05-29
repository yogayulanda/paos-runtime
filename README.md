# PAOS Runtime

PAOS Runtime is the execution layer for PAOS (Personal AI Operating System).

PAOS Runtime provides:

* Telegram bot interface
* Digest workers
* Collectors
* Context loading
* Memory integration
* Automation workflows

PAOS Runtime is not the source of truth for user knowledge.

User knowledge lives in a separate Personal Context repository.

---

## Architecture

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

## Features

Current:

* /profile
* /digest
* /ops
* /help

Future:

* Threads Collector
* Intelligence Digest
* Mnemosyne Integration
* Natural Language Routing

---

## Quick Start

Clone repository:

```bash
git clone <repo>
cd paos-runtime
```

Install:

```bash
./install.sh
```

Verify:

```bash
./doctor.sh
```

Run:

```bash
venv/bin/python bot/telegram-bot.py
```

---

## Repository Structure

```text
paos-runtime/
├── bot/
├── collectors/
├── context/
├── memory/
├── services/
├── workers/
├── scripts/
├── docs/
├── spec/
├── install.sh
├── doctor.sh
├── requirements.txt
└── README.md
```

---

## Documentation

* spec/runtime-spec.md
* docs/architecture.md
* docs/roadmap.md
