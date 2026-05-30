from dataclasses import dataclass
from pathlib import Path


NORMALIZATION_VERSION = "candidate_pool.v1"


@dataclass(frozen=True)
class CandidatePoolBuildResult:
    date: str
    category: str
    files_loaded: list[Path]
    items_loaded: int
    items_after_normalization: int
    items_after_dedupe: int
    candidates_written: int
    output_path: Path
    diagnostics: dict
