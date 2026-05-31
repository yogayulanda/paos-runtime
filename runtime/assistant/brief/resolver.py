import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
ASSISTANT_BRIEF_DIR = ROOT / "assistant" / "briefs"


@dataclass(frozen=True)
class AssistantBriefArtifact:
    path: str | None
    exists: bool
    date: str | None
    modified_at: str | None
    size_bytes: int | None
    empty: bool | None = None
    parseable: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssistantBriefResolution:
    markdown: AssistantBriefArtifact
    json: AssistantBriefArtifact
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "markdown": self.markdown.to_dict(),
            "json": self.json.to_dict(),
            "warnings": self.warnings,
        }


def _artifact_meta(path: Path | None, *, empty: bool | None = None, parseable: bool | None = None) -> AssistantBriefArtifact:
    if path is None:
        return AssistantBriefArtifact(
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

    return AssistantBriefArtifact(
        path=str(path),
        exists=True,
        date=date_value,
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        size_bytes=stat.st_size,
        empty=empty,
        parseable=parseable,
    )


def _resolve_latest_file(filename: str, local_today: str) -> Path | None:
    today_candidate = ASSISTANT_BRIEF_DIR / local_today / filename
    if today_candidate.exists():
        return today_candidate

    candidates: list[tuple[str, Path]] = []
    if ASSISTANT_BRIEF_DIR.exists() and ASSISTANT_BRIEF_DIR.is_dir():
        for date_dir in ASSISTANT_BRIEF_DIR.iterdir():
            if not date_dir.is_dir():
                continue
            try:
                datetime.strptime(date_dir.name, "%Y-%m-%d")
            except ValueError:
                continue
            candidate = date_dir / filename
            if candidate.exists():
                candidates.append((date_dir.name, candidate))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def resolve_latest_assistant_brief(local_today: str | None = None) -> AssistantBriefResolution:
    today = local_today or datetime.now().astimezone().date().isoformat()
    markdown_path = _resolve_latest_file("assistant-brief.md", today)
    json_path = _resolve_latest_file("assistant-brief.json", today)

    warnings: list[str] = []

    markdown_empty = None
    if markdown_path is not None and markdown_path.exists():
        markdown_empty = markdown_path.read_text(encoding="utf-8", errors="ignore").strip() == ""
        if markdown_empty:
            warnings.append(f"assistant brief markdown is empty: {markdown_path}")

    json_empty = None
    json_parseable = None
    if json_path is not None and json_path.exists():
        raw = json_path.read_text(encoding="utf-8", errors="ignore")
        json_empty = raw.strip() == ""
        if json_empty:
            warnings.append(f"assistant brief JSON is empty: {json_path}")
            json_parseable = False
        else:
            try:
                json.loads(raw)
                json_parseable = True
            except Exception as exc:
                json_parseable = False
                warnings.append(f"assistant brief JSON parse failure: {json_path} ({exc})")

    if markdown_path is None:
        warnings.append("assistant brief markdown is missing")
    if json_path is None:
        warnings.append("assistant brief JSON is missing")

    return AssistantBriefResolution(
        markdown=_artifact_meta(markdown_path, empty=markdown_empty, parseable=None),
        json=_artifact_meta(json_path, empty=json_empty, parseable=json_parseable),
        warnings=warnings,
    )
