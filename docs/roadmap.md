# PAOS Roadmap and Status

## Current status

Completed phases:
- Phase 4: Agentic Draft + Approval Boundary
- Phase 5: Persistent Conversational Action Loop
- Phase 5B: UX Cleanup & External Agent Usability
- Phase 6: Source Intelligence Expansion
- Phase 7: Approval-Safe Memory Layer
- Phase 8: Daily Operating Loop Hardening
- Phase 9: Runtime-Stable External Agent Orchestration

Phase 10:
- Production Hardening & Release Readiness (in progress)

## Current PAOS capabilities

- Natural-language-first Telegram operation.
- Local action-loop (proposed/accepted/rejected/deferred) with safe state transitions.
- Source intelligence pipeline (raw -> candidates -> signals -> digest -> insight).
- Approval-safe memory candidate and approved write flow.
- External agent orchestration as draft/manual handoff and review artifacts.
- MCP read/draft/local-state surfaces over stdio transport.

## Current safety boundaries

- No external apply/write execution path.
- No GitHub mutation path.
- No scheduler/cron/systemd mutation path from runtime.
- No public API/tunnel exposure.
- No Hermes gateway enable/start behavior.
- No silent durable memory writes.

## Optional post-v1 ideas

- Further source quality scoring and ranking tuning.
- Additional compact ops dashboards.
- Optional UX polish where it improves daily clarity.

These are optional and should not weaken current safety/ops boundaries.
