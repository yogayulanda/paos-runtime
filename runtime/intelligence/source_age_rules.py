from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

from config import load_intelligence_config
from config import validate_category


ALLOWED_WHEN_TIME_MISSING = {"skip", "allow_with_warning"}


@dataclass(frozen=True)
class SourceAgeRule:
    max_age_days: int
    when_time_missing: str


@dataclass(frozen=True)
class SourceAgeDecision:
    accepted: bool
    reason: str | None = None


def get_source_age_rule(category, source_family, config=None):
    config = config or load_intelligence_config()
    category = validate_category(category, config=config)
    details = (((config.get("intelligence") or {}).get("categories") or {}).get(category) or {})
    family_rules = (details.get("source_age_rules") or {}).get(source_family) or {}
    if not isinstance(family_rules, dict) or not family_rules:
        return None

    max_age_days = family_rules.get("max_age_days")
    when_time_missing = str(family_rules.get("when_time_missing") or "").strip()
    if max_age_days is None:
        return None
    if when_time_missing not in ALLOWED_WHEN_TIME_MISSING:
        return None
    try:
        max_age_days = int(max_age_days)
    except Exception:
        return None
    if max_age_days < 0:
        return None
    return SourceAgeRule(
        max_age_days=max_age_days,
        when_time_missing=when_time_missing,
    )


def parse_item_time(value):
    text = str(value or "").strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(text)
    except Exception:
        return "invalid"


def evaluate_source_item_age(item_time, rule, now=None):
    if rule is None:
        return SourceAgeDecision(accepted=True, reason=None)

    parsed = parse_item_time(item_time)
    if parsed is None:
        if rule.when_time_missing == "allow_with_warning":
            return SourceAgeDecision(accepted=True, reason="missing_time")
        return SourceAgeDecision(accepted=False, reason="missing_time")
    if parsed == "invalid":
        return SourceAgeDecision(accepted=False, reason="invalid_time")

    now = now or datetime.now().astimezone()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    age_days = (now - parsed).total_seconds() / 86400
    if age_days > rule.max_age_days:
        return SourceAgeDecision(accepted=False, reason="too_old")
    return SourceAgeDecision(accepted=True, reason=None)
