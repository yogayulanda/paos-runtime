from datetime import datetime
from pathlib import Path

from .models import ArtifactMeta, ResolvedArtifacts


ROOT = Path(__file__).resolve().parents[3]
DIGESTS_DIR = ROOT / "intelligence" / "digests"
INSIGHTS_DIR = ROOT / "intelligence" / "insights"
RUNS_DIR = ROOT / ".runtime" / "runs"


def _extract_date_from_path(path: Path) -> str | None:
    if len(path.parts) < 2:
        return None
    candidate = path.parent.name
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except ValueError:
        return None


def _artifact_meta(path: Path | None) -> ArtifactMeta:
    if path is None:
        return ArtifactMeta(
            path=None,
            exists=False,
            date=None,
            modified_at=None,
            size_bytes=None,
        )

    stat = path.stat()
    return ArtifactMeta(
        path=str(path),
        exists=True,
        date=_extract_date_from_path(path),
        modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        size_bytes=stat.st_size,
    )


def _latest_category_file(base_dir: Path, category: str, local_today: str) -> Path | None:
    today_candidate = base_dir / local_today / f"{category}.md"
    if today_candidate.exists():
        return today_candidate

    dated_candidates: list[tuple[str, Path]] = []
    if base_dir.exists() and base_dir.is_dir():
        for date_dir in base_dir.iterdir():
            if not date_dir.is_dir():
                continue
            try:
                datetime.strptime(date_dir.name, "%Y-%m-%d")
            except ValueError:
                continue
            candidate = date_dir / f"{category}.md"
            if candidate.exists():
                dated_candidates.append((date_dir.name, candidate))

    if not dated_candidates:
        return None

    dated_candidates.sort(key=lambda item: item[0], reverse=True)
    return dated_candidates[0][1]


def _resolve_runtime_statuses() -> list[ArtifactMeta]:
    if not RUNS_DIR.exists() or not RUNS_DIR.is_dir():
        return []

    artifacts: list[ArtifactMeta] = []
    for path in sorted(RUNS_DIR.glob("*/latest.json")):
        stat = path.stat()
        artifacts.append(
            ArtifactMeta(
                path=str(path),
                exists=True,
                date=None,
                modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                size_bytes=stat.st_size,
            )
        )
    return artifacts


def resolve_artifacts(category: str, local_today: str | None = None) -> ResolvedArtifacts:
    today = local_today or datetime.now().astimezone().date().isoformat()
    digest_path = _latest_category_file(DIGESTS_DIR, category, today)
    insight_path = _latest_category_file(INSIGHTS_DIR, category, today)

    return ResolvedArtifacts(
        digest=_artifact_meta(digest_path),
        insight=_artifact_meta(insight_path),
        runtime_statuses=_resolve_runtime_statuses(),
    )
