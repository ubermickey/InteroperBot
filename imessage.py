"""iMessage transport layer.

Handles reading incoming messages from the macOS Messages SQLite database
and sending replies via AppleScript. Includes delivery confirmation via
async chat.db polling and automatic service fallback (iMessage -> SMS).

Implements the Transport ABC so MessageRouter can use it alongside
WhatsApp, Web, and future transports.
"""

import sqlite3
import subprocess
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from transport import (
    Transport,
    IncomingMessage as TransportMessage,
    MessageAttachment,
)

logger = logging.getLogger(__name__)

# macOS Messages stores dates as nanoseconds since 2001-01-01
# attributedBody stores NSAttributedString as Apple typedstream binary
APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01

# Service fallback order
SERVICE_FALLBACK = ["iMessage", "SMS"]


@dataclass
class Attachment:
    rowid: int
    mime_type: Optional[str]     # "image/heic", "audio/x-m4a", "video/quicktime"
    filename: Optional[str]      # expanded absolute path on disk
    transfer_name: Optional[str] # original filename
    total_bytes: int
    media_type: str              # "image", "audio", "video", "document"


def _classify_media_type(mime_type: Optional[str]) -> str:
    """Classify a MIME type into a broad media category."""
    if not mime_type:
        return "document"
    prefix = mime_type.split("/")[0]
    if prefix in ("image", "audio", "video"):
        return prefix
    return "document"


def _expand_attachment_path(filename: Optional[str]) -> Optional[str]:
    """Expand ~/Library paths from chat.db to absolute paths."""
    if not filename:
        return None
    return filename.replace("~/", str(Path.home()) + "/")


@dataclass
class IncomingMessage:
    rowid: int
    text: str                    # "" for attachment-only messages
    chat_identifier: str         # phone number or email
    timestamp: datetime
    attachments: list[Attachment] = field(default_factory=list)


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


class iMessageTransport(Transport):
    """Reads from and writes to iMessage via macOS APIs.

    Implements the Transport ABC for use with MessageRouter.
    Also supports standalone use for backward compatibility.
    """

    name = "imessage"
    MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"

    def __init__(self, db_path: Optional[str] = None, store=None, dry_run: bool = False):
        self.db_path = db_path or str(self.MESSAGES_DB)
        self._store = store       # optional, for delivery tracking
        self._dry_run = dry_run
        self._last_rowid = 0
        self._last_outgoing_rowid = 0

    # --- Transport ABC ---

    def start(self, on_message=None) -> None:
        """Initialize polling state."""
        self._last_rowid = self.get_latest_rowid()
        self._last_outgoing_rowid = self.get_latest_outgoing_rowid()
        logger.info(
            "iMessage transport started (after ROWID %d)", self._last_rowid,
        )

    def poll(self, on_message=None) -> None:
        """Poll for new messages, convert to transport format, fire callback."""
        incoming = self.poll_new_messages(self._last_rowid)

        for msg in incoming:
            self._last_rowid = max(self._last_rowid, msg.rowid)

            if config.ALLOWED_CONTACTS and msg.chat_identifier not in config.ALLOWED_CONTACTS:
                logger.debug("Skipping message from %s (not in allowed list)", msg.chat_identifier)
                continue

            if on_message:
                transport_msg = TransportMessage(
                    transport="imessage",
                    sender=msg.chat_identifier,
                    text=msg.text,
                    timestamp=msg.timestamp,
                    attachments=[
                        MessageAttachment(
                            mime_type=a.mime_type,
                            filename=a.transfer_name,
                            local_path=a.filename,
                            size_bytes=a.total_bytes,
                            media_type=a.media_type,
                        )
                        for a in msg.attachments
                    ],
                )
                on_message(transport_msg)

        # iMessage-specific: check delivery status and retry failures
        if self._store and not self._dry_run:
            self._check_deliveries()

    def send(self, recipient: str, text: str) -> bool:
        """Send via AppleScript. Tracks delivery if store is available."""
        if self._dry_run:
            print(f"[{recipient}] {text}")
            return True
        success = self.send_message(recipient, text)
        if success and self._store:
            self._store.add_pending_delivery(
                recipient, text, self._last_outgoing_rowid,
            )
            self._last_outgoing_rowid = self.get_latest_outgoing_rowid()
        return success

    def stop(self) -> None:
        logger.info("iMessage transport stopped")

    # --- Core iMessage methods (unchanged) ---

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
        Also LEFT JOINs attachment metadata for photo/audio/video messages.
        """
        query = """
            SELECT m.ROWID, m.text, m.date, m.attributedBody,
                   m.associated_message_type, c.chat_identifier,
                   a.ROWID as att_rowid, a.mime_type, a.filename as att_filename,
                   a.transfer_name, a.total_bytes
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            LEFT JOIN message_attachment_join maj ON m.ROWID = maj.message_id
            LEFT JOIN attachment a ON maj.attachment_id = a.ROWID
            WHERE m.ROWID > ? AND m.is_from_me = 0
              AND (m.text IS NOT NULL OR m.attributedBody IS NOT NULL
                   OR a.ROWID IS NOT NULL)
            ORDER BY m.ROWID ASC
        """
        messages = []
        seen: dict[int, IncomingMessage] = {}  # group rows by m.ROWID
        try:
            with self._connect() as conn:
                rows = conn.execute(query, (last_rowid,)).fetchall()
                for row in rows:
                    msg_rowid = row["ROWID"]

                    # Skip tapbacks/reactions (associated_message_type != 0)
                    if row["associated_message_type"]:
                        continue

                    # Build or reuse the IncomingMessage for this ROWID
                    if msg_rowid not in seen:
                        text = row["text"] or _extract_attributed_text(
                            row["attributedBody"]
                        )
                        seen[msg_rowid] = IncomingMessage(
                            rowid=msg_rowid,
                            text=text or "",
                            chat_identifier=row["chat_identifier"],
                            timestamp=_apple_date_to_datetime(row["date"]),
                        )

                    # Append attachment if present (LEFT JOIN can be NULL)
                    if row["att_rowid"]:
                        mime = row["mime_type"]
                        seen[msg_rowid].attachments.append(
                            Attachment(
                                rowid=row["att_rowid"],
                                mime_type=mime,
                                filename=_expand_attachment_path(row["att_filename"]),
                                transfer_name=row["transfer_name"],
                                total_bytes=row["total_bytes"] or 0,
                                media_type=_classify_media_type(mime),
                            )
                        )

                # Only include messages that have text or attachments
                for msg in seen.values():
                    if msg.text or msg.attachments:
                        messages.append(msg)
                # Sort by rowid (dict preserves insertion order, but be explicit)
                messages.sort(key=lambda m: m.rowid)

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

    # --- Delivery tracking (iMessage-specific) ---

    def _check_deliveries(self) -> None:
        """Check pending deliveries against chat.db and retry failures."""
        pending = self._store.get_pending_deliveries()
        if not pending:
            return

        for delivery in pending:
            outgoing_rowid = delivery["outgoing_rowid"] or 0
            failures = self.check_failed_deliveries(outgoing_rowid)

            failed = any(
                f.chat_identifier == delivery["chat_identifier"] for f in failures
            )

            if not failed and delivery["attempts"] >= 2:
                self._store.update_delivery(delivery["id"], status="delivered")
                self._store.clear_delivered()
                continue

            if not failed:
                continue

            attempts = delivery["attempts"]
            services_tried = delivery["services_tried"]
            tried_list = [s.strip() for s in services_tried.split(",")]

            next_service = None
            for svc in SERVICE_FALLBACK:
                if svc not in tried_list:
                    next_service = svc
                    break

            if next_service and attempts < delivery["max_attempts"]:
                logger.warning(
                    "Delivery to %s failed via %s, retrying via %s (attempt %d/%d)",
                    delivery["chat_identifier"], tried_list[-1], next_service,
                    attempts + 1, delivery["max_attempts"],
                )
                self.send_message(
                    delivery["chat_identifier"], delivery["content"],
                    service_type=next_service,
                )
                new_outgoing = self.get_latest_outgoing_rowid()
                self._store.update_delivery(
                    delivery["id"],
                    services_tried=services_tried + "," + next_service,
                    attempts=attempts + 1,
                    outgoing_rowid=new_outgoing,
                )
            else:
                logger.error(
                    "Delivery to %s failed after %d attempts via %s — giving up",
                    delivery["chat_identifier"], attempts, services_tried,
                )
                self._store.update_delivery(delivery["id"], status="failed")
