# PAOS Daily Automation (Task 5B)

Manual first-run recommendation:

```bash
cd /home/ubuntu/paos/paos-runtime
venv/bin/python runtime/jobs/run_daily_paos.py --category ai
```

Important notes:
- Cron/systemd install is manual only.
- Telegram commands read latest artifacts only; they do not trigger this pipeline.
- Scheduler should run outside Telegram bot process.
- Runner writes daily status JSON to:
  - `.runtime/runs/daily-paos/latest.json`
  - `.runtime/runs/daily-paos/YYYY-MM-DD.json`

Optional flags:
- `--date YYYY-MM-DD` (passes date to date-aware jobs)
- `--continue-on-collector-warning true|false` (default `true`)
- `--dry-run`
- `--notify-telegram` (reserved/no-op warning in MVP)

Cron example (manual deployment):

```cron
30 8 * * * cd /home/ubuntu/paos/paos-runtime && /home/ubuntu/paos/paos-runtime/venv/bin/python runtime/jobs/run_daily_paos.py --category ai >> logs/daily-paos.log 2>&1
```

Systemd timer sketch (manual deployment):

`/etc/systemd/system/paos-daily.service`
```ini
[Unit]
Description=PAOS Daily Automation Runner

[Service]
Type=oneshot
WorkingDirectory=/home/ubuntu/paos/paos-runtime
ExecStart=/home/ubuntu/paos/paos-runtime/venv/bin/python runtime/jobs/run_daily_paos.py --category ai
```

`/etc/systemd/system/paos-daily.timer`
```ini
[Unit]
Description=Run PAOS daily automation every day at 08:30

[Timer]
OnCalendar=*-*-* 08:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Phase 9 Validation Standard

Gunakan runner tunggal commit-readiness:

`venv/bin/python runtime/assistant/jobs/validate_commit_readiness.py`

Catatan:
- Runner memakai interpreter project venv (`venv/bin/python`) untuk host checks.
- Docker MCP smoke dijalankan lewat container `paos-hermes` dan interpreter `/opt/hermes/.venv/bin/python`.
- Jika Docker/container tidak tersedia, check container ditandai skip jelas (bukan false pass).
- Gateway final harus `hermes_gateway_status=stopped_expected` dan `gateway_running=False`.
