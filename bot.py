#!/usr/bin/env python3
"""InteroperBot — iMessage-to-Claude bot with persistent conversation storage.

Usage:
    python bot.py              # Run the bot
    python bot.py --dry-run    # Print responses instead of sending
    python bot.py --reset      # Clear all conversation history and exit
    python bot.py --status     # Output JSON status for dashboard
"""

import argparse
import json
import logging
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from ai import ClaudeAssistant
from attachments import enrich_attachments
from imessage import iMessageTransport, SERVICE_FALLBACK
from store import SQLiteStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

shutdown = False


def handle_signal(signum, frame):
    global shutdown
    logger.info("Received signal %s, shutting down...", signum)
    shutdown = True


def parse_args():
    parser = argparse.ArgumentParser(description="InteroperBot iMessage bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print replies to stdout instead of sending via iMessage",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear all conversation history and exit",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Output JSON status for dashboard and exit",
    )
    return parser.parse_args()


def get_status() -> dict:
    """Gather current system status for dashboard consumption."""
    status = {
        "project": "InteroperBot",
        "version": "0.1.0",
        "status": "active",
        "uptime_since": None,
        "last_message_at": None,
        "messages_today": 0,
        "threads": [],
        "todos": [],
        "council_log": [],
        "health": {
            "messages_db": False,
            "claude_cli": False,
            "bot_process": False,
            "disk_usage_pct": 0,
        },
        "activity_log": [],
        "war_room": {"active": False, "blockers": []},
        "team": {
            "lead": "Claude Opus",
            "engineer": "Claude Sonnet",
            "hacker": "Claude Haiku",
            "council_seats": ["Architect", "Critic", "Pragmatist", "Oracle", "Hacker"],
        },
    }

    # Check Messages DB access
    messages_db = Path.home() / "Library" / "Messages" / "chat.db"
    if messages_db.exists():
        try:
            conn = sqlite3.connect(f"file:{messages_db}?mode=ro", uri=True)
            conn.execute("SELECT MAX(ROWID) FROM message")
            conn.close()
            status["health"]["messages_db"] = True
        except sqlite3.OperationalError:
            pass

    # Check Claude CLI availability
    try:
        import subprocess as _sp
        r = _sp.run([config.CLAUDE_CLI, "--version"], capture_output=True, text=True, timeout=5)
        status["health"]["claude_cli"] = r.returncode == 0
    except (FileNotFoundError, _sp.TimeoutExpired):
        pass

    # Check disk usage
    try:
        import shutil
        usage = shutil.disk_usage("/")
        status["health"]["disk_usage_pct"] = round(usage.used / usage.total * 100)
    except OSError:
        pass

    # Load existing status.json for persistent fields (todos, council_log, etc.)
    status_path = Path(__file__).parent / "status.json"
    if status_path.exists():
        try:
            existing = json.loads(status_path.read_text())
            for key in ("todos", "council_log", "activity_log", "war_room", "threads", "team"):
                if key in existing:
                    status[key] = existing[key]
        except (json.JSONDecodeError, OSError):
            pass

    return status


def main():
    args = parse_args()

    if args.status:
        status = get_status()
        print(json.dumps(status, indent=2))
        return

    store = SQLiteStore(db_path=config.DB_PATH)

    if args.reset:
        store.clear_history()
        # Also clear all CLI session IDs so fresh sessions start
        with store._connect() as conn:
            conn.execute("DELETE FROM contact_metadata WHERE key = 'cli_session_id'")
        logger.info("Conversation history and CLI sessions cleared.")
        return

    assistant = ClaudeAssistant(
        system_prompt=config.SYSTEM_PROMPT,
        timeout=config.CLI_TIMEOUT,
    )
    transport = iMessageTransport()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    last_rowid = transport.get_latest_rowid()
    last_outgoing_rowid = transport.get_latest_outgoing_rowid()
    logger.info("Bot started. Watching for new messages (after ROWID %d)...", last_rowid)

    while not shutdown:
        # --- Phase 1: Process incoming messages ---
        incoming = transport.poll_new_messages(last_rowid)

        for msg in incoming:
            last_rowid = max(last_rowid, msg.rowid)

            # Filter by allowed contacts if configured
            if config.ALLOWED_CONTACTS and msg.chat_identifier not in config.ALLOWED_CONTACTS:
                logger.debug("Skipping message from %s (not in allowed list)", msg.chat_identifier)
                continue

            # Build enriched content: text + attachment descriptions
            content = msg.text
            metadata = None
            if msg.attachments and config.ENABLE_ATTACHMENTS:
                descriptions = enrich_attachments(msg.attachments)
                attachment_context = "\n".join(
                    f"[Attached: {d}]" for d in descriptions
                )
                content = f"{msg.text}\n{attachment_context}" if msg.text else attachment_context
                metadata = {
                    "attachments": [
                        {"filename": a.transfer_name, "mime_type": a.mime_type,
                         "size": a.total_bytes, "media_type": a.media_type}
                        for a in msg.attachments
                    ]
                }

            logger.info("Message from %s: %s", msg.chat_identifier, content[:80])

            # Get or create the contact in our store
            contact_id = store.get_or_create_contact(msg.chat_identifier)

            # Load CLI session for this contact (if any)
            session_id = store.get_metadata(contact_id, "cli_session_id")

            # Log the incoming message (enriched content + attachment metadata)
            store.log_message(
                contact_id=contact_id,
                role="user",
                content=content,
                timestamp=msg.timestamp,
                metadata=metadata,
            )

            # Get Claude's response (history is fallback-only now)
            history = store.get_history(contact_id, limit=config.MAX_HISTORY)
            reply, new_session_id = assistant.respond(history, session_id=session_id)

            # Persist the CLI session ID for next turn
            if new_session_id:
                store.set_metadata(contact_id, "cli_session_id", new_session_id)

            # Log the reply
            store.log_message(
                contact_id=contact_id,
                role="assistant",
                content=reply,
            )

            # Send or print the reply
            if args.dry_run:
                print(f"[{msg.chat_identifier}] {reply}")
            else:
                transport.send_message(msg.chat_identifier, reply)
                store.add_pending_delivery(
                    msg.chat_identifier, reply, last_outgoing_rowid,
                )
                last_outgoing_rowid = transport.get_latest_outgoing_rowid()

        # --- Phase 2: Check delivery status and retry failures ---
        if not args.dry_run:
            _check_and_retry_deliveries(store, transport)

        time.sleep(config.POLL_INTERVAL)

    logger.info("Bot stopped.")


def _check_and_retry_deliveries(store: SQLiteStore, transport: iMessageTransport):
    """Check pending deliveries against chat.db and retry failures."""
    pending = store.get_pending_deliveries()
    if not pending:
        return

    for delivery in pending:
        outgoing_rowid = delivery["outgoing_rowid"] or 0
        failures = transport.check_failed_deliveries(outgoing_rowid)

        # Check if any failure matches this delivery's chat_identifier
        failed = any(
            f.chat_identifier == delivery["chat_identifier"] for f in failures
        )

        if not failed and delivery["attempts"] >= 2:
            # No error detected after enough time — assume delivered
            store.update_delivery(delivery["id"], status="delivered")
            store.clear_delivered()
            continue

        if not failed:
            # Still waiting for confirmation — check again next cycle
            continue

        # Delivery failed — try next service
        attempts = delivery["attempts"]
        services_tried = delivery["services_tried"]
        tried_list = [s.strip() for s in services_tried.split(",")]

        # Find next untried service
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
            transport.send_message(
                delivery["chat_identifier"], delivery["content"],
                service_type=next_service,
            )
            new_outgoing = transport.get_latest_outgoing_rowid()
            store.update_delivery(
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
            store.update_delivery(delivery["id"], status="failed")


if __name__ == "__main__":
    main()
