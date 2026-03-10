#!/usr/bin/env python3
"""InteroperBot — Multi-transport messaging bot powered by Claude CLI.

Routes messages from iMessage, WhatsApp, and Web through a single
MessageRouter that handles Store -> AI -> Store for all transports.

Usage:
    python bot.py                  # Run with iMessage (+ web if WEB_ENABLED)
    python bot.py --dry-run        # Print responses instead of sending
    python bot.py --reset          # Clear all conversation history and exit
    python bot.py --status         # Output JSON status for dashboard
    python bot.py --setup-whatsapp # Bootstrap WhatsApp bridge (QR scan)
"""

import argparse
import json
import logging
import signal
import sqlite3
import sys
import threading
from pathlib import Path

import config
from ai import ClaudeAssistant
from core import MessageRouter
from imessage import iMessageTransport
from store import SQLiteStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


def parse_args():
    parser = argparse.ArgumentParser(description="InteroperBot multi-transport bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print replies to stdout instead of sending",
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
    parser.add_argument(
        "--setup-whatsapp",
        action="store_true",
        help="Bootstrap WhatsApp bridge (install deps, scan QR code)",
    )
    return parser.parse_args()


def get_status() -> dict:
    """Gather current system status for dashboard consumption."""
    status = {
        "project": "InteroperBot",
        "version": "0.2.0",
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

    # Load existing status.json for persistent fields
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

    if args.setup_whatsapp:
        from whatsapp import setup_whatsapp
        setup_whatsapp()
        return

    store = SQLiteStore(db_path=config.DB_PATH)

    if args.reset:
        store.clear_history()
        with store._connect() as conn:
            conn.execute("DELETE FROM contact_metadata WHERE key = 'cli_session_id'")
        logger.info("Conversation history and CLI sessions cleared.")
        return

    assistant = ClaudeAssistant(
        system_prompt=config.SYSTEM_PROMPT,
        timeout=config.CLI_TIMEOUT,
    )
    router = MessageRouter(store, assistant)

    # --- Register transports ---

    imessage = iMessageTransport(store=store, dry_run=args.dry_run)
    router.register(imessage)

    if config.WHATSAPP_ENABLED:
        from whatsapp import WhatsAppTransport
        router.register(WhatsAppTransport())

    if config.WEB_ENABLED:
        from web import WebTransport
        import uvicorn

        web = WebTransport(router)
        router.register(web)
        threading.Thread(
            target=uvicorn.run,
            args=(web.app,),
            kwargs={"host": "127.0.0.1", "port": config.WEB_PORT, "log_level": "info"},
            daemon=True,
        ).start()
        logger.info("Web UI at http://127.0.0.1:%d", config.WEB_PORT)

    # --- Signal handling ---

    signal.signal(signal.SIGINT, lambda s, f: router.shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: router.shutdown())

    transports = ", ".join(router.transports.keys())
    logger.info("Bot started. Transports: [%s]", transports)

    router.run()


if __name__ == "__main__":
    main()
