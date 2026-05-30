from dataclasses import dataclass
from pathlib import Path


INSIGHT_VERSION = "insights.v1"
SUPPORTED_LANGUAGES = {"en", "id"}
SUPPORTED_INSIGHT_TYPES = (
    "learning",
    "tool",
    "project",
    "content",
    "career",
    "market",
)
SUPPORTED_PRIORITIES = ("high", "medium", "low")


@dataclass(frozen=True)
class InsightBuildResult:
    category: str
    date: str
    language: str
    signals_loaded: int
    insights_generated: int
    jsonl_path: Path
    markdown_path: Path
    digest_path: Path
    generation_mode: str
    fallback_used: bool
    type_distribution: dict[str, int]
    diagnostics: dict
