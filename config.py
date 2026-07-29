"""Configuration loaded from environment / .env file."""
import os
from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"Missing required env var {name}. Copy .env.example to .env and fill it in.")
    return v


# --- Telegram ---
TELEGRAM_BOT_TOKEN = _req("TELEGRAM_BOT_TOKEN")

# --- LLM (OpenAI-compatible; AIPipe by default) ---
# AIPipe: base_url = https://aipipe.org/openai/v1 , key = your AIPipe token
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://aipipe.org/openai/v1").rstrip("/")
LLM_API_KEY = _req("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")

# --- Log hosting (GitHub raw) ---
# A fine-grained or classic PAT with contents:write on the repo below.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()          # e.g. "yourname/tds-p1-bot"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
LOG_DIR_IN_REPO = os.getenv("LOG_DIR_IN_REPO", "logs").strip("/")

# --- Agent behaviour ---
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "12"))
PYTHON_TIMEOUT = int(os.getenv("PYTHON_TIMEOUT", "60"))       # seconds per code execution
CHAT_DEBOUNCE_SECONDS = float(os.getenv("CHAT_DEBOUNCE_SECONDS", "4"))
