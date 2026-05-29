from pathlib import Path


def load_env(env_path: str | None = None) -> dict[str, str]:
    if env_path is None:
        env_path = "/home/ubuntu/paos/paos-runtime/.env"

    env = {}

    with open(env_path) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            env[key] = value

    return env


def context_root() -> Path:
    env = load_env()
    return Path(env["PAOS_CONTEXT_PATH"])


def read_context_file(relative_path: str, max_chars: int = 4000) -> str:
    root = context_root()
    path = root / relative_path

    if not path.exists():
        return ""

    return path.read_text(errors="ignore")[:max_chars]


def read_profile_context() -> str:
    files = [
        "USER.md",
        "core/identity.md",
        "core/working-style.md",
        "core/current-state.md",
    ]

    parts = []

    for file in files:
        content = read_context_file(file)
        if content:
            parts.append(f"# {file}\n\n{content}")

    return "\n\n---\n\n".join(parts)