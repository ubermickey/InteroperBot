"""Transport abstraction layer for message delivery.

Provides a MessageTransport ABC that can be backed by iMessage (default),
WhatsApp, or any future messaging platform.

Adding a new transport:
    1. Create a new file (e.g. telegram.py)
    2. Subclass MessageTransport and implement the abstract methods
    3. Decorate with @register_transport("telegram")
    4. Import it in this module's _load_builtin_transports()
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """A message received from any transport."""
    message_id: str          # transport-specific ID (rowid, WhatsApp msg ID, etc.)
    text: str
    chat_identifier: str     # phone number, email, or WhatsApp JID
    timestamp: datetime
    transport: str           # "imessage", "whatsapp", etc.


class MessageTransport(ABC):
    """Abstract interface for message transports.

    Implement this to add support for a new messaging platform
    (iMessage, WhatsApp, Telegram, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this transport (e.g. 'imessage', 'whatsapp')."""
        ...

    @abstractmethod
    def get_initial_state(self) -> Any:
        """Return the initial polling state (e.g. latest message ID).

        The returned value is passed as `since_state` to poll_new_messages().
        """
        ...

    @abstractmethod
    def poll_new_messages(self, since_state: Any) -> tuple[list[IncomingMessage], Any]:
        """Fetch new incoming messages since the given state.

        Returns:
            (messages, new_state) — the list of new messages and updated state
            for the next poll cycle.
        """
        ...

    @abstractmethod
    def send_message(self, recipient: str, text: str, **kwargs) -> bool:
        """Send a message to the given recipient.

        Returns True on success, False on failure.
        """
        ...

    def supports_delivery_tracking(self) -> bool:
        """Whether this transport can detect failed deliveries."""
        return False

    def check_failed_deliveries(self, since_state: Any) -> list[dict]:
        """Check for delivery failures since the given state.

        Override if supports_delivery_tracking() returns True.
        Returns list of dicts with at least 'chat_identifier' and 'error' keys.
        """
        return []

    def get_service_fallback_order(self) -> list[str]:
        """Return the service fallback order for retries.

        Override to provide transport-specific fallback (e.g. iMessage → SMS).
        Default is no fallback.
        """
        return [self.name]


# ---------------------------------------------------------------------------
# Transport registry — plug-and-play discovery
# ---------------------------------------------------------------------------

TRANSPORT_REGISTRY: dict[str, type[MessageTransport]] = {}


def register_transport(name: str):
    """Decorator to register a transport class by name.

    Usage:
        @register_transport("telegram")
        class TelegramTransport(MessageTransport):
            ...
    """
    def decorator(cls: type[MessageTransport]):
        TRANSPORT_REGISTRY[name] = cls
        return cls
    return decorator


def _load_builtin_transports():
    """Import built-in transport modules so their @register_transport runs."""
    # Each import triggers the decorator, populating TRANSPORT_REGISTRY.
    try:
        import imessage  # noqa: F401 — registers "imessage"
    except Exception:
        logger.debug("iMessage transport not available (expected on non-macOS)")
    try:
        import whatsapp  # noqa: F401 — registers "whatsapp"
    except Exception:
        logger.debug("WhatsApp transport not available")
    try:
        import waha  # noqa: F401 — registers "waha"
    except Exception:
        logger.debug("WAHA transport not available")


def create_transports(names: str) -> list[MessageTransport]:
    """Factory: instantiate transports by name.

    Args:
        names: "imessage", "whatsapp", "all", or comma-separated list

    Returns:
        List of instantiated MessageTransport objects.
    """
    _load_builtin_transports()

    if names == "all":
        names_list = list(TRANSPORT_REGISTRY.keys())
    else:
        names_list = [n.strip() for n in names.split(",")]

    transports = []
    for name in names_list:
        cls = TRANSPORT_REGISTRY.get(name)
        if cls is None:
            available = list(TRANSPORT_REGISTRY.keys())
            raise ValueError(f"Unknown transport: {name!r}. Available: {available}")
        transports.append(cls())
    return transports
