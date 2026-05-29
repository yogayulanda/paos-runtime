import json
from pathlib import Path

import feedparser
import requests

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
# STATE
# ========================================

STATE_FILE = Path(
    "/home/ubuntu/paos/paos-runtime/state/rss-state.json"
)

if STATE_FILE.exists():
    state = json.loads(STATE_FILE.read_text())
else:
    state = {}

# ========================================
# FEEDS
# ========================================

RSS_FEEDS = {

    "🤖 AI": [
        "https://www.reddit.com/r/LocalLLaMA/.rss",
        "https://hnrss.org/newest?q=AI",
        "https://hnrss.org/newest?q=LLM",
        "https://hnrss.org/newest?q=OpenAI",
        "https://hnrss.org/newest?q=Anthropic",
        "https://hnrss.org/newest?q=Claude",
        "https://hnrss.org/newest?q=Copilot",
        "https://hnrss.org/newest?q=Cursor",
        "https://hnrss.org/newest?q=Agent",
        "https://hnrss.org/newest?q=RAG",
    ],

    "💻 Tech": [
        "https://hnrss.org/frontpage",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.wired.com/feed/rss",
        "https://techcrunch.com/feed/",
        "https://www.engadget.com/rss.xml",
        "https://www.zdnet.com/news/rss.xml",
        "https://www.infoq.com/feed/",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://www.reddit.com/r/programming/.rss",
    ],

    "📈 Stocks": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=MSFT&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GOOG&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSLA&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=META&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AMD&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AMZN&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=QQQ&region=US&lang=en-US",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US",
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

            latest_entries = feed.entries[:3]

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
                    f"• {title}\n{link}"
                )

        except Exception as e:
            collected.append(
                f"⚠️ Feed error:\n{feed_url}\n{str(e)}"
            )

    if not collected:
        continue

    digest = "\n\n".join(collected[:10])

    message = f"""
{category} Digest

{digest}
"""

    send_telegram(message)

# ========================================
# SAVE STATE
# ========================================

STATE_FILE.write_text(
    json.dumps(state, indent=2)
)
