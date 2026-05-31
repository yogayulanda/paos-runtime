import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ASSISTANT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ASSISTANT_DIR.parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from assistant.config import resolve_category


ROOT = ASSISTANT_DIR.parents[1]
ASSISTANT_CONTEXT_DIR = ROOT / "assistant" / "context"
DEFAULT_MAX_CHARS = 12000
CONTRACT_VERSION = "1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print latest PAOS assistant context for external AI tool consumption."
    )
    parser.add_argument("--category")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--section",
        choices=("all", "profile", "memory", "runtime", "intelligence"),
        default="all",
    )
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    return parser.parse_args()


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool, int]:
    if max_chars <= 0:
        return "", bool(text), len(text)
    if len(text) <= max_chars:
        return text, False, 0
    return text[:max_chars], True, len(text) - max_chars


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _bounded_json_output(envelope: dict[str, Any], max_chars: int, source_json_path: Path) -> str:
    full_text = _json_dump(envelope)
    if max_chars <= 0:
        return _json_dump(
            {
                "contract_version": envelope.get("contract_version"),
                "read_only": True,
                "source": envelope.get("source"),
                "request": envelope.get("request"),
                "content": None,
                "truncation": {
                    "truncated": True,
                    "max_chars": max_chars,
                    "omitted_chars": len(full_text),
                    "reason": "max_chars is non-positive",
                    "source_json": str(source_json_path),
                },
            }
        )
    if len(full_text) <= max_chars:
        return full_text

    omitted_chars = len(full_text) - max_chars
    content_json = json.dumps(envelope.get("content"), ensure_ascii=True, indent=2)
    excerpt_budget = max(0, min(len(content_json), max_chars // 2))
    excerpt = content_json[:excerpt_budget]

    truncated_envelope = {
        "contract_version": envelope.get("contract_version"),
        "read_only": True,
        "source": envelope.get("source"),
        "request": envelope.get("request"),
        "content": {
            "truncated": True,
            "excerpt": excerpt,
        },
        "truncation": {
            "truncated": True,
            "max_chars": max_chars,
            "omitted_chars": omitted_chars,
            "source_json": str(source_json_path),
        },
    }

    candidate = _json_dump(truncated_envelope)
    if len(candidate) <= max_chars:
        return candidate

    minimal_envelope = {
        "contract_version": envelope.get("contract_version"),
        "read_only": True,
        "source": envelope.get("source"),
        "request": envelope.get("request"),
        "content": {"truncated": True},
        "truncation": {
            "truncated": True,
            "max_chars": max_chars,
            "omitted_chars": omitted_chars,
            "source_json": str(source_json_path),
        },
    }
    return _json_dump(minimal_envelope)


def _iter_dated_dirs() -> list[Path]:
    if not ASSISTANT_CONTEXT_DIR.exists() or not ASSISTANT_CONTEXT_DIR.is_dir():
        return []

    dirs: list[Path] = []
    for path in ASSISTANT_CONTEXT_DIR.iterdir():
        if not path.is_dir():
            continue
        try:
            datetime.strptime(path.name, "%Y-%m-%d")
        except ValueError:
            continue
        dirs.append(path)
    return sorted(dirs, key=lambda item: item.name, reverse=True)


def _read_context_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _resolve_latest_context_payload(category: str) -> tuple[dict[str, Any], Path, Path, str]:
    latest_any: tuple[dict[str, Any], Path, Path, str] | None = None
    for date_dir in _iter_dated_dirs():
        json_path = date_dir / "assistant-context.json"
        if not json_path.exists():
            continue
        payload = _read_context_json(json_path)
        if payload is None:
            continue

        markdown_path = date_dir / "assistant-context.md"
        candidate = (payload, json_path, markdown_path, date_dir.name)
        if latest_any is None:
            latest_any = candidate

        if str(payload.get("category") or "").strip() == category:
            return candidate

    if latest_any is None:
        raise RuntimeError("No assistant context artifact found under assistant/context/<YYYY-MM-DD>.")

    raise RuntimeError(
        f"No assistant context artifact found for category '{category}'. "
        f"Latest available artifact is dated {latest_any[3]} with category "
        f"'{(latest_any[0].get('category') or 'unknown')}'."
    )


def _section_content(payload: dict[str, Any], section: str) -> dict[str, Any]:
    context = payload.get("context") or {}
    sources = payload.get("sources") or {}
    diagnostics = payload.get("diagnostics") or {}

    profile = {
        "identity": context.get("identity"),
        "working_style": context.get("working_style"),
        "active_projects": context.get("active_projects"),
        "sources": sources.get("repo_context"),
    }
    memory = {
        "temporary_memory": context.get("temporary_memory"),
        "source": sources.get("memory"),
    }
    runtime = {
        "runtime_state": context.get("runtime_state"),
        "source": sources.get("runtime_state"),
    }
    intelligence = {
        "latest_intelligence": context.get("latest_intelligence"),
        "source": sources.get("artifacts"),
    }

    if section == "profile":
        return profile
    if section == "memory":
        return memory
    if section == "runtime":
        return runtime
    if section == "intelligence":
        return intelligence
    return {
        "profile": profile,
        "memory": memory,
        "runtime": runtime,
        "intelligence": intelligence,
        "assistant_guidance": context.get("assistant_guidance"),
        "diagnostics": diagnostics,
    }


def _render_markdown(content: dict[str, Any], section: str) -> str:
    lines = [
        "# PAOS Assistant Context Consumption",
        "",
        f"## Section: {section}",
        "",
        "```json",
        _json_dump(content),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    resolved_category = resolve_category(args.category)

    payload, json_path, markdown_path, source_date = _resolve_latest_context_payload(resolved_category.value)
    selected_content = _section_content(payload, args.section)

    envelope = {
        "contract_version": CONTRACT_VERSION,
        "read_only": True,
        "source": {
            "date": source_date,
            "category": payload.get("category"),
            "generated_at": payload.get("generated_at"),
            "assistant_context_json_path": str(json_path),
            "assistant_context_markdown_path": str(markdown_path) if markdown_path.exists() else None,
        },
        "request": {
            "category": resolved_category.value,
            "category_source": resolved_category.source,
            "format": args.format,
            "section": args.section,
            "max_chars": args.max_chars,
        },
        "content": selected_content,
    }

    if args.format == "json":
        print(_bounded_json_output(envelope, args.max_chars, json_path))
        return
    else:
        source_lines = [
            "# PAOS Assistant Context Consumption",
            "",
            f"- Source Date: `{source_date}`",
            f"- Source Category: `{payload.get('category')}`",
            f"- Source Generated At: `{payload.get('generated_at')}`",
            f"- Source JSON Path: `{json_path}`",
            f"- Source Markdown Path: `{markdown_path if markdown_path.exists() else 'missing'}`",
            f"- Requested Section: `{args.section}`",
            "",
        ]
        body = _render_markdown(selected_content, args.section)
        full_text = "\n".join(source_lines) + body

    truncated_text, truncated, omitted_chars = _truncate_text(full_text, args.max_chars)
    if truncated:
        marker = (
            "\n\n[TRUNCATED] "
            f"output exceeded max-chars={args.max_chars}; omitted_chars={omitted_chars}; "
            f"source_json={json_path}"
        )
        truncated_text = truncated_text + marker

    print(truncated_text)


if __name__ == "__main__":
    main()
