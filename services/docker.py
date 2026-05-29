import subprocess


def container_status() -> str:
    result = subprocess.getoutput(
        "docker ps --format '📦 {{.Names}} → {{.Status}}'"
    )

    return result if result else "No running containers"


def container_count() -> str:
    return subprocess.getoutput(
        "docker ps --format '{{.Names}}' | wc -l"
    )