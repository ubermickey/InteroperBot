#!/usr/bin/env python3
"""InteroperBot — iMessage-to-Claude bot with persistent conversation storage.

Usage:
    python bot.py              # Run the bot
    python bot.py --dry-run    # Print responses instead of sending
    python bot.py --reset      # Clear all conversation history and exit
"""

import argparse
import logging
import signal
import sys
import time

import config
from ai import ClaudeAssistant
from imessage import iMessageTransport
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
    return parser.parse_args()


def main():
    args = parse_args()

    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set. Create a .env file or export it.")
        sys.exit(1)

    store = SQLiteStore(db_path=config.DB_PATH)

    if args.reset:
        store.clear_history()
        logger.info("Conversation history cleared.")
        return

    assistant = ClaudeAssistant(
        api_key=config.ANTHROPIC_API_KEY,
        model=config.CLAUDE_MODEL,
        system_prompt=config.SYSTEM_PROMPT,
    )
    transport = iMessageTransport()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    last_rowid = transport.get_latest_rowid()
    logger.info("Bot started. Watching for new messages (after ROWID %d)...", last_rowid)

    while not shutdown:
        incoming = transport.poll_new_messages(last_rowid)

        for msg in incoming:
            last_rowid = max(last_rowid, msg.rowid)

            # Filter by allowed contacts if configured
            if config.ALLOWED_CONTACTS and msg.chat_identifier not in config.ALLOWED_CONTACTS:
                logger.debug("Skipping message from %s (not in allowed list)", msg.chat_identifier)
                continue

            logger.info("Message from %s: %s", msg.chat_identifier, msg.text[:80])

            # Get or create the contact in our store
            contact_id = store.get_or_create_contact(msg.chat_identifier)

            # Log the incoming message
            store.log_message(
                contact_id=contact_id,
                role="user",
                content=msg.text,
                timestamp=msg.timestamp,
            )

            # Load conversation history and get Claude's response
            history = store.get_history(contact_id, limit=config.MAX_HISTORY)
            reply = assistant.respond(history)

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

        time.sleep(config.POLL_INTERVAL)

    logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
