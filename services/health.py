import subprocess


def uptime() -> str:
    return subprocess.getoutput("uptime -p")


def ram_usage() -> str:
    return subprocess.getoutput(
        "free -h | awk '/Mem:/ {print $3 \"/\" $2}'"
    )


def disk_usage() -> str:
    return subprocess.getoutput(
        "df -h / | awk 'NR==2 {print $3 \"/\" $2 \" (\" $5 \")\"}'"
    )