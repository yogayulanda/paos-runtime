from __future__ import annotations

import subprocess
import sys


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip())
    return (proc.stdout or "").strip()


def main() -> int:
    base = ["docker", "exec", "paos-hermes", "sh", "-lc"]

    out = _run(
        base
        + [
            "PYTHONPATH=/workspace/paos-runtime/runtime "
            "/opt/hermes/.venv/bin/python - <<'PY'\n"
            "import yaml, mcp\n"
            "from assistant.mcp.server import create_mcp_server\n"
            "s=create_mcp_server()\n"
            "print('yaml_ok', bool(getattr(yaml, '__version__', '')))\n"
            "print('mcp_ok', bool(mcp))\n"
            "print('server_ok', bool(s))\n"
            "PY"
        ]
    )
    print(out)
    if "yaml_ok True" not in out or "mcp_ok True" not in out or "server_ok True" not in out:
        raise RuntimeError("hermes MCP smoke did not return expected markers")

    print("smoke_hermes_mcp_container: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
