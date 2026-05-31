# Assistant Memory Surface Contract

Purpose: expose a compact, read-only memory snapshot for Telegram `/memory`.

Required sections:
- Memory Provider
- Health / fallback status
- Active Memory
- Recent Progress
- Decisions
- Blockers
- Next Actions
- Promotion Candidates

Rules:
- Must use MemoryProvider abstraction via configured selection.
- Must degrade gracefully when provider is unavailable.
- Must not write memory.
- Must not trigger pipelines.
- If memory is empty, fallback from latest assistant artifacts.
- Output must be deterministic and compact for Telegram.
