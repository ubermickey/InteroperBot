"""Bot configuration loaded from environment variables / .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_list(key: str) -> list[str]:
    val = os.getenv(key, "")
    return [v.strip() for v in val.split(",") if v.strip()]


ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
SYSTEM_PROMPT: str = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful assistant responding via iMessage. Keep responses concise and conversational.",
)
ALLOWED_CONTACTS: list[str] = _get_list("ALLOWED_CONTACTS")
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "2"))
MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "50"))
DB_PATH: str = os.getenv(
    "DB_PATH", str(Path.home() / ".interoperbot" / "conversations.db")
)
