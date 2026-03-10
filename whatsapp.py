"""WhatsApp transport layer (Baileys bridge).

Manages a Node.js subprocess running the Baileys WhatsApp Web client.
Communication: HTTP for sends, WebSocket for incoming messages.
"""

import json
import logging
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import config
from transport import Transport, IncomingMessage

logger = logging.getLogger(__name__)

BRIDGE_DIR = Path(__file__).parent / "helpers" / "wa-bridge"


class WhatsAppTransport(Transport):
    """WhatsApp transport via a local Baileys Node.js bridge.

    The bridge runs as a subprocess serving HTTP + WebSocket on localhost.
    - POST /send: send messages
    - GET /status: connection state
    - WebSocket /ws: incoming message stream
    """

    name = "whatsapp"

    def __init__(self):
        self.bridge_url = f"http://127.0.0.1:{config.WHATSAPP_BRIDGE_PORT}"
        self.bridge_process: Optional[subprocess.Popen] = None
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None

    def start(self, on_message: Callable[[IncomingMessage], str]) -> None:
        """Launch the Node.js bridge and connect WebSocket."""
        if not (BRIDGE_DIR / "node_modules").exists():
            logger.error(
                "WhatsApp bridge not installed. Run: python bot.py --setup-whatsapp"
            )
            return

        logger.info("Starting WhatsApp bridge at %s", self.bridge_url)
        self.bridge_process = subprocess.Popen(
            ["node", str(BRIDGE_DIR / "index.js")],
            cwd=str(BRIDGE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for bridge to start
        time.sleep(2)

        # Connect WebSocket for incoming messages
        try:
            import websocket

            ws_url = f"ws://127.0.0.1:{config.WHATSAPP_BRIDGE_PORT}/ws"
            self._ws = websocket.WebSocketApp(
                ws_url,
                on_message=lambda ws, data: self._handle(data, on_message),
                on_error=lambda ws, err: logger.error("WA bridge WS error: %s", err),
                on_close=lambda ws, code, msg: logger.info("WA bridge WS closed"),
            )
            self._ws_thread = threading.Thread(
                target=self._ws.run_forever,
                daemon=True,
            )
            self._ws_thread.start()
            logger.info("WhatsApp transport connected")
        except ImportError:
            logger.error("websocket-client not installed: pip install websocket-client")

    def send(self, recipient: str, text: str) -> bool:
        """Send via bridge HTTP API."""
        try:
            import httpx

            r = httpx.post(
                f"{self.bridge_url}/send",
                json={"to": recipient, "text": text},
                timeout=30,
            )
            return r.status_code == 200
        except Exception as e:
            logger.error("WhatsApp send failed: %s", e)
            return False

    def stop(self) -> None:
        """Terminate the bridge subprocess."""
        if self._ws:
            self._ws.close()
        if self.bridge_process:
            self.bridge_process.terminate()
            self.bridge_process.wait(timeout=5)
            logger.info("WhatsApp bridge stopped")

    def _handle(self, raw: str, on_message: Callable) -> None:
        """Convert bridge JSON event -> IncomingMessage -> route."""
        try:
            data = json.loads(raw)
            if data.get("type") != "message":
                return

            msg = IncomingMessage(
                transport="whatsapp",
                sender=data["from"],
                text=data.get("text", ""),
                timestamp=datetime.fromisoformat(data["timestamp"]),
                raw=data,
            )
            on_message(msg)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse bridge message: %s", e)


def setup_whatsapp() -> None:
    """Automated bridge bootstrap: check Node, scaffold, npm install, QR scan."""
    # 1. Check Node.js
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise FileNotFoundError
        logger.info("Node.js %s found", result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("Node.js required. Install: brew install node")
        return

    # 2. Scaffold bridge files if missing
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    package_json = BRIDGE_DIR / "package.json"
    index_js = BRIDGE_DIR / "index.js"

    if not package_json.exists() or not index_js.exists():
        print("Bridge files should exist at helpers/wa-bridge/")
        print("If missing, check the repository or re-clone.")
        return

    # 3. npm install
    if not (BRIDGE_DIR / "node_modules").exists():
        print("Installing bridge dependencies...")
        subprocess.run(["npm", "install"], cwd=str(BRIDGE_DIR), check=True)

    # 4. Start bridge for QR scan
    print("\nStarting bridge — scan the QR code with WhatsApp:")
    print("  WhatsApp → Settings → Linked Devices → Link a Device")
    print("  Press Ctrl+C when connected.\n")

    proc = subprocess.Popen(
        ["node", str(BRIDGE_DIR / "index.js")],
        cwd=str(BRIDGE_DIR),
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nWhatsApp bridge setup complete.")
        print("Credentials saved to helpers/wa-bridge/auth/")
        print("Enable with: WHATSAPP_ENABLED=true python bot.py")
