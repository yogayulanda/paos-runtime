import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
ASSISTANT_CONTEXT_DIR = ROOT / "assistant" / "context"


@dataclass(frozen=True)
class AssistantContextArtifact:
    path: str | None
    exists: bool
    date: str | None
    modified_at: str | None
    size_bytes: int | None
    empty: bool | None = None
    parseable: bool | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssistantContextResolution:
    markdown: AssistantContextArtifact
    json: AssistantContextArtifact
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "markdown": self.markdown.to_dict(),
            "json": self.json.to_dict(),
            "warnings": self.warnings,
        }


def _artifact_meta(path: Path | None, *, empty: bool | None = None, parseable: bool | None = None) -> AssistantContextArtifact:
    if path is None:
        return AssistantContextArtifact(
            path=None,
            exists=False,
            date=None,
            modified_at=None,
            size_bytes=None,
            empty=empty,
            parseable=parseable,
        )

    stat = path.stat()
    date_value = None
    try:
        datetime.strptime(path.parent.name, "%Y-%m-%d")
        date_value = path.parent.name
    except ValueError:
        date_value = None
    return AssistantContextArtifact(
        path=str(path),
        exists=True,
        date=date_value,
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        size_bytes=stat.st_size,
        empty=empty,
        parseable=parseable,
    )


def _resolve_latest_context_file(filename: str, local_today: str) -> Path | None:
    today_candidate = ASSISTANT_CONTEXT_DIR / local_today / filename
    if today_candidate.exists():
        return today_candidate

    dated_candidates: list[tuple[str, Path]] = []
    if ASSISTANT_CONTEXT_DIR.exists() and ASSISTANT_CONTEXT_DIR.is_dir():
        for date_dir in ASSISTANT_CONTEXT_DIR.iterdir():
            if not date_dir.is_dir():
                continue
            try:
                datetime.strptime(date_dir.name, "%Y-%m-%d")
            except ValueError:
                continue
            candidate = date_dir / filename
            if candidate.exists():
                dated_candidates.append((date_dir.name, candidate))

    if not dated_candidates:
        return None

    dated_candidates.sort(key=lambda item: item[0], reverse=True)
    return dated_candidates[0][1]


def resolve_latest_assistant_context(local_today: str | None = None) -> AssistantContextResolution:
    today = local_today or datetime.now().astimezone().date().isoformat()
    markdown_path = _resolve_latest_context_file("assistant-context.md", today)
    json_path = _resolve_latest_context_file("assistant-context.json", today)

    warnings: list[str] = []

    markdown_empty = None
    if markdown_path is not None and markdown_path.exists():
        markdown_empty = markdown_path.read_text(encoding="utf-8", errors="ignore").strip() == ""
        if markdown_empty:
            warnings.append(f"assistant context markdown is empty: {markdown_path}")

    json_parseable = None
    if json_path is not None and json_path.exists():
        try:
            json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
            json_parseable = True
        except Exception as exc:
            json_parseable = False
            warnings.append(f"assistant context JSON parse failure: {json_path} ({exc})")

    markdown = _artifact_meta(markdown_path, empty=markdown_empty, parseable=None)
    json_artifact = _artifact_meta(json_path, empty=None, parseable=json_parseable)

    if markdown_path is None:
        warnings.append("assistant context markdown is missing")
    if json_path is None:
        warnings.append("assistant context JSON is missing")

    return AssistantContextResolution(
        markdown=markdown,
        json=json_artifact,
        warnings=warnings,
    )
