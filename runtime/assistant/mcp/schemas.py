import json

MAX_CONTENT_CHARS = 8000
MAX_METADATA_BYTES = 8192
DEFAULT_RECALL_LIMIT = 10
MAX_RECALL_LIMIT = 50
DEFAULT_CONTEXT_MAX_CHARS = 12000
MIN_CONTEXT_MAX_CHARS = 200
MAX_CONTEXT_MAX_CHARS = 50000

CONTEXT_FORMATS = {"json", "markdown"}
CONTEXT_SECTIONS = {"all", "profile", "memory", "runtime", "intelligence"}


def clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, int(value)))


def validate_content(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        raise ValueError("content is required and must be non-empty")
    if len(text) > MAX_CONTENT_CHARS:
        raise ValueError(f"content exceeds max length ({MAX_CONTENT_CHARS})")
    return text


def validate_metadata(metadata) -> dict:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    raw = json.dumps(metadata, ensure_ascii=True)
    if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError(f"metadata exceeds max serialized size ({MAX_METADATA_BYTES} bytes)")
    return metadata


def normalize_context_params(fmt: str, section: str, max_chars: int):
    out_format = str(fmt or "json").strip().lower()
    out_section = str(section or "all").strip().lower()
    if out_format not in CONTEXT_FORMATS:
        raise ValueError(f"invalid format: {out_format}")
    if out_section not in CONTEXT_SECTIONS:
        raise ValueError(f"invalid section: {out_section}")
    bounded = clamp_int(int(max_chars), MIN_CONTEXT_MAX_CHARS, MAX_CONTEXT_MAX_CHARS)
    return out_format, out_section, bounded
