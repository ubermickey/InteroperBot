"""Transport abstraction layer.

Defines transport-agnostic message types and the Transport ABC that all
message transports (iMessage, WhatsApp, Web) implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional


@dataclass
class MessageAttachment:
    """Transport-agnostic attachment metadata."""

    mime_type: Optional[str]
    filename: Optional[str]       # display name (e.g. "photo.jpg")
    local_path: Optional[str]     # absolute path on disk (for enrichment)
    size_bytes: int
    media_type: str               # "image", "audio", "video", "document"


@dataclass
class IncomingMessage:
    """Transport-agnostic incoming message."""

    transport: str           # "imessage", "whatsapp", "web"
    sender: str              # phone/email/user-id
    text: str
    timestamp: datetime
    attachments: list[MessageAttachment] = field(default_factory=list)
    raw: Optional[dict] = None


class Transport(ABC):
    """Abstract base class for message transports.

    Transports come in two flavors:
    - Pull (polling): Override poll() — e.g. iMessage reads chat.db
    - Push (event-driven): Override start() — e.g. WhatsApp WebSocket
    """

    name: str

    @abstractmethod
    def send(self, recipient: str, text: str) -> bool:
        """Send a message to the recipient. Returns True on success."""
        ...

    def start(self, on_message: Callable[[IncomingMessage], str]) -> None:
        """Initialize the transport. Push transports begin receiving here."""
        pass

    def stop(self) -> None:
        """Gracefully shut down the transport."""
        pass

    def poll(self, on_message: Callable[[IncomingMessage], str]) -> None:
        """Poll for new messages (pull transports only)."""
        pass
