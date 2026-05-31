# Claude Code Adapter Guide

## 1) SSH alias

Add to `~/.ssh/config` on WSL/PC:

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

## 2) Register MCP server

```bash
claude mcp add paos --scope user -- ssh paos-vps 'cd /home/ubuntu/paos/paos-runtime && exec venv/bin/python runtime/assistant/jobs/run_paos_mcp.py'
claude mcp list
```

If project-level config conflicts, remove duplicate `paos` entries or use one scope only.

## 3) MCP smoke tests

- `paos_health` args: `{"category":"ai","include_diagnostics":false}`
- `paos_memory_write` args: `{"content":"PAOS MCP Claude test.","category":"ai"}`
- `paos_memory_recall` args: `{"query":"PAOS MCP Claude test","category":"ai","limit":5}`
- `paos_context_get` args: `{"category":"ai","section":"memory","format":"json","max_chars":2400}`

Expected:

- `ok=true`
- structured `warnings`/`errors` arrays
- memory provider metadata in responses

## 4) Troubleshooting

- Startup/initialize failure: rerun `claude mcp list` and direct SSH command above.
- SSH password prompts: key auth not configured; fix SSH config/agent.
- `fallback_used=true`: configured provider unhealthy; inspect `configured_health` in `paos_health`.
- Mnemosyne missing: install on VPS venv: `venv/bin/python -m pip install "mnemosyne-memory==3.1.2"`.
