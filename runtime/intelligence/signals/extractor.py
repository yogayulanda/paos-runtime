import json
import re
from collections import defaultdict
from datetime import datetime

from signals.models import SIGNAL_VERSION


TOPIC_RULES = [
    {
        "key": "anthropic_rwanda_alx",
        "title": "Anthropic expands AI education in Africa",
        "theme": "AI Education",
        "why": "Claude is moving into education and public-sector initiatives, which signals broader institutional adoption beyond developer tooling.",
        "keywords": ["rwanda", "alx", "education", "learner", "chidi", "africa"],
    },
    {
        "key": "claude_opus_48",
        "title": "Claude Opus 4.8 launch drives coding-model discussion",
        "theme": "AI Product Launches",
        "why": "Model launches and workflow upgrades shape how builders allocate tool spend, agent workflows, and coding-stack defaults.",
        "keywords": ["opus 4.8", "4.8", "claude code", "dynamic workflows", "swe-bench", "fast mode"],
    },
    {
        "key": "salesforce_agentic",
        "title": "Agentic software workflows are being validated at enterprise scale",
        "theme": "Agent Engineering",
        "why": "Enterprise case studies with measurable delivery and quality gains are strong evidence that agentic workflows are becoming operational, not experimental.",
        "keywords": ["salesforce", "agentic", "231 days", "21 endpoints", "incidents dropped", "workflow itself"],
    },
    {
        "key": "mnemosyne_memory",
        "title": "Memory and context plumbing remain a real agent-engineering bottleneck",
        "theme": "Agent Engineering",
        "why": "Context continuity, environment correctness, and memory systems still decide whether agent setups feel powerful or brittle in practice.",
        "keywords": ["mnemosyne", "hermes", "context", "env", "memory system", "obsidian"],
    },
    {
        "key": "kiro_tooling",
        "title": "Developers are actively comparing AI coding tools on cost and workflow comfort",
        "theme": "Developer Tools",
        "why": "Tool preference is increasingly driven by limit behavior, workflow feel, and model access rather than raw benchmark claims alone.",
        "keywords": ["kiro", "windsurf", "trial gratis", "langganan claude", "bansos", "antigravity"],
    },
    {
        "key": "superpowers_harness",
        "title": "Agent harness experimentation is moving toward self-hosted terminal orchestration",
        "theme": "Agent Engineering",
        "why": "Teams building their own harness patterns are treating agent control surfaces as a product surface, not just a prompt surface.",
        "keywords": ["superpowers", "harness", "agy", "tmux", "send-keys", "capture-pane"],
    },
    {
        "key": "higgsfield_photo_prompts",
        "title": "Prompt-pack growth is pushing AI creator tooling toward template commerce",
        "theme": "AI Product Launches",
        "why": "The market is rewarding repeatable prompt systems and packaged workflows, not only standalone models.",
        "keywords": ["higgsfield", "photo edits", "prompts", "watermarks", "portrait", "anime effect"],
    },
]

THEME_RULES = [
    ("AI Education", ["education", "learner", "school", "tutor", "africa", "rwanda", "alx"]),
    ("Agent Engineering", ["agent", "agentic", "harness", "workflow", "subagent", "memory", "tmux", "migration"]),
    ("Developer Tools", ["tool", "repo", "plugin", "terminal", "code", "kiro", "windsurf", "developer"]),
    ("AI Product Launches", ["launch", "available today", "released", "new", "opus 4.8", "fast mode"]),
    ("AI Models", ["model", "claude", "chatgpt", "opus", "sonnet", "benchmark"]),
    ("AI Research", ["research", "paper", "study", "benchmark"]),
    ("Startups", ["startup", "founder", "product", "market"]),
]

OTHER_THEME = "Other"


def compact_text(value):
    return " ".join(str(value or "").split())


def lower_text(value):
    return compact_text(value).lower()


def split_sentences(text):
    value = compact_text(text)
    if not value:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]


def first_sentences(text, limit=2):
    sentences = split_sentences(text)
    if not sentences:
        return compact_text(text)
    return " ".join(sentences[:limit])


def detect_theme(text):
    lowered = lower_text(text)
    for theme, keywords in THEME_RULES:
        if any(keyword in lowered for keyword in keywords):
            return theme
    return OTHER_THEME


def match_topic_rule(text):
    lowered = lower_text(text)
    for rule in TOPIC_RULES:
        if any(keyword in lowered for keyword in rule["keywords"]):
            return rule
    return None


def default_topic_key(candidate):
    theme = detect_theme(candidate.get("content", ""))
    normalized_theme = theme.lower().replace(" ", "_")
    return {
        "key": f"{normalized_theme}_roundup",
        "title": f"{theme} roundup from trusted Threads accounts",
        "theme": theme,
        "why": "",
        "keywords": [],
    }


def classify_candidate(candidate):
    content = candidate.get("content", "")
    topic = match_topic_rule(content) or default_topic_key(candidate)
    theme = topic["theme"] or detect_theme(content)
    return {
        "topic_key": topic["key"],
        "theme": theme,
        "title_hint": topic.get("title") or "",
        "why_hint": topic.get("why") or "",
    }


def group_candidates(candidates):
    groups = defaultdict(list)
    theme_counts = defaultdict(int)

    for candidate in candidates:
        classification = classify_candidate(candidate)
        key = classification["topic_key"]
        candidate = dict(candidate)
        candidate["_classification"] = classification
        groups[key].append(candidate)
        theme_counts[classification["theme"]] += 1

    return groups, dict(theme_counts)


def representative_candidate(candidates):
    return max(
        candidates,
        key=lambda item: (
            len(compact_text(item.get("content"))),
            compact_text(item.get("source_name")),
        ),
    )


def build_title(representative, title_hint, theme):
    if title_hint:
        return title_hint

    content = compact_text(representative.get("content"))
    source = compact_text(representative.get("source_name"))
    sentence = first_sentences(content, limit=1)
    if not sentence:
        return f"{theme} signal from {source}"

    sentence = re.sub(r"^[\"'“”]+|[\"'“”]+$", "", sentence)
    return sentence[:96].rstrip(" ,.;:")


def build_summary(candidates, representative, theme):
    base = first_sentences(representative.get("content", ""), limit=2)
    if len(candidates) == 1:
        return base

    accounts = sorted(
        {compact_text(item.get("source_name")) for item in candidates if item.get("source_name")}
    )
    return (
        f"{base} This theme appeared across {len(candidates)} candidate items "
        f"from {len(accounts)} account(s)."
    )


def build_why_it_matters(candidates, representative, theme, why_hint):
    if why_hint:
        return why_hint

    source_accounts = sorted(
        {compact_text(item.get("source_name")) for item in candidates if item.get("source_name")}
    )
    if theme == "Developer Tools":
        return "Developer-tool chatter is useful because workflow preference shifts often show up in trusted-source posts before they harden into broader market defaults."
    if theme == "Agent Engineering":
        return "Agent-engineering signals matter because they reveal where real execution bottlenecks and leverage points are emerging in production workflows."
    if theme == "AI Models":
        return "Model-level signals matter because capability, pricing, and reliability changes quickly influence downstream tool choice and product direction."
    if theme == "AI Product Launches":
        return "Product-launch signals matter because they reshape the practical stack builders can use immediately."
    if theme == "AI Education":
        return "Education adoption matters because it shows where AI products are turning into institutional infrastructure."
    return (
        f"This signal was derived from {len(candidates)} candidate item(s) across "
        f"{len(source_accounts)} trusted account(s), making it reusable for downstream digest and opportunity analysis."
    )


def build_sources(candidates):
    sources = []
    seen = set()

    for item in candidates:
        source = {
            "platform": compact_text(item.get("platform")),
            "source_type": compact_text(item.get("source_type")),
            "source_name": compact_text(item.get("source_name")),
            "url": compact_text(item.get("url")) or None,
        }
        key = (
            source["platform"],
            source["source_type"],
            source["source_name"],
            source["url"],
        )
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)

    return sources


def build_signal(group_key, candidates):
    representative = representative_candidate(candidates)
    classification = representative["_classification"]
    theme = classification["theme"]
    title = build_title(representative, classification["title_hint"], theme)
    summary = build_summary(candidates, representative, theme)
    why_it_matters = build_why_it_matters(
        candidates,
        representative,
        theme,
        classification["why_hint"],
    )
    urls = []
    seen_urls = set()
    for item in candidates:
        url = compact_text(item.get("url"))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        urls.append(url)

    accounts = sorted(
        {compact_text(item.get("source_name")) for item in candidates if item.get("source_name")}
    )
    sources = build_sources(candidates)

    return {
        "title": title,
        "summary": summary,
        "theme": theme,
        "why_it_matters": why_it_matters,
        "sources": sources,
        "source_urls": urls,
        "source_accounts": accounts,
        "generated_at": datetime.now().astimezone().isoformat(),
        "signal_metadata": {
            "signal_version": SIGNAL_VERSION,
            "topic_key": group_key,
            "candidate_count": len(candidates),
            "category": compact_text(representative.get("category")),
        },
    }


def build_signals(candidates):
    groups, theme_counts = group_candidates(candidates)
    ranked_groups = sorted(
        groups.items(),
        key=lambda item: (
            -len(item[1]),
            item[1][0]["_classification"]["theme"],
            compact_text(item[1][0].get("source_name")),
            item[0],
        ),
    )

    signals = [build_signal(group_key, items) for group_key, items in ranked_groups]
    themes = sorted(theme_counts.keys())
    diagnostics = {
        "group_count": len(groups),
        "theme_counts": theme_counts,
        "signals_by_theme": {
            theme: sum(1 for signal in signals if signal["theme"] == theme)
            for theme in themes
        },
    }
    return signals, themes, diagnostics


def build_heuristic_signals(candidates):
    signals, themes, diagnostics = build_signals(candidates)
    for signal in signals:
        signal["signal_metadata"]["generation_mode"] = "heuristic"
    return signals, themes, diagnostics
