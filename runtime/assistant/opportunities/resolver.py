import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
ASSISTANT_OPPORTUNITIES_DIR = ROOT / "assistant" / "opportunities"


@dataclass(frozen=True)
class AssistantOpportunitiesArtifact:
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
class AssistantOpportunitiesResolution:
    markdown: AssistantOpportunitiesArtifact
    json: AssistantOpportunitiesArtifact
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "markdown": self.markdown.to_dict(),
            "json": self.json.to_dict(),
            "warnings": self.warnings,
        }


def _artifact_meta(path: Path | None, *, empty: bool | None = None, parseable: bool | None = None) -> AssistantOpportunitiesArtifact:
    if path is None:
        return AssistantOpportunitiesArtifact(
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

    return AssistantOpportunitiesArtifact(
        path=str(path),
        exists=True,
        date=date_value,
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        size_bytes=stat.st_size,
        empty=empty,
        parseable=parseable,
    )


def _resolve_latest_file(filename: str, local_today: str) -> Path | None:
    today_candidate = ASSISTANT_OPPORTUNITIES_DIR / local_today / filename
    if today_candidate.exists():
        return today_candidate

    candidates: list[tuple[str, Path]] = []
    if ASSISTANT_OPPORTUNITIES_DIR.exists() and ASSISTANT_OPPORTUNITIES_DIR.is_dir():
        for date_dir in ASSISTANT_OPPORTUNITIES_DIR.iterdir():
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


def resolve_latest_assistant_opportunities(local_today: str | None = None) -> AssistantOpportunitiesResolution:
    today = local_today or datetime.now().astimezone().date().isoformat()
    markdown_path = _resolve_latest_file("opportunities.md", today)
    json_path = _resolve_latest_file("opportunities.json", today)

    warnings: list[str] = []

    markdown_empty = None
    if markdown_path is not None and markdown_path.exists():
        markdown_empty = markdown_path.read_text(encoding="utf-8", errors="ignore").strip() == ""
        if markdown_empty:
            warnings.append(f"assistant opportunities markdown is empty: {markdown_path}")

    json_empty = None
    json_parseable = None
    if json_path is not None and json_path.exists():
        raw = json_path.read_text(encoding="utf-8", errors="ignore")
        json_empty = raw.strip() == ""
        if json_empty:
            warnings.append(f"assistant opportunities JSON is empty: {json_path}")
            json_parseable = False
        else:
            try:
                json.loads(raw)
                json_parseable = True
            except Exception as exc:
                json_parseable = False
                warnings.append(f"assistant opportunities JSON parse failure: {json_path} ({exc})")

    if markdown_path is None:
        warnings.append("assistant opportunities markdown is missing")
    if json_path is None:
        warnings.append("assistant opportunities JSON is missing")

    return AssistantOpportunitiesResolution(
        markdown=_artifact_meta(markdown_path, empty=markdown_empty, parseable=None),
        json=_artifact_meta(json_path, empty=json_empty, parseable=json_parseable),
        warnings=warnings,
    )
