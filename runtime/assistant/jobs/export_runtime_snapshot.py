from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_ROOT = ROOT / "backups" / "snapshots"

INCLUDE_PATHS = [
    "assistant/action-loop",
    "assistant/agent-orchestration",
    "runtime/assistant/memory/runtime",
    "runtime/assistant/memory/local.jsonl",
    "intelligence/digests",
    "intelligence/insights",
    ".runtime/runs",
]


def _safe_name(raw: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    cleaned = "".join(ch if ch in allowed else "-" for ch in raw.strip())
    return cleaned.strip("-._") or "snapshot"


def _copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export local PAOS runtime snapshot (manual backup).")
    parser.add_argument("--name", default="", help="Optional snapshot suffix, e.g. before-upgrade")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = _safe_name(args.name) if args.name else ""
    snapshot_name = f"{stamp}-{suffix}" if suffix else stamp
    target = SNAPSHOT_ROOT / snapshot_name
    target.mkdir(parents=True, exist_ok=False)

    copied = 0
    for rel in INCLUDE_PATHS:
        src = ROOT / rel
        if not src.exists():
            continue
        _copy(src, target / rel)
        copied += 1

    print(f"snapshot_path={target}")
    print(f"entries_copied={copied}")
    print("note=manual restore only; review files before overwriting local runtime state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
