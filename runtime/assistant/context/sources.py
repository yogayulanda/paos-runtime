import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from assistant.artifacts import resolve_artifacts
from assistant.config import load_assistant_config
from assistant.memory import MemoryQuery, load_memory_provider


ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT / ".runtime" / "runs"
ENV_PATH = ROOT / ".env"


@dataclass(frozen=True)
class RepoContextFileSource:
    path: str
    exists: bool
    modified_at: str | None
    size_bytes: int | None
    content: str
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepoContextSectionSource:
    name: str
    title: str
    files: list[RepoContextFileSource] = field(default_factory=list)
    content: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "files": [file.to_dict() for file in self.files],
            "content": self.content,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class ArtifactSource:
    name: str
    path: str | None
    exists: bool
    date: str | None
    modified_at: str | None
    size_bytes: int | None
    excerpt: str
    truncated: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeStatusSource:
    path: str
    job: str | None
    status: str | None
    category: str | None
    category_source: str | None
    generated_at: str | None
    modified_at: str | None
    size_bytes: int | None
    summary: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemorySource:
    provider: dict[str, Any]
    items: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text.strip(), False
    return text[:max_chars].rstrip() + "\n\n[truncated]", True


def _truncate_content(value: str, max_chars: int = 600) -> str:
    text, _ = _truncate_text(value, max_chars)
    return text


def _read_text(path: Path, max_chars: int) -> tuple[str, bool]:
    if not path.exists() or not path.is_file():
        return "", False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return _truncate_text(text, max_chars)


def _load_env_value(key: str) -> str | None:
    env_value = os.getenv(key)
    if env_value:
        return env_value

    if not ENV_PATH.exists():
        return None

    for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, current_value = line.split("=", 1)
        if current_key.strip() == key:
            return current_value.strip()
    return None


def _load_repo_context_root() -> Path:
    path_value = _load_env_value("PAOS_CONTEXT_PATH")
    if not path_value:
        raise RuntimeError("PAOS_CONTEXT_PATH is not configured in .env or the environment.")
    return Path(path_value).expanduser()


def _file_source(root: Path, relative_path: str, max_chars: int) -> RepoContextFileSource:
    path = root / relative_path
    if not path.exists():
        return RepoContextFileSource(
            path=str(path),
            exists=False,
            modified_at=None,
            size_bytes=None,
            content="",
            truncated=False,
        )

    stat = path.stat()
    content, truncated = _read_text(path, max_chars)
    return RepoContextFileSource(
        path=str(path),
        exists=True,
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        size_bytes=stat.st_size,
        content=content,
        truncated=truncated,
    )


def load_repo_context_sources() -> tuple[list[RepoContextSectionSource], list[str]]:
    config = load_assistant_config()
    warnings: list[str] = []

    try:
        root = _load_repo_context_root()
    except Exception as exc:
        return [], [f"repo_context_root_unavailable: {exc}"]

    if not root.exists() or not root.is_dir():
        return [], [f"repo_context_root_missing: {root}"]

    sections: list[RepoContextSectionSource] = []
    for section in config.context.repo_sections:
        files: list[RepoContextFileSource] = []
        file_chunks: list[str] = []
        section_warnings: list[str] = []
        for relative_path in section.files:
            file_source = _file_source(root, relative_path, config.context.max_chars_per_file)
            files.append(file_source)
            if not file_source.exists:
                section_warnings.append(f"missing repo context file: {relative_path}")
                continue
            if file_source.content:
                file_chunks.append(f"### {relative_path}\n\n{file_source.content}")

        content = "\n\n---\n\n".join(file_chunks).strip()
        if not content:
            section_warnings.append(f"no content available for section: {section.name}")

        sections.append(
            RepoContextSectionSource(
                name=section.name,
                title=section.title,
                files=files,
                content=content,
                warnings=section_warnings,
            )
        )
        warnings.extend(section_warnings)

    return sections, warnings


def load_latest_artifact_sources(category: str) -> tuple[dict[str, ArtifactSource], list[str]]:
    config = load_assistant_config()
    artifacts = resolve_artifacts(category=category)
    warnings: list[str] = []
    result: dict[str, ArtifactSource] = {}

    for name, metadata in (("digest", artifacts.digest), ("insight", artifacts.insight)):
        path = Path(metadata.path) if metadata.path else None
        excerpt = ""
        truncated = False
        item_warnings: list[str] = []

        if not metadata.exists:
            item_warnings.append(f"latest {name} artifact missing")
        elif path is not None:
            try:
                excerpt, truncated = _read_text(path, config.context.max_artifact_excerpt_chars)
            except OSError as exc:
                item_warnings.append(f"failed to read latest {name} artifact: {exc}")
        result[name] = ArtifactSource(
            name=name,
            path=metadata.path,
            exists=metadata.exists,
            date=metadata.date,
            modified_at=metadata.modified_at,
            size_bytes=metadata.size_bytes,
            excerpt=excerpt,
            truncated=truncated,
            warnings=item_warnings,
        )
        warnings.extend(item_warnings)

    return result, warnings


def load_runtime_status_sources(limit: int) -> tuple[list[RuntimeStatusSource], list[str]]:
    if not RUNS_DIR.exists() or not RUNS_DIR.is_dir():
        return [], [f"runtime_status_directory_missing: {RUNS_DIR}"]

    items: list[RuntimeStatusSource] = []
    warnings: list[str] = []
    ordered_paths: list[tuple[float, Path]] = []
    for path in RUNS_DIR.glob("*/latest.json"):
        try:
            ordered_paths.append((path.stat().st_mtime, path))
        except OSError as exc:
            warnings.append(f"runtime status stat failure for {path}: {exc}")
    paths = [path for _, path in sorted(ordered_paths, key=lambda item: item[0], reverse=True)]

    for path in paths:
        if len(items) >= max(0, limit):
            break
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            warnings.append(f"runtime status parse failure for {path}: {exc}")
            continue

        if not isinstance(payload, dict):
            warnings.append(f"runtime status payload is not a mapping: {path}")
            continue

        stat = path.stat()
        job = payload.get("job")
        status = payload.get("status")
        category = payload.get("category")
        category_source = payload.get("category_source")
        generated_at = payload.get("generated_at") or payload.get("finished_at")
        summary = f"{job or path.parent.name}: {status or 'unknown'}"
        if category:
            summary += f" ({category})"
        compact_payload = {
            key: payload.get(key)
            for key in (
                "job",
                "status",
                "category",
                "category_source",
                "started_at",
                "finished_at",
                "generated_at",
                "error_message",
                "duration_seconds",
                "output_path",
                "digest_path",
                "insight_path",
                "markdown_path",
                "json_path",
            )
            if payload.get(key) is not None
        }

        items.append(
            RuntimeStatusSource(
                path=str(path),
                job=str(job) if job is not None else None,
                status=str(status) if status is not None else None,
                category=str(category) if category is not None else None,
                category_source=str(category_source) if category_source is not None else None,
                generated_at=str(generated_at) if generated_at is not None else None,
                modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                size_bytes=stat.st_size,
                summary=summary,
                payload=compact_payload,
            )
        )

    return items, warnings


def load_memory_sources(category: str, limit: int) -> tuple[MemorySource, list[str]]:
    warnings: list[str] = []
    selection = load_memory_provider()
    query = MemoryQuery(text="", scope=category, limit=limit)

    try:
        items = selection.provider.recall(query)
    except Exception as exc:
        warnings.append(f"memory recall failed for {selection.active_provider}: {exc}")
        items = []

    result_items: list[dict[str, Any]] = []
    for item in items[: max(0, limit)]:
        result_items.append(
            {
                "id": item.id,
                "content": _truncate_content(item.content),
                "scope": item.scope,
                "created_at": item.created_at,
                "source": item.source,
                "metadata": item.metadata,
            }
        )

    if selection.fallback_used or not selection.configured_health.healthy:
        warnings.append(
            f"memory provider fallback used: {selection.configured_provider} -> {selection.active_provider}"
        )
    if not selection.active_health.healthy:
        warnings.append(
            f"memory provider unavailable: {selection.active_provider} - {selection.active_health.message}"
        )

    return MemorySource(provider=selection.to_dict(), items=result_items, warnings=warnings), warnings
