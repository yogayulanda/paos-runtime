import subprocess
from pathlib import Path

from context.loader import load_env
from services.health import uptime, ram_usage, disk_usage
from services.docker import container_status


def _runtime_path() -> Path:
    env = load_env()
    return Path(env.get("PAOS_RUNTIME_PATH", "/home/ubuntu/paos/paos-runtime"))


def _runtime_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(_runtime_path()),
            capture_output=True,
            text=True,
            check=False,
        )
        branch_name = (result.stdout or "").strip()
        if branch_name:
            return branch_name
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            return f"error ({err or 'git branch failed'})"
        return "unknown"
    except Exception as exc:
        return f"error ({exc})"


def _runtime_status() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(_runtime_path()),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            return f"error ({err or 'git status failed'})"
        output = (result.stdout or "").strip()
        return output if output else "clean"
    except Exception as exc:
        return f"error ({exc})"


async def handle_ops(update):
    runtime_branch = _runtime_branch()
    git_status = _runtime_status()
    message = f"""
🟢 PAOS Operations

⏱ Uptime:
{uptime()}

🧠 RAM:
{ram_usage()}

💾 Disk:
{disk_usage()}

🐳 Docker:
{container_status()}

🌿 Git:
Branch: {runtime_branch}
Status: {git_status}
"""

    await update.message.reply_text(message[:4000])
