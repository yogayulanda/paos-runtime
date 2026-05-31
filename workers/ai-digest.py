"""Deprecated legacy digest worker.

This worker is intentionally disabled to prevent accidental reuse.
Use the runtime intelligence pipeline instead:
  venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai
"""

import sys


def main():
    message = (
        "workers/ai-digest.py is deprecated and disabled.\n"
        "Use: venv/bin/python runtime/intelligence/jobs/run_daily_intelligence.py --category ai"
    )
    print(message, file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
