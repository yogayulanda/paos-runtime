# Codex Adapter Guide

## 1) SSH alias

Configure `~/.ssh/config` on WSL/PC:

```sshconfig
Host paos-vps
  HostName <VPS_IP_OR_HOST>
  User ubuntu
  IdentityFile ~/.ssh/<your_key>
  IdentitiesOnly yes
```

Validate:

```bash
ssh paos-vps 'echo ok'
ssh paos-vps 'cd /home/ubuntu/paos/paos-runtime && venv/bin/python runtime/assistant/jobs/run_paos_mcp.py --help'
```

## 2) Codex MCP config

Add in `~/.codex/config.toml`:

```toml
[mcp_servers.paos]
command = "ssh"
args = [
  "paos-vps",
  "cd /home/ubuntu/paos/paos-runtime && exec venv/bin/python runtime/assistant/jobs/run_paos_mcp.py"
]
```

Restart Codex session after config changes.

## 3) MCP smoke tests

- `paos_health` args: `{"category":"ai","include_diagnostics":false}`
- `paos_memory_recall` args: `{"query":"latest progress","category":"ai","limit":5}`
- `paos_context_get` args: `{"category":"ai","section":"memory","format":"json","max_chars":2400}`
- `paos_action_list` args: `{"limit":5}`
- `paos_action_resolve` args: `{"reference":"action terakhir"}`

Expected:

- `ok=true`
- provider metadata included
- action-loop tools return resolvable local action context

## 4) Troubleshooting

- No MCP tools visible: verify TOML quoting and restart Codex.
- SSH password prompt: key auth not set.
- MCP call errors: run remote command directly via SSH and inspect stderr.
- `fallback_used=true`: provider fallback engaged; inspect `configured_health`.

Note: exact Codex UI wiring may vary by version; command pattern above is the stable requirement.

## Phase 5B Safe-Use Notes

- Use PAOS MCP as source of truth when available.
- Prefer action-loop tools (`paos_action_list`, `paos_action_resolve`, `paos_action_get`) before coding.
- Do not request manual context paste when MCP can supply it.
- Do not invoke `paos_memory_write` in normal Telegram/Hermes workflows.
- Do not mutate scheduler, GitHub, repo, or gateway.

## Phase 9 External-Agent Orchestration

- Prefer handoff/review surfaces:
  - `paos_agent_handoff_create`
  - `paos_agent_result_review`
  - `paos_agent_next_action_draft`
  - `paos_agent_memory_candidate_create`
- Handoff is draft/manual prompt only (handoff != execution).
- Accepted action is direction only (accepted != executed).
- No commit/push/PR/issue unless explicitly requested.
