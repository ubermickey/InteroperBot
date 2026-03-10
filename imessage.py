"""iMessage transport layer.

Handles reading incoming messages from the macOS Messages SQLite database
and sending replies via AppleScript. Includes delivery confirmation via
async chat.db polling and automatic service fallback (iMessage → SMS).
"""

import sqlite3
import subprocess
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from transport import MessageTransport, IncomingMessage, register_transport

logger = logging.getLogger(__name__)

# macOS Messages stores dates as nanoseconds since 2001-01-01
APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01

# Service fallback order
SERVICE_FALLBACK = ["iMessage", "SMS"]


@dataclass
class FailedDelivery:
    rowid: int
    chat_identifier: str
    error: int


def _apple_date_to_datetime(apple_date: int) -> datetime:
    """Convert macOS Messages date (nanoseconds since 2001-01-01) to datetime."""
    if apple_date == 0:
        return datetime.now(timezone.utc)
    # Modern macOS uses nanoseconds
    seconds = apple_date / 1_000_000_000
    unix_ts = seconds + APPLE_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc)


@register_transport("imessage")
class iMessageTransport(MessageTransport):
    """Reads from and writes to iMessage via macOS APIs."""

    MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(self.MESSAGES_DB)

    @property
    def name(self) -> str:
        return "imessage"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_initial_state(self) -> dict:
        """Return initial state with latest rowids for polling."""
        return {
            "last_rowid": self.get_latest_rowid(),
            "last_outgoing_rowid": self.get_latest_outgoing_rowid(),
        }

    def get_latest_rowid(self) -> int:
        """Get the current max ROWID so we only process new messages."""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(ROWID) as max_id FROM message").fetchone()
            return row["max_id"] or 0

    def get_latest_outgoing_rowid(self) -> int:
        """Get the current max ROWID of outgoing messages."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(ROWID) as max_id FROM message WHERE is_from_me = 1"
            ).fetchone()
            return row["max_id"] or 0

    def poll_new_messages(self, since_state: Any) -> tuple[list[IncomingMessage], Any]:
        """Fetch all incoming messages with ROWID > last_rowid."""
        if isinstance(since_state, dict):
            last_rowid = since_state.get("last_rowid", 0)
        else:
            # Backward compat: accept raw int
            last_rowid = int(since_state)

        query = """
            SELECT m.ROWID, m.text, m.date, c.chat_identifier
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE m.ROWID > ? AND m.is_from_me = 0 AND m.text IS NOT NULL
            ORDER BY m.ROWID ASC
        """
        messages = []
        new_last_rowid = last_rowid
        try:
            with self._connect() as conn:
                rows = conn.execute(query, (last_rowid,)).fetchall()
                for row in rows:
                    new_last_rowid = max(new_last_rowid, row["ROWID"])
                    messages.append(
                        IncomingMessage(
                            message_id=str(row["ROWID"]),
                            text=row["text"],
                            chat_identifier=row["chat_identifier"],
                            timestamp=_apple_date_to_datetime(row["date"]),
                            transport="imessage",
                        )
                    )
        except sqlite3.OperationalError as e:
            logger.error("Failed to read Messages DB: %s", e)

        new_state = {"last_rowid": new_last_rowid}
        if isinstance(since_state, dict) and "last_outgoing_rowid" in since_state:
            new_state["last_outgoing_rowid"] = since_state["last_outgoing_rowid"]
        return messages, new_state

    def supports_delivery_tracking(self) -> bool:
        return True

    def check_failed_deliveries(self, since_state: Any) -> list[dict]:
        """Check chat.db for outgoing messages with delivery errors since rowid."""
        if isinstance(since_state, dict):
            since_rowid = since_state.get("last_outgoing_rowid", 0)
        else:
            since_rowid = int(since_state)

        query = """
            SELECT m.ROWID, c.chat_identifier, m.error
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE m.is_from_me = 1 AND m.ROWID > ? AND m.error != 0
            ORDER BY m.ROWID ASC
        """
        failures = []
        try:
            with self._connect() as conn:
                rows = conn.execute(query, (since_rowid,)).fetchall()
                for row in rows:
                    failures.append({
                        "rowid": row["ROWID"],
                        "chat_identifier": row["chat_identifier"],
                        "error": row["error"],
                    })
        except sqlite3.OperationalError as e:
            logger.error("Failed to check delivery status: %s", e)
        return failures

    def get_service_fallback_order(self) -> list[str]:
        return SERVICE_FALLBACK

    def send_message(self, recipient: str, text: str, **kwargs) -> bool:
        """Send a message via AppleScript using the specified service type."""
        service_type = kwargs.get("service_type", "iMessage")
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "Messages" to send "{escaped}" '
            f'to buddy "{recipient}" of '
            f'(service 1 whose service type is {service_type})'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=30,
            )
            logger.info("Sent reply to %s via %s", recipient, service_type)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                "AppleScript failed for %s via %s: %s",
                recipient, service_type, e.stderr.decode(),
            )
            return False
        except subprocess.TimeoutExpired:
            logger.error("AppleScript timed out for %s", recipient)
            return False
