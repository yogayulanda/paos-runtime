import json
from pathlib import Path

import feedparser
import requests
from openai import OpenAI

# ========================================
# ENV
# ========================================

ENV_PATH = "/home/ubuntu/paos/paos-runtime/.env"

env = {}

with open(ENV_PATH) as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env[k] = v

TOKEN = env["TELEGRAM_BOT_TOKEN"]
CHAT_ID = env["TELEGRAM_CHAT_ID"]

# ========================================
# LLM
# ========================================

client = OpenAI(
    api_key=env["LLM_API_KEY"],
    base_url=env["LLM_BASE_URL"],
)

MODEL = env["LLM_MODEL"]

# ========================================
# STATE
# ========================================

STATE_FILE = Path(
    "/home/ubuntu/paos/paos-runtime/state/ai-digest-state.json"
)

if STATE_FILE.exists():
    state = json.loads(STATE_FILE.read_text())
else:
    state = {}

# ========================================
# FEEDS
# ========================================

RSS_FEEDS = {
    "AI": [
        "https://www.reddit.com/r/LocalLLaMA/.rss",
        "https://hnrss.org/newest?q=AI",
        "https://hnrss.org/newest?q=LLM",
    ],

    "TECH": [
        "https://hnrss.org/frontpage",
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
    ],

    "STOCKS": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=MSFT&region=US&lang=en-US",
    ]
}

# ========================================
# TELEGRAM
# ========================================

def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message[:4000],
        },
    )

# ========================================
# PROCESS
# ========================================

for category, feeds in RSS_FEEDS.items():

    collected = []

    for feed_url in feeds:

        try:
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                continue

            latest_entries = feed.entries[:5]

            for entry in latest_entries:

                entry_id = entry.get(
                    "id",
                    entry.get("link", "")
                )

                if not entry_id:
                    continue

                if state.get(entry_id):
                    continue

                state[entry_id] = True

                title = entry.get("title", "No title")
                link = entry.get("link", "")

                collected.append(
                    f"- {title}\n{link}"
                )

        except Exception:
            continue

    if not collected:
        continue

    raw_updates = "\n\n".join(collected[:15])

    prompt = f"""
You are an AI intelligence analyst.

Summarize these updates into:
- key trends
- important developments
- notable engineering or market signals

Keep concise but insightful.

Category:
{category}

Updates:
{raw_updates}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    summary = response.choices[0].message.content

    message = f"""
🧠 {category} Intelligence Digest

{summary}
"""

    send_telegram(message)

# ========================================
# SAVE STATE
# ========================================

STATE_FILE.write_text(
    json.dumps(state, indent=2)
)
