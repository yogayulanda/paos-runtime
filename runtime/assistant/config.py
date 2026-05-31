from pathlib import Path

import yaml

from .models import (
    AssistantConfig,
    AssistantContextConfig,
    AssistantContextSectionConfig,
    AssistantMemoryConfig,
    ResolvedCategory,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "runtime" / "assistant" / "config.yaml"


def _load_raw_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit("runtime/assistant/config.yaml is missing.")

    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit("runtime/assistant/config.yaml must be a mapping.")

    assistant = payload.get("assistant") or {}
    if not isinstance(assistant, dict):
        raise SystemExit("runtime/assistant/config.yaml must include `assistant` mapping.")

    categories = assistant.get("categories") or {}
    if not isinstance(categories, dict) or not categories:
        raise SystemExit(
            "runtime/assistant/config.yaml must define `assistant.categories` mapping."
        )

    default_category = str(assistant.get("default_category") or "").strip()
    if default_category and default_category not in categories:
        allowed = "\n".join(f"- {name}" for name in sorted(categories))
        raise SystemExit(
            "Invalid default category in runtime/assistant/config.yaml: "
            f"{default_category}\nAllowed categories:\n{allowed}"
        )

    return payload


def load_assistant_config() -> AssistantConfig:
    payload = _load_raw_config()
    assistant = payload.get("assistant") or {}
    categories = sorted((assistant.get("categories") or {}).keys())
    default_value = str(assistant.get("default_category") or "").strip() or None

    memory = assistant.get("memory") or {}
    if not isinstance(memory, dict):
        raise SystemExit("runtime/assistant/config.yaml `assistant.memory` must be a mapping.")

    context = assistant.get("context") or {}
    if not isinstance(context, dict):
        raise SystemExit("runtime/assistant/config.yaml `assistant.context` must be a mapping.")

    provider = str(memory.get("provider") or "local").strip() or "local"
    fallback_provider = str(memory.get("fallback_provider") or "local").strip() or "local"

    local_path = Path(
        str(
            ((memory.get("local") or {}).get("path") or "runtime/assistant/memory/local.jsonl")
        )
    )
    mnemosyne_path = Path(
        str(
            (
                (memory.get("mnemosyne") or {}).get("path")
                or "runtime/assistant/memory/mnemosyne.jsonl"
            )
        )
    )
    mnemosyne_endpoint = str((memory.get("mnemosyne") or {}).get("endpoint") or "").strip() or None
    mnemosyne_timeout_seconds = float((memory.get("mnemosyne") or {}).get("timeout_seconds") or 2.0)

    repo_sections_raw = context.get("repo_sections") or []
    if not isinstance(repo_sections_raw, list) or not repo_sections_raw:
        raise SystemExit(
            "runtime/assistant/config.yaml `assistant.context.repo_sections` must be a non-empty list."
        )

    repo_sections: list[AssistantContextSectionConfig] = []
    for entry in repo_sections_raw:
        if not isinstance(entry, dict):
            raise SystemExit(
                "runtime/assistant/config.yaml `assistant.context.repo_sections` entries must be mappings."
            )
        name = str(entry.get("name") or "").strip()
        title = str(entry.get("title") or "").strip()
        files = entry.get("files") or []
        if not name or not title or not isinstance(files, list) or not files:
            raise SystemExit(
                "runtime/assistant/config.yaml `assistant.context.repo_sections` entries must define "
                "`name`, `title`, and non-empty `files`."
            )
        repo_sections.append(
            AssistantContextSectionConfig(
                name=name,
                title=title,
                files=[str(value).strip() for value in files if str(value).strip()],
            )
        )
        if not repo_sections[-1].files:
            raise SystemExit(
                "runtime/assistant/config.yaml `assistant.context.repo_sections` entries must include at least one non-empty file path."
            )

    max_chars_per_file = int(context.get("max_chars_per_file") or 2400)
    max_artifact_excerpt_chars = int(context.get("max_artifact_excerpt_chars") or 1600)
    max_memory_items = int(context.get("max_memory_items") or 8)
    max_runtime_statuses = int(context.get("max_runtime_statuses") or 10)

    def resolve_path(path: Path) -> Path:
        return path if path.is_absolute() else ROOT / path

    return AssistantConfig(
        default_category=default_value,
        categories=categories,
        memory=AssistantMemoryConfig(
            provider=provider,
            fallback_provider=fallback_provider,
            local_path=resolve_path(local_path),
            mnemosyne_path=resolve_path(mnemosyne_path),
            mnemosyne_endpoint=mnemosyne_endpoint,
            mnemosyne_timeout_seconds=mnemosyne_timeout_seconds,
        ),
        context=AssistantContextConfig(
            repo_sections=repo_sections,
            max_chars_per_file=max_chars_per_file,
            max_artifact_excerpt_chars=max_artifact_excerpt_chars,
            max_memory_items=max_memory_items,
            max_runtime_statuses=max_runtime_statuses,
        ),
    )


def validate_category(category: str, config: AssistantConfig | None = None) -> str:
    config = config or load_assistant_config()
    category = str(category or "").strip()
    if category in config.categories:
        return category

    allowed = "\n".join(f"- {name}" for name in config.categories)
    raise SystemExit(f"Unknown category: {category}\nAllowed categories:\n{allowed}")


def resolve_category(cli_category: str | None = None) -> ResolvedCategory:
    config = load_assistant_config()

    if cli_category:
        value = validate_category(cli_category, config=config)
        return ResolvedCategory(value=value, source="cli")

    if config.default_category:
        value = validate_category(config.default_category, config=config)
        return ResolvedCategory(value=value, source="config")

    if "ai" in config.categories:
        return ResolvedCategory(value="ai", source="fallback")

    allowed = "\n".join(f"- {name}" for name in config.categories)
    raise SystemExit(
        "No category provided, no default_category configured, and fallback `ai` is not allowed.\n"
        f"Allowed categories:\n{allowed}"
    )
