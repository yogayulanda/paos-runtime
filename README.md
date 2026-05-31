# PAOS Runtime

Personal AI runtime, intelligence dashboard, and automation layer.

PAOS Runtime is a lightweight runtime layer for building a personal AI operating workflow. It runs collectors, creates intelligence artifacts, powers a Telegram dashboard, and exposes a practical daily intelligence pipeline for local or self-hosted use.

The stable user-facing path today is the Telegram bot plus the intelligence pipeline.

## Quick Start

`install.sh` creates `venv/`, installs dependencies, creates required runtime directories, and creates `.env` from `.env.example` only when `.env` is missing.

```bash
git clone https://github.com/yogayulanda/paos-runtime.git
cd paos-runtime
bash install.sh
# edit .env if you want Telegram or AI generation
bash doctor.sh
venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai
```

## Current Status

PAOS Runtime is actively evolving.

- Telegram dashboard, RSS source, Threads source, Candidate Pool, Signal Builder, Digest, and Insight pipeline are working.
- `/update` runs the daily intelligence pipeline and sends the final dashboard.
- `/status` reads the latest digest and insight status and warns if insight is stale compared to digest.
- GitHub, LinkedIn, Jobs, and keyword discovery are planned or inactive unless configured and implemented.
- `personal-context` is not automatically read by the current intelligence pipeline.
- Mnemosyne and MCP integration are roadmap/future integration, not required for current runtime usage.

## Minimum Requirements

- Linux, macOS, or a VPS-friendly environment
- Python 3.11+ or Python 3.12 recommended
- Telegram bot token only for Telegram usage
- OpenAI-compatible endpoint only for AI generation mode
- `tmux` optional for VPS operation

## What PAOS Is

PAOS is a personal runtime, a daily intelligence pipeline, a Telegram control surface, and a source-driven intelligence system that produces digest and insight artifacts.

It is designed to stay separate from `personal-context` and from future Mnemosyne working-memory integration.

## What PAOS Is Not

- Not a general-purpose agent OS
- Not a hosted SaaS
- Not a replacement for Claude Code or Codex
- Not a memory database by itself
- Not a fully autonomous agent system yet
- Not a Docker-first runtime
- Not a complete Mnemosyne/MCP implementation yet

## Architecture Overview

```text
PAOS Runtime
      ├── Telegram Bot
      ├── Intelligence Jobs
      ├── RSS Collector
      ├── Threads Collector
      ├── Candidate Pool
      ├── Signal Builder
      ├── Digest Builder
      ├── Insight Engine
      └── Runtime Status
```

`paos-runtime` executes jobs, runs collectors, and produces artifacts.

The current runtime can run without `personal-context`. Future Mnemosyne/MCP work is separate and not required for current usage.

## Feature Stack

- Telegram Dashboard: concise dashboard surface with inline buttons for section details.
- Intelligence Pipeline: runs RSS, Candidate Pool, Signal Builder, Digest, and Insight jobs in sequence.
- Source Collectors: RSS and Threads are active.
- Candidate Pool: normalizes and deduplicates source items before signal extraction.
- Signal Builder: turns candidates into higher-level intelligence signals.
- Digest Builder: renders daily digest artifacts.
- Insight Engine: produces the PAOS Daily Intelligence dashboard artifact.
- Runtime Status: status snapshots are written under `.runtime/runs/`.
- Artifact Storage: generated markdown and JSONL artifacts live under top-level `intelligence/`.
- AI Fallback Handling: AI timeouts should not fail the whole pipeline if fallback synthesis can still generate `ai.md`.
- Contracts and Prompts: dashboard, insight, and content style contracts are externalized in `runtime/intelligence/contracts/` and `runtime/intelligence/prompts/`.

## Current Telegram Commands

- `/help` shows available commands.
- `/status` shows the latest pipeline status and warns when insight is stale relative to digest.
- `/insight` shows the latest PAOS Daily Intelligence dashboard.
- `/update` runs the daily intelligence pipeline and sends progress plus the final dashboard.

Auxiliary commands exist for compatibility and operational checks, but the README keeps the core surface focused on the intelligence workflow.

The Telegram dashboard is concise. `/update` does not spam raw digest content, and Telegram does not display JSONL artifacts directly. Section details open through inline buttons.

## Intelligence Pipeline

```text
RSS / Threads
→ Candidate Pool
→ Signal Builder
→ Digest
→ Insight
→ Telegram Dashboard
```

The runtime writes generated artifacts to:

- `intelligence/raw/`
- `intelligence/candidates/`
- `intelligence/signals/`
- `intelligence/digests/`
- `intelligence/insights/`
- `.runtime/runs/`

`run_daily_intelligence.py` invokes `run_insights.py` so canonical insight status stays fresh in `.runtime/runs/insights/latest.json`.

The Telegram dashboard consumes `intelligence/insights/YYYY-MM-DD/ai.md`.

## Installation

```bash
git clone https://github.com/yogayulanda/paos-runtime.git
cd paos-runtime
bash install.sh
```

Then edit `.env` if you want to use Telegram, AI generation, Threads authentication, or a custom runtime/context path.

```bash
bash doctor.sh
```

`doctor.sh` reports missing optional configuration as warnings, not hard failures. Missing Telegram or AI configuration does not block local setup.

## Configuration

The main runtime configuration lives in:

- `runtime/intelligence/config.yaml`
- `runtime/intelligence/sources/rss.yaml`
- `runtime/intelligence/sources/threads.yaml`
- `runtime/intelligence/sources/keyword.yaml`

Current runtime environment variables:

- `PAOS_RUNTIME_PATH`
- `PAOS_CONTEXT_PATH`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `PAOS_INSIGHT_AI_CONNECT_TIMEOUT_SECONDS`
- `PAOS_INSIGHT_AI_READ_TIMEOUT_SECONDS`

Optional AI override variables used by parts of the intelligence layer:

- `PAOS_AI_PROVIDER`
- `PAOS_AI_BASE_URL`
- `PAOS_AI_API_KEY`
- `PAOS_AI_MODEL`

Optional Threads-related variables:

- `THREADS_ACCESS_TOKEN`
- `THREADS_EXPECTED_USERNAME`

The AI endpoint must be OpenAI-compatible. The current primary runtime path reads the `LLM_*` variables, and the endpoint can point to a local OpenAI-compatible server such as `http://localhost:20128/v1`.

If no working AI endpoint is configured, supported jobs may use fallback behavior where available, but AI-generated signal and insight quality will be lower.

`PAOS_CONTEXT_PATH` is reserved for future context integration direction. The current intelligence pipeline does not automatically read `personal-context` yet.

## Common Commands

```bash
# Full daily intelligence run
venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai

# Run RSS collector
venv/bin/python runtime/intelligence/jobs/run_rss_collector.py --category ai

# Run Threads account collector
venv/bin/python runtime/intelligence/jobs/run_threads_account.py --category ai --timeout-seconds 120

# Run candidate pool
venv/bin/python runtime/intelligence/jobs/run_candidate_pool.py --category ai

# Run signal builder
venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category ai --mode ai

# Run digest
venv/bin/python runtime/intelligence/jobs/run_digest.py --category ai

# Run insights
venv/bin/python runtime/intelligence/jobs/run_insights.py --category ai

# Start Telegram bot
venv/bin/python bot/telegram-bot.py
```

## Running Telegram

Start the bot in a dedicated shell or `tmux` session:

```bash
tmux new -s telegram
venv/bin/python bot/telegram-bot.py
```

Before starting another bot process, confirm that one is not already polling.

Example check:

```bash
ps aux | grep telegram-bot.py
```

`/update` runs the pipeline and sends progress updates, then one final dashboard.

## Contracts and Customization

PAOS externalizes the output contract so you can tune the runtime without editing core Python logic.

- `runtime/intelligence/contracts/dashboard.md`
- `runtime/intelligence/contracts/insight.md`
- `runtime/intelligence/contracts/content-style.md`
- `runtime/intelligence/prompts/insight-system.md`
- `runtime/intelligence/prompts/insight-user.md`

Use these files to change dashboard shape, insight behavior, and content style while keeping the runtime code stable.

## Using PAOS with AI Coding Tools

PAOS Runtime does not replace AI coding tools such as Claude Code, Codex, or GitHub Copilot.

It produces runtime intelligence, context artifacts, and an operational dashboard. Mnemosyne is roadmap work for future working-memory and MCP-facing context exposure to AI coding tools such as Claude Code, Codex, GitHub Copilot, or other MCP-compatible agents. That integration is not implemented as a current runtime requirement.

## Internal Helpers and Legacy Areas

These areas exist in the repository, but they are not the recommended public install path and should not be treated as the main runtime surface:

- `context/loader.py` is an internal helper for loading `.env` and reading selected files from `personal-context`.
- `context/router.py` is legacy and not active runtime code.
- `memory/` is a placeholder for future Mnemosyne-related work.
- `workers/` contains legacy scripts kept for compatibility.
- `scripts/` contains older operational helpers.
- `docker-compose.yml` is experimental/private and not the recommended public install path yet.

## Generated vs Source-Controlled Files

Source-controlled:

- `runtime/`
- `bot/`
- `runtime/intelligence/contracts/`
- `runtime/intelligence/prompts/`
- `runtime/intelligence/config.yaml`
- `runtime/intelligence/sources/*.yaml`
- `install.sh`
- `doctor.sh`

Generated or local:

- `intelligence/raw/`
- `intelligence/candidates/`
- `intelligence/signals/`
- `intelligence/digests/`
- `intelligence/insights/`
- `.runtime/runs/`
- `.env`

`intelligence/` is generated output. `.runtime/runs/` is runtime status. These should usually not be committed.

## Security and Secrets

- Never commit `.env`.
- Never commit Telegram bot tokens.
- Never commit API keys.
- Do not commit `personal-context` data.
- Generated artifacts may contain personal or source-derived data.
- Review artifacts and logs before sharing anything publicly.

## Extending PAOS

- New source family: add the collector/policy/config path for the source and wire it into the category config.
- New category: define it in `runtime/intelligence/config.yaml` and add matching source config where needed.
- New dashboard section: extend the insight contract and renderer, then wire the Telegram section mapping.
- New content style: update the content-style contract and prompts.
- Future MCP integration: keep the runtime separate and expose only selected context or memory through MCP.

## Known Limitations

- Some collectors may require manual or session setup.
- Threads collection may depend on public or authenticated access mode.
- AI quality depends on the configured endpoint and model.
- Fallback insight generation is robust, but less nuanced than successful AI generation.
- GitHub, LinkedIn, and Jobs sources are planned or inactive unless implemented and configured.
- `personal-context` is not automatically read by the current intelligence pipeline.
- Mnemosyne and MCP integration are not implemented as current runtime behavior.

## Roadmap

- RSS freshness filtering
- GitHub source
- LinkedIn source
- Job and career source
- Better content-style tuning
- personal-context reader and prompt injection
- Mnemosyne working-memory integration
- MCP bridge for Claude Code, Codex, GitHub Copilot, and other agents
- Dashboard polish
- Source quality scoring

## Contributing

- Keep runtime and context separate.
- Avoid overengineering.
- Prefer small, testable changes.
- Preserve artifact contracts.
- Do not commit secrets.
- Update README or docs when adding user-facing features.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
