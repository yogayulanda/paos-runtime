from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from assistant.action_loop import create_daily_action, render_daily_action_result  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one daily action draft in local action loop")
    parser.add_argument("--category", default="runtime")
    parser.add_argument("--persist", default="true")
    args = parser.parse_args()
    persist = str(args.persist).strip().lower() in {"1", "true", "yes", "on"}
    result = create_daily_action(category=args.category, persist=persist, actor="job")
    print(render_daily_action_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
