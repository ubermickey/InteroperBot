"""WAHA (WhatsApp HTTP API) transport layer.

Self-hosted WhatsApp transport using WAHA (https://github.com/devlikeapro/waha),
which wraps Baileys (reverse-engineered WhatsApp Web protocol) behind a REST API.

No API key from Meta required — authenticates by scanning a QR code with your
phone, just like WhatsApp Web. Runs as a Docker container.

Setup:
    1. Run WAHA:  docker run -p 3000:3000 devlikeapro/waha
    2. Start a session:  POST http://localhost:3000/api/sessions/start
    3. Scan QR code:  GET http://localhost:3000/api/<session>/auth/qr
    4. Configure env vars (all optional — defaults work out of the box)

Environment Variables:
    WAHA_API_URL        — WAHA base URL (default: http://localhost:3000)
    WAHA_SESSION_NAME   — Session name (default: "default")
    WAHA_WEBHOOK_PORT   — Port for incoming message webhooks (default: 8444)
    WAHA_API_KEY        — WAHA API key if configured (default: none)

WARNING: Uses reverse-engineered WhatsApp protocol. Account ban risk exists.
         Use a dedicated/burner WhatsApp number.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional
from queue import Queue, Empty

import config
from transport import MessageTransport, IncomingMessage, register_transport

logger = logging.getLogger(__name__)

# Optional: use requests if available, fall back to urllib
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    _HAS_REQUESTS = False


def _api_request(method: str, url: str, headers: dict, data: dict = None) -> dict:
    """Make an HTTP request to the WAHA API."""
    if _HAS_REQUESTS:
        resp = _requests.request(method, url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return {}
    else:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url,
            data=body,
            headers={**headers, "Content-Type": "application/json"} if body else headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode()
            return json.loads(content) if content else {}


class WAHAWebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for incoming WAHA webhook events."""

    def log_message(self, format, *args):
        logger.debug("WAHA Webhook: " + format, *args)

    def do_POST(self):
        """Handle incoming WAHA webhook events."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        self.send_response(200)
        self.end_headers()

        try:
            payload = json.loads(body)
            self._process_webhook(payload)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("Failed to parse WAHA webhook payload: %s", e)

    def _process_webhook(self, payload: dict):
        """Extract messages from WAHA webhook payload.

        WAHA sends webhook events with this structure:
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "true_1234567890@c.us_ABCDEF",
                "timestamp": 1704067200,
                "from": "1234567890@c.us",
                "to": "0987654321@c.us",
                "body": "Hello!",
                "fromMe": false,
                "hasMedia": false,
                ...
            }
        }
        """
        event = payload.get("event", "")

        # Only process incoming messages (not status updates, acks, etc.)
        if event not in ("message", "message.any"):
            logger.debug("Skipping WAHA event: %s", event)
            return

        msg = payload.get("payload", {})

        # Skip messages sent by us
        if msg.get("fromMe", False):
            return

        # Extract text body — WAHA puts it directly in "body"
        text = msg.get("body", "")
        if not text:
            logger.debug("Skipping non-text or empty WAHA message")
            return

        # Parse sender — WAHA uses JID format: "1234567890@c.us"
        sender = msg.get("from", "")
        if not sender:
            return

        # Convert JID to phone number for storage consistency
        chat_id = _jid_to_phone(sender)

        ts = msg.get("timestamp", 0)
        incoming = IncomingMessage(
            message_id=msg.get("id", f"waha_{int(time.time())}"),
            text=text,
            chat_identifier=chat_id,
            timestamp=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc),
            transport="waha",
        )
        self.server.message_queue.put(incoming)
        logger.info("WAHA message from %s: %s", chat_id, text[:80])


def _jid_to_phone(jid: str) -> str:
    """Convert WhatsApp JID (1234567890@c.us) to phone number (+1234567890)."""
    phone = jid.split("@")[0]
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


def _phone_to_jid(phone: str) -> str:
    """Convert phone number (+1234567890) to WhatsApp JID (1234567890@c.us)."""
    digits = phone.lstrip("+").replace("-", "").replace(" ", "")
    return f"{digits}@c.us"


@register_transport("waha")
class WAHATransport(MessageTransport):
    """Sends and receives messages via a self-hosted WAHA instance.

    WAHA wraps Baileys (WhatsApp Web protocol) behind a REST API.
    No Meta API key required — just scan a QR code.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        session_name: Optional[str] = None,
        api_key: Optional[str] = None,
        webhook_port: Optional[int] = None,
    ):
        self.api_url = (api_url or getattr(config, "WAHA_API_URL", "http://localhost:3000")).rstrip("/")
        self.session_name = session_name or getattr(config, "WAHA_SESSION_NAME", "default")
        self.api_key = api_key or getattr(config, "WAHA_API_KEY", "")
        self.webhook_port = webhook_port or getattr(config, "WAHA_WEBHOOK_PORT", 8444)

        self._message_queue: Queue = Queue()
        self._webhook_server: Optional[HTTPServer] = None
        self._webhook_thread: Optional[threading.Thread] = None

    @property
    def name(self) -> str:
        return "waha"

    def _headers(self) -> dict:
        """Build request headers, including API key if configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    # --- Session management ---

    def check_session_status(self) -> dict:
        """Check if the WAHA session is connected."""
        try:
            url = f"{self.api_url}/api/sessions/{self.session_name}"
            result = _api_request("GET", url, self._headers())
            return result
        except Exception as e:
            logger.error("Failed to check WAHA session status: %s", e)
            return {"status": "error", "error": str(e)}

    def start_session(self) -> dict:
        """Start a WAHA session (creates it if it doesn't exist)."""
        try:
            url = f"{self.api_url}/api/sessions/{self.session_name}/start"
            data = {
                "name": self.session_name,
                "config": {
                    "webhooks": [
                        {
                            "url": f"http://localhost:{self.webhook_port}/webhook",
                            "events": ["message"],
                        }
                    ]
                },
            }
            result = _api_request("POST", url, self._headers(), data)
            logger.info("WAHA session '%s' started: %s", self.session_name, result.get("status", "unknown"))
            return result
        except Exception as e:
            logger.error("Failed to start WAHA session: %s", e)
            return {"status": "error", "error": str(e)}

    def get_qr_code(self) -> Optional[str]:
        """Get the QR code for pairing (returns base64 image data or None)."""
        try:
            url = f"{self.api_url}/api/{self.session_name}/auth/qr"
            result = _api_request("GET", url, self._headers())
            return result.get("value", None)
        except Exception as e:
            logger.error("Failed to get WAHA QR code: %s", e)
            return None

    # --- Webhook server ---

    def start_webhook(self):
        """Start the webhook HTTP server in a background thread."""
        if self._webhook_server:
            return

        server = HTTPServer(("0.0.0.0", self.webhook_port), WAHAWebhookHandler)
        server.message_queue = self._message_queue

        self._webhook_server = server
        self._webhook_thread = threading.Thread(
            target=server.serve_forever, daemon=True,
        )
        self._webhook_thread.start()
        logger.info("WAHA webhook listening on port %d", self.webhook_port)

    def stop_webhook(self):
        """Stop the webhook HTTP server."""
        if self._webhook_server:
            self._webhook_server.shutdown()
            self._webhook_server = None
            self._webhook_thread = None
            logger.info("WAHA webhook stopped")

    # --- MessageTransport ABC implementation ---

    def get_initial_state(self) -> dict:
        """Initialize: start webhook server and attempt to start WAHA session."""
        self.start_webhook()

        # Try to start/resume the WAHA session
        status = self.check_session_status()
        session_status = status.get("status", "unknown")

        if session_status not in ("CONNECTED", "WORKING"):
            logger.info("WAHA session not connected (status=%s), attempting to start...", session_status)
            self.start_session()
        else:
            logger.info("WAHA session '%s' is connected.", self.session_name)

        return {"last_message_id": None, "session_status": session_status}

    def poll_new_messages(self, since_state: Any) -> tuple[list[IncomingMessage], Any]:
        """Drain the webhook message queue."""
        messages = []
        last_id = since_state.get("last_message_id") if isinstance(since_state, dict) else None

        while True:
            try:
                msg = self._message_queue.get_nowait()
                messages.append(msg)
                last_id = msg.message_id
            except Empty:
                break

        return messages, {"last_message_id": last_id}

    def send_message(self, recipient: str, text: str, **kwargs) -> bool:
        """Send a text message via the WAHA REST API."""
        # Convert phone number to JID if needed
        chat_id = recipient if "@" in recipient else _phone_to_jid(recipient)

        url = f"{self.api_url}/api/sendText"
        data = {
            "session": self.session_name,
            "chatId": chat_id,
            "text": text,
        }

        try:
            result = _api_request("POST", url, self._headers(), data)
            msg_id = result.get("id", "unknown")
            logger.info("Sent WAHA reply to %s (msg_id=%s)", recipient, msg_id)
            return True
        except Exception as e:
            logger.error("WAHA API error sending to %s: %s", recipient, e)
            return False

    def mark_as_read(self, message_id: str, chat_id: str) -> bool:
        """Mark a message as read (sends blue ticks)."""
        url = f"{self.api_url}/api/sendSeen"
        data = {
            "session": self.session_name,
            "chatId": chat_id if "@" in chat_id else _phone_to_jid(chat_id),
        }

        try:
            _api_request("POST", url, self._headers(), data)
            return True
        except Exception:
            return False
