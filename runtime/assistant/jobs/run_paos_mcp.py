import argparse
import sys
from pathlib import Path


ASSISTANT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ASSISTANT_DIR.parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.mcp.server import McpDependencyError, run_stdio_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PAOS MCP server (stdio only).")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio"],
        help="Only stdio transport is supported in Phase 3B.",
    )
    return parser.parse_args()


def main() -> None:
    _ = parse_args()
    try:
        run_stdio_server()
    except McpDependencyError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
