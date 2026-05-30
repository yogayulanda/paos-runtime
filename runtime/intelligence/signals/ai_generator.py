import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from signals.models import SIGNAL_VERSION


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import config as runtime_config


DEFAULT_TIMEOUT_SECONDS = 60


def compact_text(value):
    return " ".join(str(value or "").split())


def env_config():
    override_base_url = compact_text(os.getenv("PAOS_AI_BASE_URL"))
    override_model = compact_text(os.getenv("PAOS_AI_MODEL"))
    override_api_key = compact_text(os.getenv("PAOS_AI_API_KEY"))
    override_provider = compact_text(os.getenv("PAOS_AI_PROVIDER"))

    runtime_base_url = compact_text(os.getenv("LLM_BASE_URL")) or compact_text(
        getattr(runtime_config, "LLM_BASE_URL", "")
    )
    runtime_model = compact_text(os.getenv("LLM_MODEL")) or compact_text(
        getattr(runtime_config, "LLM_MODEL", "")
    )
    runtime_api_key = compact_text(os.getenv("LLM_API_KEY")) or compact_text(
        getattr(runtime_config, "LLM_API_KEY", "")
    )

    base_url = override_base_url or runtime_base_url
    model = override_model or runtime_model
    api_key = override_api_key or runtime_api_key
    provider = override_provider or infer_provider(base_url)
    config_source = (
        "paos_override"
        if override_base_url or override_model or override_api_key or override_provider
        else "runtime_default"
    )

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "config_source": config_source,
    }


def ai_available():
    config = env_config()
    return bool(config["base_url"] and config["model"] and config["api_key"])


def infer_provider(base_url):
    value = compact_text(base_url).lower()
    if not value:
        return ""
    if "openai" in value:
        return "openai_compatible"
    if "openrouter" in value:
        return "openai_compatible"
    if "/v1" in value or "localhost" in value or "127.0.0.1" in value:
        return "openai_compatible"
    return "openai_compatible"


def resolve_endpoint(config):
    base_url = config["base_url"] or "https://api.openai.com/v1"
    return base_url.rstrip("/") + "/chat/completions"


def build_messages(category, candidates):
    system = (
        "You are generating PAOS intelligence signals from trusted-source candidate items.\n"
        "Return strict JSON only.\n"
        "Group related candidates into 5-10 meaningful intelligence signals.\n"
        "Focus on AI engineering, agent workflows, developer tools, product launches, research, education, startups, and career-relevant intelligence.\n"
        "Do not summarize every post individually.\n"
        "Do not invent facts or unsupported claims.\n"
        "Preserve source URLs and source accounts exactly from the candidate input where relevant.\n"
        "Use concise, high-signal titles and summaries."
    )
    user = {
        "category": category,
        "instructions": {
            "required_output_schema": {
                "signals": [
                    {
                        "title": "string",
                        "summary": "string",
                        "theme": "string",
                        "why_it_matters": "string",
                        "sources": [
                            {
                                "platform": "string",
                                "source_type": "string",
                                "source_name": "string",
                                "url": "string"
                            }
                        ],
                        "source_urls": ["string"],
                        "source_accounts": ["string"],
                    }
                ]
            },
            "constraints": [
                "Return valid JSON only.",
                "Return between 5 and 10 signals when possible.",
                "Prefer using the `sources` field with explicit platform, source_type, source_name, and url.",
                "Only use source_urls and source_accounts that exist in candidate input.",
                "Only use source records that exist in candidate input.",
                "Avoid duplicate signals.",
                "Prefer grouping multiple related candidates into one signal.",
            ],
            "candidates": candidates,
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def parse_response_content(payload):
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("AI response contained no choices.")

    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = "\n".join(text_parts)

    content = compact_text(content)
    if not content:
        raise ValueError("AI response content was empty.")

    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    return content


def validate_signal(signal, allowed_urls, allowed_accounts, category):
    title = compact_text(signal.get("title"))
    summary = compact_text(signal.get("summary"))
    theme = compact_text(signal.get("theme")) or "Other"
    why = compact_text(signal.get("why_it_matters"))
    urls = []
    seen_urls = set()
    for value in signal.get("source_urls") or []:
        value = compact_text(value)
        if not value or value not in allowed_urls or value in seen_urls:
            continue
        seen_urls.add(value)
        urls.append(value)

    accounts = []
    seen_accounts = set()
    for value in signal.get("source_accounts") or []:
        value = compact_text(value)
        if not value or value not in allowed_accounts or value in seen_accounts:
            continue
        seen_accounts.add(value)
        accounts.append(value)

    if not title or not summary or not why or not urls or not accounts:
        return None

    sources = []
    seen_sources = set()
    raw_sources = signal.get("sources") or []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        platform = compact_text(source.get("platform"))
        source_type = compact_text(source.get("source_type"))
        source_name = compact_text(source.get("source_name"))
        url = compact_text(source.get("url"))
        if not platform or not source_type or not source_name or not url:
            continue
        if url not in urls or source_name not in accounts:
            continue
        key = (platform, source_type, source_name, url)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        sources.append(
            {
                "platform": platform,
                "source_type": source_type,
                "source_name": source_name,
                "url": url,
            }
        )

    return {
        "title": title,
        "summary": summary,
        "theme": theme,
        "why_it_matters": why,
        "sources": sources,
        "source_urls": urls,
        "source_accounts": accounts,
        "generated_at": datetime.now().astimezone().isoformat(),
        "signal_metadata": {
            "signal_version": SIGNAL_VERSION,
            "generation_mode": "ai",
            "candidate_count": 0,
            "category": category,
        },
    }


def generate_ai_signals(category, candidates, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    config = env_config()
    if not ai_available():
        raise RuntimeError("AI configuration is incomplete.")

    started = time.time()
    endpoint = resolve_endpoint(config)
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": build_messages(category, candidates),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
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
    raw_signals = parsed.get("signals")
    if not isinstance(raw_signals, list) or not raw_signals:
        raise ValueError("AI response did not include a valid `signals` array.")

    allowed_urls = {
        compact_text(item.get("url"))
        for item in candidates
        if compact_text(item.get("url"))
    }
    allowed_accounts = {
        compact_text(item.get("source_name"))
        for item in candidates
        if compact_text(item.get("source_name"))
    }
    source_records_by_url = {}
    candidate_count_by_url = {}
    for item in candidates:
        url = compact_text(item.get("url"))
        if not url:
            continue
        candidate_count_by_url[url] = candidate_count_by_url.get(url, 0) + 1
        source_records_by_url.setdefault(url, [])
        source_records_by_url[url].append(
            {
                "platform": compact_text(item.get("platform")),
                "source_type": compact_text(item.get("source_type")),
                "source_name": compact_text(item.get("source_name")),
                "url": url,
            }
        )

    signals = []
    themes = set()
    for raw_signal in raw_signals:
        normalized = validate_signal(raw_signal, allowed_urls, allowed_accounts, category)
        if not normalized:
            continue
        if not normalized["sources"]:
            seen_sources = set()
            derived_sources = []
            for url in normalized["source_urls"]:
                for source in source_records_by_url.get(url, []):
                    key = (
                        source["platform"],
                        source["source_type"],
                        source["source_name"],
                        source["url"],
                    )
                    if key in seen_sources:
                        continue
                    seen_sources.add(key)
                    derived_sources.append(source)
            normalized["sources"] = derived_sources
        normalized["signal_metadata"]["candidate_count"] = sum(
            candidate_count_by_url.get(url, 0) for url in normalized["source_urls"]
        )
        signals.append(normalized)
        themes.add(normalized["theme"])

    if not signals:
        raise ValueError("AI response produced no valid signals after validation.")

    diagnostics = {
        "generation_mode": "ai",
        "ai_provider": config["provider"],
        "ai_model": config["model"],
        "ai_endpoint": endpoint,
        "config_source": config["config_source"],
        "ai_duration_seconds": round(time.time() - started, 2),
    }
    return signals, sorted(themes), diagnostics
