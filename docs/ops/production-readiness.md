# PAOS Production Readiness (Phase 10)

Purpose: keep PAOS stable for daily operation without adding major new runtime features.

## Expected operating state

- Primary UX: natural-language chat from Telegram.
- Slash commands: fallback/admin/debug only.
- MCP transport: stdio only (no public API/tunnel).
- Hermes gateway: expected stopped.
- External agent orchestration: draft/manual handoff only (no auto-dispatch).
- Memory write: approval-safe path only for explicit user intent.

## Daily operation

1. Check repo + runtime readiness:

```bash
cd /home/ubuntu/paos/paos-runtime
venv/bin/python runtime/assistant/jobs/validate_commit_readiness.py
```

2. If needed, run daily intelligence:

```bash
venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai
```

3. Use Telegram as primary surface (`/help` for fallback commands).

## Validation before commit

Standard pre-commit safety check:

```bash
venv/bin/python runtime/assistant/jobs/validate_commit_readiness.py
```

Runner validates:
- host interpreter/import health
- git status + ignored audit + diff format
- secret scan + mutation/safety scan
- action-loop and orchestration smokes/e2e
- memory e2e (isolated candidate file)
- source/summary/plan smokes
- Docker MCP smoke (when container available)
- final gateway state (`hermes_gateway_status=stopped_expected`, `gateway_running=False`)

## Runtime artifact policy

Mutable runtime data is local-only and must stay out of commits:

- `assistant/action-loop/*`
- `assistant/agent-orchestration/*`
- `runtime/assistant/memory/runtime/*`
- `runtime/assistant/memory/local.jsonl`
- `runtime/assistant/memory/mnemosyne-data/**`
- `intelligence/raw/**`
- `intelligence/candidates/**`
- `intelligence/signals/**`
- `intelligence/digests/**`
- `intelligence/insights/**`
- `.runtime/**`
- `backups/snapshots/**`

Keep `.gitkeep` only for directory placeholders.

## Backup and restore (manual/local)

Lightweight option:

```bash
venv/bin/python runtime/assistant/jobs/export_runtime_snapshot.py
```

Custom target name:

```bash
venv/bin/python runtime/assistant/jobs/export_runtime_snapshot.py --name before-phase10-fix
```

Rules:
- local backup only (no cloud upload by default)
- snapshot excludes `.env` and secrets files
- backup files must remain git-ignored
- restore must be explicit and manual (never silent overwrite)

Restore example:

```bash
# Example only: inspect snapshot first, then restore selected files.
ls -la backups/snapshots/<snapshot-name>
cp backups/snapshots/<snapshot-name>/assistant/action-loop/actions.jsonl assistant/action-loop/actions.jsonl
```

## Gateway expected state and flapping note

- Hermes gateway is intentionally disabled/stopped for PAOS runtime operation.
- Sometimes container/supervision behavior can make status appear noisy/flapping.
- Validation standard is final state only: gateway must end as stopped.
- New code must not start or enable gateway.

## Troubleshooting

Interpreter mismatch:
- Always run jobs with project interpreter: `venv/bin/python ...`
- Rebuild environment if imports fail:

```bash
bash install.sh
bash doctor.sh
```

Docker MCP smoke fails:
- Confirm Docker daemon available and `paos-hermes` exists:

```bash
docker ps

docker ps -a --filter name=paos-hermes
```

- Ensure container has `/opt/hermes/.venv/bin/python` and mounted repo path.

Hermes gateway flapping/noisy status:
- Check only through runtime wrapper status; do not start gateway.
- If any process unexpectedly starts gateway, stop it and re-run readiness validation.

## Safe commit/push checklist

1. `venv/bin/python runtime/assistant/jobs/validate_commit_readiness.py` passes.
2. No runtime/generated JSONL artifacts are staged.
3. No secret-pattern hit in diff.
4. No forbidden mutation patterns in diff.
5. Gateway final status is stopped.
6. Commit only source/docs/scripts changes.
