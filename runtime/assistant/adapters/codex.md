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
- `paos_memory_write` args: `{"content":"PAOS MCP Codex test.","category":"ai"}`
- `paos_memory_recall` args: `{"query":"PAOS MCP Codex test","category":"ai","limit":5}`
- `paos_context_get` args: `{"category":"ai","section":"memory","format":"json","max_chars":2400}`

Expected:

- `ok=true`
- provider metadata included
- recall returns written item

## 4) Troubleshooting

- No MCP tools visible: verify TOML quoting and restart Codex.
- SSH password prompt: key auth not set.
- MCP call errors: run remote command directly via SSH and inspect stderr.
- `fallback_used=true`: provider fallback engaged; inspect `configured_health`.

Note: exact Codex UI wiring may vary by version; command pattern above is the stable requirement.
