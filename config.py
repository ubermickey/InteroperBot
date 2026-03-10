"""Bot configuration loaded from environment variables / .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_list(key: str) -> list[str]:
    val = os.getenv(key, "")
    return [v.strip() for v in val.split(",") if v.strip()]


SYSTEM_PROMPT: str = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful assistant responding via iMessage. Keep responses concise and conversational.",
)
ALLOWED_CONTACTS: list[str] = _get_list("ALLOWED_CONTACTS")
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "2"))
MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "50"))
CLI_TIMEOUT: int = int(os.getenv("CLI_TIMEOUT", "120"))
DB_PATH: str = os.getenv(
    "DB_PATH", str(Path.home() / ".interoperbot" / "conversations.db")
)
CLAUDE_CLI: str = os.getenv(
    "CLAUDE_CLI", str(Path.home() / ".local" / "bin" / "claude")
)

# Attachment processing
ENABLE_ATTACHMENTS: bool = os.getenv("ENABLE_ATTACHMENTS", "true").lower() == "true"
ATTACHMENT_TIMEOUT: int = int(os.getenv("ATTACHMENT_TIMEOUT", "30"))
MAX_VIDEO_FRAMES: int = int(os.getenv("MAX_VIDEO_FRAMES", "30"))

# WhatsApp (Baileys bridge)
WHATSAPP_ENABLED: bool = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
WHATSAPP_BRIDGE_PORT: int = int(os.getenv("WHATSAPP_BRIDGE_PORT", "3456"))

# Web UI
WEB_ENABLED: bool = os.getenv("WEB_ENABLED", "true").lower() == "true"
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))
