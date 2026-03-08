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
from typing import Optional

logger = logging.getLogger(__name__)

# macOS Messages stores dates as nanoseconds since 2001-01-01
APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01

# Service fallback order
SERVICE_FALLBACK = ["iMessage", "SMS"]


@dataclass
class IncomingMessage:
    rowid: int
    text: str
    chat_identifier: str  # phone number or email
    timestamp: datetime


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


class iMessageTransport:
    """Reads from and writes to iMessage via macOS APIs."""

    MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(self.MESSAGES_DB)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

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

    def poll_new_messages(self, last_rowid: int) -> list[IncomingMessage]:
        """Fetch all incoming messages with ROWID > last_rowid."""
        query = """
            SELECT m.ROWID, m.text, m.date, c.chat_identifier
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE m.ROWID > ? AND m.is_from_me = 0 AND m.text IS NOT NULL
            ORDER BY m.ROWID ASC
        """
        messages = []
        try:
            with self._connect() as conn:
                rows = conn.execute(query, (last_rowid,)).fetchall()
                for row in rows:
                    messages.append(
                        IncomingMessage(
                            rowid=row["ROWID"],
                            text=row["text"],
                            chat_identifier=row["chat_identifier"],
                            timestamp=_apple_date_to_datetime(row["date"]),
                        )
                    )
        except sqlite3.OperationalError as e:
            logger.error("Failed to read Messages DB: %s", e)
        return messages

    def check_failed_deliveries(self, since_rowid: int) -> list[FailedDelivery]:
        """Check chat.db for outgoing messages with delivery errors since rowid."""
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
                    failures.append(
                        FailedDelivery(
                            rowid=row["ROWID"],
                            chat_identifier=row["chat_identifier"],
                            error=row["error"],
                        )
                    )
        except sqlite3.OperationalError as e:
            logger.error("Failed to check delivery status: %s", e)
        return failures

    @staticmethod
    def send_message(
        chat_identifier: str, text: str, service_type: str = "iMessage",
    ) -> bool:
        """Send a message via AppleScript using the specified service type."""
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "Messages" to send "{escaped}" '
            f'to buddy "{chat_identifier}" of '
            f'(service 1 whose service type is {service_type})'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=30,
            )
            logger.info("Sent reply to %s via %s", chat_identifier, service_type)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                "AppleScript failed for %s via %s: %s",
                chat_identifier, service_type, e.stderr.decode(),
            )
            return False
        except subprocess.TimeoutExpired:
            logger.error("AppleScript timed out for %s", chat_identifier)
            return False
