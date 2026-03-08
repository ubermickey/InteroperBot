"""Storage abstraction layer for conversation persistence.

Provides a MessageStore ABC that can be backed by SQLite (default),
Notion, or any future Executive Assistant backend.
"""

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class Contact:
    id: int
    identifier: str  # phone number or email
    display_name: Optional[str]
    created_at: datetime


@dataclass
class Message:
    id: int
    contact_id: int
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime
    metadata: Optional[dict] = None


class MessageStore(ABC):
    """Abstract interface for conversation storage.

    Implement this to back the bot with a different persistence layer
    (e.g. Notion API, a custom EA backend, Postgres, etc.).
    """

    @abstractmethod
    def log_message(
        self,
        contact_id: int,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """Store a message. Returns the message ID."""
        ...

    @abstractmethod
    def get_history(self, contact_id: int, limit: int = 50) -> list[dict]:
        """Return recent messages for a contact as Claude-API-compatible dicts.

        Returns list of {"role": "user"|"assistant", "content": "..."}.
        Oldest first.
        """
        ...

    @abstractmethod
    def get_or_create_contact(
        self, identifier: str, display_name: Optional[str] = None
    ) -> int:
        """Find or create a contact by identifier (phone/email). Returns contact ID."""
        ...

    @abstractmethod
    def get_contact(self, contact_id: int) -> Optional[Contact]:
        """Retrieve a contact by ID."""
        ...

    @abstractmethod
    def get_metadata(self, contact_id: int, key: str) -> Optional[str]:
        """Get a metadata value for a contact."""
        ...

    @abstractmethod
    def set_metadata(self, contact_id: int, key: str, value: str) -> None:
        """Set a metadata value for a contact."""
        ...

    @abstractmethod
    def clear_history(self, contact_id: Optional[int] = None) -> None:
        """Clear message history. If contact_id is None, clear all."""
        ...


class SQLiteStore(MessageStore):
    """SQLite-backed message store. Default for local use."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = Path.home() / ".interoperbot"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "conversations.db")
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL REFERENCES contacts(id),
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_messages_contact_ts
                    ON messages(contact_id, timestamp);

                CREATE TABLE IF NOT EXISTS contact_metadata (
                    contact_id INTEGER NOT NULL REFERENCES contacts(id),
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (contact_id, key)
                );

                CREATE TABLE IF NOT EXISTS pending_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_identifier TEXT NOT NULL,
                    content TEXT NOT NULL,
                    services_tried TEXT NOT NULL DEFAULT 'iMessage',
                    attempts INTEGER NOT NULL DEFAULT 1,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    status TEXT NOT NULL DEFAULT 'pending',
                    outgoing_rowid INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def log_message(
        self,
        contact_id: int,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        ts = timestamp or datetime.now(timezone.utc)
        meta_json = json.dumps(metadata) if metadata else None
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (contact_id, role, content, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (contact_id, role, content, ts.isoformat(), meta_json),
            )
            return cursor.lastrowid

    def get_history(self, contact_id: int, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages "
                "WHERE contact_id = ? "
                "ORDER BY timestamp DESC, id DESC "
                "LIMIT ?",
                (contact_id, limit),
            ).fetchall()
        # Reverse so oldest is first (Claude API expects chronological order)
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_or_create_contact(
        self, identifier: str, display_name: Optional[str] = None
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM contacts WHERE identifier = ?", (identifier,)
            ).fetchone()
            if row:
                return row["id"]
            cursor = conn.execute(
                "INSERT INTO contacts (identifier, display_name) VALUES (?, ?)",
                (identifier, display_name),
            )
            return cursor.lastrowid

    def get_contact(self, contact_id: int) -> Optional[Contact]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, identifier, display_name, created_at FROM contacts WHERE id = ?",
                (contact_id,),
            ).fetchone()
            if not row:
                return None
            return Contact(
                id=row["id"],
                identifier=row["identifier"],
                display_name=row["display_name"],
                created_at=row["created_at"],
            )

    def get_metadata(self, contact_id: int, key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM contact_metadata WHERE contact_id = ? AND key = ?",
                (contact_id, key),
            ).fetchone()
            return row["value"] if row else None

    def set_metadata(self, contact_id: int, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO contact_metadata (contact_id, key, value) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(contact_id, key) DO UPDATE SET value = excluded.value",
                (contact_id, key, value),
            )

    def clear_history(self, contact_id: Optional[int] = None) -> None:
        with self._connect() as conn:
            if contact_id is not None:
                conn.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
            else:
                conn.execute("DELETE FROM messages")

    # --- Pending delivery tracking ---

    def add_pending_delivery(
        self, chat_identifier: str, content: str, outgoing_rowid: Optional[int] = None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO pending_deliveries (chat_identifier, content, outgoing_rowid) "
                "VALUES (?, ?, ?)",
                (chat_identifier, content, outgoing_rowid),
            )
            return cursor.lastrowid

    def get_pending_deliveries(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, chat_identifier, content, services_tried, attempts, "
                "max_attempts, outgoing_rowid FROM pending_deliveries "
                "WHERE status = 'pending'"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_delivery(self, delivery_id: int, **kwargs) -> None:
        allowed = {"services_tried", "attempts", "status", "outgoing_rowid"}
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return
        vals.append(delivery_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE pending_deliveries SET {', '.join(sets)} WHERE id = ?", vals,
            )

    def clear_delivered(self) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM pending_deliveries WHERE status != 'pending'"
            )
            return cursor.rowcount

    # --- Dashboard query helpers ---

    def get_all_conversations(self) -> list[dict]:
        """All contacts with message count, last activity, and last message preview."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT c.id, c.identifier, c.display_name,
                       COUNT(m.id) AS message_count,
                       MAX(m.timestamp) AS last_activity,
                       (SELECT content FROM messages
                        WHERE contact_id = c.id
                        ORDER BY timestamp DESC, id DESC LIMIT 1) AS last_message,
                       (SELECT role FROM messages
                        WHERE contact_id = c.id
                        ORDER BY timestamp DESC, id DESC LIMIT 1) AS last_role
                FROM contacts c
                LEFT JOIN messages m ON m.contact_id = c.id
                GROUP BY c.id
                ORDER BY last_activity DESC NULLS LAST
            """).fetchall()
            return [dict(r) for r in rows]

    def get_conversation_timeline(self, contact_id: int, limit: int = 50) -> list[dict]:
        """Messages with timestamps for train animation timeline."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, timestamp FROM messages "
                "WHERE contact_id = ? "
                "ORDER BY timestamp DESC, id DESC LIMIT ?",
                (contact_id, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_yard_status(self) -> dict:
        """AI and delivery status for the maintenance panel."""
        with self._connect() as conn:
            session_rows = conn.execute(
                "SELECT cm.contact_id, c.identifier, cm.value AS session_id "
                "FROM contact_metadata cm "
                "JOIN contacts c ON c.id = cm.contact_id "
                "WHERE cm.key = 'cli_session_id' AND cm.value != ''"
            ).fetchall()
            pending = conn.execute(
                "SELECT id, chat_identifier, attempts, max_attempts, services_tried "
                "FROM pending_deliveries WHERE status = 'pending'"
            ).fetchall()
            total_messages = conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages"
            ).fetchone()["cnt"]
            total_contacts = conn.execute(
                "SELECT COUNT(*) AS cnt FROM contacts"
            ).fetchone()["cnt"]
        return {
            "active_sessions": [dict(r) for r in session_rows],
            "pending_deliveries": [dict(r) for r in pending],
            "total_messages": total_messages,
            "total_contacts": total_contacts,
        }
