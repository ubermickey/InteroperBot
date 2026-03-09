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
# attributedBody stores NSAttributedString as Apple typedstream binary
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


def _extract_attributed_text(blob: Optional[bytes]) -> Optional[str]:
    """Extract plain text from an NSAttributedString typedstream blob.

    The attributedBody column stores a NeXT typedstream binary. The readable
    text sits between the NSString type header and the NSDictionary metadata.
    We locate it by scanning for the NSString/NSSuperString marker byte
    sequence and extracting the UTF-8 content that follows.
    """
    if not blob:
        return None
    try:
        # The typedstream contains the text after a length-prefixed NSString.
        # Strategy: find the "+NSString" or "NSAttributedString" marker,
        # then read the length-prefixed text block that follows.
        # The text block starts after a specific byte pattern:
        #   ...NSString...  <length_byte> <text_bytes>  ...NSDictionary...
        text = blob.decode("utf-8", errors="replace")

        # Look for content between the stream header and attribute metadata.
        # The typedstream places the actual string after "NSString" class info
        # and terminates before "NSDictionary" or "NSAttributes" sections.
        # A reliable heuristic: find the first substantial UTF-8 run after
        # the binary header and before the attribute dictionaries.

        # Approach: scan the raw bytes for the longest UTF-8 run.
        # The text payload is always the longest printable sequence in the blob.
        runs = []
        current_run = bytearray()
        for byte in blob:
            # Accept printable ASCII, common UTF-8 continuation, newlines, tabs
            if 0x20 <= byte <= 0x7E or byte in (0x0A, 0x0D, 0x09):
                current_run.append(byte)
            elif byte >= 0xC0:  # UTF-8 multibyte lead
                current_run.append(byte)
            elif byte >= 0x80 and current_run and current_run[-1] >= 0x80:
                current_run.append(byte)  # UTF-8 continuation
            else:
                if len(current_run) > 1:
                    runs.append(bytes(current_run))
                current_run = bytearray()
        if len(current_run) > 1:
            runs.append(bytes(current_run))

        if not runs:
            return None

        # The actual message text is the longest run, decoded as UTF-8
        longest = max(runs, key=len)
        decoded = longest.decode("utf-8", errors="replace").strip()

        # Filter out typedstream metadata strings (class names, keys)
        # These are short and contain known Apple class markers
        metadata_markers = (
            "NSAttributedString", "NSString", "NSDictionary",
            "NSMutableAttributedString", "NSObject", "NSMutableString",
            "NSColor", "NSFont", "NSParagraphStyle",
            "streamtyped", "__kIMMessage",
        )
        if any(decoded.startswith(m) for m in metadata_markers):
            # This run is metadata — try the second longest
            runs_decoded = []
            for r in runs:
                d = r.decode("utf-8", errors="replace").strip()
                if d and not any(d.startswith(m) for m in metadata_markers):
                    runs_decoded.append(d)
            if runs_decoded:
                decoded = max(runs_decoded, key=len)
            else:
                return None

        return decoded if len(decoded) > 0 else None
    except Exception as e:
        logger.debug("attributedBody extraction failed: %s", e)
        return None


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
        """Fetch all incoming messages with ROWID > last_rowid.

        Reads both `text` and `attributedBody` columns — macOS stores ~95%
        of messages only in attributedBody (NSAttributedString binary).
        """
        query = """
            SELECT m.ROWID, m.text, m.date, m.attributedBody,
                   m.associated_message_type, c.chat_identifier
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE m.ROWID > ? AND m.is_from_me = 0
              AND (m.text IS NOT NULL OR m.attributedBody IS NOT NULL)
            ORDER BY m.ROWID ASC
        """
        messages = []
        try:
            with self._connect() as conn:
                rows = conn.execute(query, (last_rowid,)).fetchall()
                for row in rows:
                    # Skip tapbacks/reactions (associated_message_type != 0)
                    if row["associated_message_type"]:
                        continue

                    text = row["text"] or _extract_attributed_text(
                        row["attributedBody"]
                    )
                    if not text:
                        continue  # attachment-only or undecodable

                    messages.append(
                        IncomingMessage(
                            rowid=row["ROWID"],
                            text=text,
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
        escaped_id = chat_identifier.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "Messages" to send "{escaped}" '
            f'to buddy "{escaped_id}" of '
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
