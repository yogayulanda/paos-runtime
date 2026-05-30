from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "runtime" / "intelligence" / "config.yaml"


@dataclass(frozen=True)
class ResolvedCategory:
    value: str
    source: str


def load_intelligence_config():
    if not CONFIG_PATH.exists():
        return {}

    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit("runtime/intelligence/config.yaml must be a mapping.")

    intelligence = payload.get("intelligence") or {}
    if not isinstance(intelligence, dict):
        raise SystemExit("runtime/intelligence/config.yaml must include `intelligence` mapping.")

    categories = intelligence.get("categories") or {}
    if not isinstance(categories, dict) or not categories:
        raise SystemExit(
            "runtime/intelligence/config.yaml must define `intelligence.categories` mapping."
        )

    default_category = str(intelligence.get("default_category") or "").strip()
    if default_category and default_category not in categories:
        allowed = "\n".join(f"- {name}" for name in sorted(categories))
        raise SystemExit(
            "Invalid default category in runtime/intelligence/config.yaml: "
            f"{default_category}\nAllowed categories:\n{allowed}"
        )

    return payload


def get_allowed_categories(config=None):
    config = config or load_intelligence_config()
    categories = ((config.get("intelligence") or {}).get("categories") or {})
    return sorted(categories.keys())


def validate_category(category, config=None):
    category = str(category or "").strip()
    allowed = get_allowed_categories(config=config)
    if category in allowed:
        return category

    allowed_block = "\n".join(f"- {name}" for name in allowed)
    raise SystemExit(
        f"Unknown category: {category}\n"
        f"Allowed categories:\n{allowed_block}"
    )


def resolve_category(cli_category=None, config=None):
    config = config or load_intelligence_config()
    allowed = get_allowed_categories(config=config)

    if cli_category:
        value = validate_category(cli_category, config=config)
        return ResolvedCategory(value=value, source="cli")

    configured_default = str(
        ((config.get("intelligence") or {}).get("default_category") or "")
    ).strip()
    if configured_default:
        value = validate_category(configured_default, config=config)
        return ResolvedCategory(value=value, source="config")

    if "ai" not in allowed:
        allowed_block = "\n".join(f"- {name}" for name in allowed)
        raise SystemExit(
            "No category provided, no default_category configured, and fallback `ai` is not allowed.\n"
            f"Allowed categories:\n{allowed_block}"
        )

    return ResolvedCategory(value="ai", source="fallback")


def validate_source_categories(source_name, source_categories, config=None):
    config = config or load_intelligence_config()
    allowed = set(get_allowed_categories(config=config))
    unknown = sorted(set(source_categories or []) - allowed)
    if not unknown:
        return

    unknown_block = "\n".join(f"- {name}" for name in unknown)
    allowed_block = "\n".join(f"- {name}" for name in sorted(allowed))
    raise SystemExit(
        f"Source config category mismatch in {source_name}. Unknown categories:\n"
        f"{unknown_block}\nAllowed categories:\n{allowed_block}"
    )


def is_source_enabled(category, source_family, config=None):
    config = config or load_intelligence_config()
    category = validate_category(category, config=config)
    details = (((config.get("intelligence") or {}).get("categories") or {}).get(category) or {})
    enabled_sources = details.get("enabled_sources") or []
    if not isinstance(enabled_sources, list):
        return False
    return source_family in {str(value).strip() for value in enabled_sources}
