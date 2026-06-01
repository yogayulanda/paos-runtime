# Cowork / Non-Repo Agent Guide

Use this when the agent is not running inside PAOS repo.

## Starter prompt

Use PAOS MCP as the source of truth when available.
Find the latest accepted or pending PAOS action.
Inspect relevant context/evidence.
Continue safely.
Do not mutate memory, scheduler, GitHub, repo, or gateway.
If you cannot access PAOS MCP, say so clearly and ask for the smallest context needed.

## Minimal working pattern

1. Check runtime/context: `paos_runtime_status_get`, `paos_context_health_get`
2. Resolve work direction: `paos_action_list`, `paos_action_resolve`, `paos_action_get`
3. If needed: `paos_handoff_get`, `paos_daily_get`, `paos_source_status_get`
4. Never call `paos_memory_write` in normal Telegram/Hermes flow
5. Never execute external apply/write actions

## Phase 9 Quick Rule

- Buat handoff via `paos_agent_handoff_create`.
- Review hasil via `paos_agent_result_review` sebelum tindak lanjut.
- Memory dari hasil agent harus lewat candidate (`paos_agent_memory_candidate_create`) dulu.
