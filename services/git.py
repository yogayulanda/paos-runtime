import subprocess

from context.loader import context_root


def branch() -> str:
    root = context_root()
    return subprocess.getoutput(
        f"cd {root} && git branch --show-current"
    )


def status() -> str:
    root = context_root()
    result = subprocess.getoutput(
        f"cd {root} && git status --short"
    )

    return result if result else "clean"


def pull() -> str:
    root = context_root()
    return subprocess.getoutput(
        f"cd {root} && git pull"
    )