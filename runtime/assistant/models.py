from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolvedCategory:
    value: str
    source: str


@dataclass(frozen=True)
class AssistantConfig:
    default_category: str | None
    categories: list[str]
    memory: "AssistantMemoryConfig"
    context: "AssistantContextConfig"


@dataclass(frozen=True)
class AssistantMemoryConfig:
    provider: str
    fallback_provider: str
    local_path: Path
    mnemosyne_path: Path
    mnemosyne_endpoint: str | None
    mnemosyne_timeout_seconds: float
    mnemosyne_adapter_mode: str
    mnemosyne_data_dir: Path
    mnemosyne_bank: str
    mnemosyne_session_id: str
    mnemosyne_author_id: str | None
    mnemosyne_author_type: str | None
    mnemosyne_channel_id: str | None
    mnemosyne_strict_healthcheck: bool


@dataclass(frozen=True)
class AssistantContextSectionConfig:
    name: str
    title: str
    files: list[str]


@dataclass(frozen=True)
class AssistantContextConfig:
    repo_sections: list[AssistantContextSectionConfig]
    max_chars_per_file: int
    max_artifact_excerpt_chars: int
    max_memory_items: int
    max_runtime_statuses: int
