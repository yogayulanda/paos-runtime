import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
import yaml


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from digest.loader import load_signals
from digest.loader import resolve_date
from digest.loader import signal_path
from insights.models import INSIGHT_VERSION
from insights.models import InsightBuildResult
from insights.models import SUPPORTED_INSIGHT_TYPES
from insights.models import SUPPORTED_LANGUAGES
from insights.models import SUPPORTED_PRIORITIES
from insights.renderer import render_insights
from signals.ai_generator import ai_available
from signals.ai_generator import env_config
from signals.ai_generator import parse_response_content
from signals.ai_generator import resolve_endpoint


ROOT = INTELLIGENCE_DIR.parents[1]
CONFIG_PATH = ROOT / "runtime" / "intelligence" / "config.yaml"
INSIGHTS_DIR = ROOT / "intelligence" / "insights"
DIGESTS_DIR = ROOT / "intelligence" / "digests"
DEFAULT_TIMEOUT_SECONDS = 60


COPY = {
    "en": {
        "header": "Daily Insights",
        "reason": "Why this deserves attention today",
        "fallback_reason": "This insight is derived from a strong signal cluster and should be reviewed today.",
    },
    "id": {
        "header": "Insight Harian",
        "reason": "Alasan insight ini perlu diperhatikan hari ini",
        "fallback_reason": "Insight ini berasal dari klaster sinyal yang kuat dan layak ditinjau hari ini.",
    },
}


class InsightFreshnessError(RuntimeError):
    pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build PAOS daily insights from intelligence signals."
    )
    parser.add_argument("--category", required=True)
    parser.add_argument("--date", default="today")
    parser.add_argument(
        "--mode",
        choices=["auto", "ai", "heuristic"],
        default="auto",
    )
    return parser.parse_args()


def compact_text(value):
    return " ".join(str(value or "").split())


def digest_path(date, category):
    return DIGESTS_DIR / resolve_date(date) / f"{category}.md"


def output_jsonl_path(date, category):
    return INSIGHTS_DIR / date / f"{category}.jsonl"


def output_markdown_path(date, category):
    return INSIGHTS_DIR / date / f"{category}.md"


def load_runtime_config():
    if not CONFIG_PATH.exists():
        return {}
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def resolve_language(config=None):
    config = config or load_runtime_config()
    language = compact_text(((config.get("insights") or {}).get("language"))).lower()
    if language in SUPPORTED_LANGUAGES:
        return language
    return "en"


def validate_digest_freshness(date, category):
    signal_file = signal_path(date=date, category=category)
    rendered_digest = digest_path(date=date, category=category)

    if not signal_file.exists():
        raise InsightFreshnessError(
            "Signal output is missing. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )

    if not rendered_digest.exists():
        raise InsightFreshnessError(
            "Digest output is missing. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_digest.py --category {category}"
        )

    if rendered_digest.stat().st_mtime < signal_file.stat().st_mtime:
        raise InsightFreshnessError(
            "Digest output is stale relative to signals. "
            f"digest={rendered_digest} signal={signal_file}. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_digest.py --category {category}"
        )

    return signal_file, rendered_digest


def write_jsonl(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")


def write_markdown(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_messages(category, language, signals):
    language_name = "Indonesian" if language == "id" else "English"
    system = (
        "You are generating PAOS daily insights from existing intelligence signals.\n"
        "Return strict JSON only.\n"
        "Convert signals into actionable personal intelligence that answers: what should I pay attention to today?\n"
        "Prioritize personal actionability: what should the user study, evaluate, build, publish, monitor, or leverage today?\n"
        "Prefer personally actionable interpretations over broad strategic commentary.\n"
        f"Write all user-facing text in {language_name}.\n"
        "Do not create tasks, schedules, automations, memory updates, or personal-context changes.\n"
        "Do not invent facts beyond the source signals.\n"
        "Use concise, high-signal titles.\n"
        "Only cite signal titles that exist in the input."
    )
    user = {
        "category": category,
        "language": language,
        "instructions": {
            "required_output_schema": {
                "insights": [
                    {
                        "title": "string",
                        "insight_type": "learning|tool|project|content|career|market",
                        "priority": "high|medium|low",
                        "reason": "string",
                        "source_signal_titles": ["string"],
                        "insight_metadata": {},
                    }
                ]
            },
            "category_definitions": {
                "learning": "Something worth studying more deeply today, such as evaluation frameworks, prompting techniques, architecture patterns, AI engineering practices, or research worth understanding.",
                "tool": "A tool, model, workflow, library, framework, or platform worth evaluating directly.",
                "project": "An improvement opportunity for PAOS, Forge, personal systems, or active engineering projects.",
                "content": "A publishing, writing, personal-branding, article, thread, or educational opportunity. Use only when there is a clear publication angle.",
                "career": "A professional opportunity, hiring trend, skill trend, role evolution, or career signal.",
                "market": "An industry movement, business positioning, ecosystem shift, adoption trend, or investment watch signal.",
            },
            "constraints": [
                "Return valid JSON only.",
                "Return between 4 and 10 insights when possible.",
                "Use only supported insight_type and priority values.",
                "Each insight must reference at least one source signal title from the input.",
                "Prefer combining related signals into one insight when it increases actionability.",
                "Do not output tasks, reminders, TODOs, or automation instructions.",
                "If a signal fits multiple categories, choose the most personally actionable category using this priority order: learning, then tool, then project, then content, then career, then market.",
                "Strongly consider learning when a signal suggests a new concept, methodology, framework, architecture pattern, engineering practice, or evaluation approach. Learning is actionable, not passive.",
                "Use tool for tools, models, workflows, libraries, frameworks, platforms, and observability systems that are worth evaluating directly.",
                "Use project for concrete improvement opportunities in PAOS, Forge, personal systems, or active engineering projects.",
                "Use content only when there is a clear publishing, writing, educational, or personal-branding angle. Do not use content just because a topic is interesting.",
                "Use market only when the primary value is industry movement, ecosystem change, adoption trend, business positioning, or investment watchfulness.",
                "Do not use market for product releases, frameworks, tools, workflows, or engineering practices unless the signal is primarily market-oriented.",
                "When the source signals support multiple categories, prefer a balanced distribution across categories and avoid using market as a default catch-all bucket.",
            ],
            "signals": signals,
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def build_signal_reference(signal):
    return {
        "title": compact_text(signal.get("title")),
        "theme": compact_text(signal.get("theme")) or "Other",
        "summary": compact_text(signal.get("summary")),
        "why_it_matters": compact_text(signal.get("why_it_matters")),
        "source_urls": [compact_text(url) for url in (signal.get("source_urls") or []) if compact_text(url)],
        "source_accounts": [
            compact_text(account)
            for account in (signal.get("source_accounts") or [])
            if compact_text(account)
        ],
        "sources": [
            {
                "platform": compact_text(source.get("platform")),
                "source_type": compact_text(source.get("source_type")),
                "source_name": compact_text(source.get("source_name")),
                "url": compact_text(source.get("url")),
            }
            for source in (signal.get("sources") or [])
            if isinstance(source, dict)
        ],
    }


def validate_insight(raw_insight, signal_map, category, language, generation_mode):
    title = compact_text(raw_insight.get("title"))
    insight_type = compact_text(raw_insight.get("insight_type")).lower()
    priority = compact_text(raw_insight.get("priority")).lower()
    reason = compact_text(raw_insight.get("reason"))
    metadata = raw_insight.get("insight_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    source_signal_titles = []
    seen_titles = set()
    for value in raw_insight.get("source_signal_titles") or []:
        normalized = compact_text(value)
        if not normalized or normalized not in signal_map or normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        source_signal_titles.append(normalized)

    if (
        not title
        or insight_type not in SUPPORTED_INSIGHT_TYPES
        or priority not in SUPPORTED_PRIORITIES
        or not reason
        or not source_signal_titles
    ):
        return None

    return {
        "title": title,
        "insight_type": insight_type,
        "priority": priority,
        "reason": reason,
        "source_signals": [build_signal_reference(signal_map[title]) for title in source_signal_titles],
        "generated_at": datetime.now().astimezone().isoformat(),
        "insight_metadata": {
            "insight_version": INSIGHT_VERSION,
            "generation_mode": generation_mode,
            "category": category,
            "language": language,
            "source_signal_count": len(source_signal_titles),
            **metadata,
        },
    }


def generate_ai_insights(category, language, signals, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    config = env_config()
    if not ai_available():
        raise RuntimeError("AI configuration is incomplete.")

    started = time.time()
    endpoint = resolve_endpoint(config)
    payload = {
        "model": config["model"],
        "messages": build_messages(category=category, language=language, signals=signals),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content = parse_response_content(response.json())
    parsed = json.loads(content)
    raw_insights = parsed.get("insights")
    if not isinstance(raw_insights, list) or not raw_insights:
        raise ValueError("AI response did not include a valid `insights` array.")

    signal_map = {
        compact_text(signal.get("title")): signal
        for signal in signals
        if compact_text(signal.get("title"))
    }
    insights = []
    seen_keys = set()
    for raw_insight in raw_insights:
        normalized = validate_insight(
            raw_insight=raw_insight,
            signal_map=signal_map,
            category=category,
            language=language,
            generation_mode="ai",
        )
        if not normalized:
            continue
        key = (
            normalized["title"].lower(),
            normalized["insight_type"],
            tuple(signal["title"] for signal in normalized["source_signals"]),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        insights.append(normalized)

    if not insights:
        raise ValueError("AI response produced no valid insights after validation.")

    diagnostics = {
        "generation_mode": "ai",
        "ai_provider": config["provider"],
        "ai_model": config["model"],
        "ai_endpoint": endpoint,
        "config_source": config["config_source"],
        "ai_duration_seconds": round(time.time() - started, 2),
    }
    return insights, diagnostics


def infer_insight_type(signal):
    theme = compact_text(signal.get("theme")).lower()
    title = compact_text(signal.get("title")).lower()
    summary = compact_text(signal.get("summary")).lower()
    corpus = " ".join([theme, title, summary])

    if any(token in corpus for token in ("education", "prompt", "research", "learn")):
        return "learning"
    if any(token in corpus for token in ("tool", "workflow", "usage", "plugin", "code", "agent")):
        return "tool"
    if any(token in corpus for token in ("paos", "memory", "orchestration", "delivery", "review", "mnemosyne")):
        return "project"
    if any(token in corpus for token in ("content", "guide", "publishing", "education", "prompting")):
        return "content"
    if any(token in corpus for token in ("career", "talent", "developer", "operator")):
        return "career"
    return "market"


def infer_priority(signal):
    count = int(((signal.get("signal_metadata") or {}).get("candidate_count")) or 0)
    if count >= 4:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def build_heuristic_insight(signal, language):
    copy = COPY[language]
    insight_type = infer_insight_type(signal)
    reason = compact_text(signal.get("why_it_matters")) or copy["fallback_reason"]
    title = compact_text(signal.get("title")) or copy["header"]
    return {
        "title": title,
        "insight_type": insight_type,
        "priority": infer_priority(signal),
        "reason": reason,
        "source_signals": [build_signal_reference(signal)],
        "generated_at": datetime.now().astimezone().isoformat(),
        "insight_metadata": {
            "insight_version": INSIGHT_VERSION,
            "generation_mode": "heuristic",
            "language": language,
            "source_signal_count": 1,
        },
    }


def generate_heuristic_insights(signals, language):
    insights = [build_heuristic_insight(signal, language) for signal in signals[:10]]
    diagnostics = {
        "generation_mode": "heuristic",
        "heuristic_reason": COPY[language]["reason"],
    }
    return insights, diagnostics


def type_distribution(insights):
    counter = Counter(item.get("insight_type") or "unknown" for item in insights)
    return {key: counter.get(key, 0) for key in SUPPORTED_INSIGHT_TYPES}


def build_insight_layer(category, date, mode="auto"):
    resolved_date = resolve_date(date)
    signal_file, rendered_digest = validate_digest_freshness(
        date=resolved_date,
        category=category,
    )
    _input_path, signals = load_signals(date=resolved_date, category=category)
    if not signals:
        raise InsightFreshnessError(
            "Signal output is empty or incomplete. "
            f"Run: venv/bin/python runtime/intelligence/jobs/run_signal_builder.py --category {category} --mode ai"
        )

    config = load_runtime_config()
    language = resolve_language(config)
    generation_mode = "heuristic"
    fallback_used = False
    diagnostics = {
        "input_path": str(signal_file),
        "digest_path": str(rendered_digest),
        "generation_mode": "heuristic",
        "fallback_used": False,
        "language": language,
        "ai_provider": env_config().get("provider") or None,
        "ai_model": env_config().get("model") or None,
    }

    if mode == "heuristic":
        insights, extra_diagnostics = generate_heuristic_insights(signals=signals, language=language)
        diagnostics.update(extra_diagnostics)
    else:
        try:
            if mode == "ai" and not ai_available():
                raise RuntimeError("AI mode requested but AI configuration is unavailable.")
            insights, extra_diagnostics = generate_ai_insights(
                category=category,
                language=language,
                signals=signals,
            )
            generation_mode = "ai"
            diagnostics.update(extra_diagnostics)
            diagnostics["generation_mode"] = "ai"
        except Exception as exc:
            if mode == "ai":
                raise
            fallback_used = True
            diagnostics["fallback_used"] = True
            diagnostics["ai_error"] = str(exc)
            insights, extra_diagnostics = generate_heuristic_insights(signals=signals, language=language)
            diagnostics.update(extra_diagnostics)
            diagnostics["generation_mode"] = "heuristic"

    jsonl_path = output_jsonl_path(resolved_date, category)
    markdown_path = output_markdown_path(resolved_date, category)
    write_jsonl(jsonl_path, insights)
    write_markdown(
        markdown_path,
        render_insights(
            category=category,
            date=resolved_date,
            language=language,
            signals=signals,
            insights=insights,
        ),
    )

    return InsightBuildResult(
        category=category,
        date=resolved_date,
        language=language,
        signals_loaded=len(signals),
        insights_generated=len(insights),
        jsonl_path=jsonl_path,
        markdown_path=markdown_path,
        digest_path=rendered_digest,
        generation_mode=generation_mode,
        fallback_used=fallback_used,
        type_distribution=type_distribution(insights),
        diagnostics=diagnostics,
    )


def print_result(result):
    print("Insight Build")
    print(f"date: {result.date}")
    print(f"category: {result.category}")
    print(f"language: {result.language}")
    print(f"signals_loaded: {result.signals_loaded}")
    print(f"insights_generated: {result.insights_generated}")
    print(f"generation_mode: {result.generation_mode}")
    print(f"fallback_used: {result.fallback_used}")
    print(f"jsonl_path: {result.jsonl_path}")
    print(f"markdown_path: {result.markdown_path}")
    print("type_distribution:")
    for key, value in result.type_distribution.items():
        print(f"  {key}: {value}")
    print("diagnostics:")
    for key, value in result.diagnostics.items():
        print(f"  {key}: {value}")


def main():
    args = parse_args()
    result = build_insight_layer(category=args.category, date=args.date, mode=args.mode)
    print_result(result)


if __name__ == "__main__":
    main()
