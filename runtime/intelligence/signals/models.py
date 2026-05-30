from dataclasses import dataclass
from pathlib import Path


SIGNAL_VERSION = "signals.v1"


@dataclass(frozen=True)
class SignalBuildResult:
    date: str
    category: str
    candidates_loaded: int
    themes_detected: list[str]
    signals_generated: int
    output_path: Path
    generation_mode: str
    fallback_used: bool
    diagnostics: dict
