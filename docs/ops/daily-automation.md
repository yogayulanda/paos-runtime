# PAOS Daily Automation

Daily run stays simple and local. Telegram remains the primary user-facing surface.

## Manual run (recommended baseline)

```bash
cd /home/ubuntu/paos/paos-runtime
venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai
```

Notes:
- Scheduler/cron/systemd changes are manual and optional.
- Telegram reads existing artifacts; it is not the scheduler process.
- Keep runner process independent from Telegram bot process.

## Optional scheduler examples (manual only)

Cron example:

```cron
30 8 * * * cd /home/ubuntu/paos/paos-runtime && /home/ubuntu/paos/paos-runtime/venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai >> /home/ubuntu/paos/paos-runtime/.runtime/logs/daily-intelligence.log 2>&1
```

Systemd timer sketch (manual deployment if explicitly desired):
- Use `runtime/intelligence/jobs/run_daily_intelligence.py`
- Do not add auto-mutation from PAOS runtime code.

## Phase 10 validation standard

Single readiness runner:

```bash
venv/bin/python runtime/assistant/jobs/validate_commit_readiness.py
```

Expected outputs include:
- host checks using `venv/bin/python`
- Docker MCP smoke status (clear PASS/SKIP/FAIL)
- runtime artifact ignore audit
- final gateway state:
  - `hermes_gateway_status=stopped_expected`
  - `gateway_running=False`

## Gateway operating note

Hermes gateway should stay stopped in normal PAOS operation.
Validation may check status and assert final stopped state. Do not add code that starts/enables gateway.
