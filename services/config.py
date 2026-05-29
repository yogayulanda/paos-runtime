from context.loader import load_env

env = load_env()

PAOS_RUNTIME_PATH = env["PAOS_RUNTIME_PATH"]
PAOS_CONTEXT_PATH = env["PAOS_CONTEXT_PATH"]

TELEGRAM_BOT_TOKEN = env["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = env.get("TELEGRAM_CHAT_ID", "")

LLM_BASE_URL = env.get("LLM_BASE_URL", "")
LLM_API_KEY = env.get("LLM_API_KEY", "local")
LLM_MODEL = env.get("LLM_MODEL", "")