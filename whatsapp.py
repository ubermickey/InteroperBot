"""WhatsApp transport layer.

Handles sending and receiving WhatsApp messages via the WhatsApp Business
Cloud API (Meta Graph API). Requires a WhatsApp Business Account and
access token.

Setup:
    1. Create a Meta Business App at https://developers.facebook.com
    2. Enable WhatsApp product and get a permanent access token
    3. Register a phone number for the WhatsApp Business API
    4. Set a webhook URL for incoming messages
    5. Configure env vars: WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID

Environment Variables:
    WHATSAPP_ACCESS_TOKEN      — Meta Graph API access token
    WHATSAPP_PHONE_NUMBER_ID   — Your WhatsApp phone number ID
    WHATSAPP_VERIFY_TOKEN      — Webhook verification token (for incoming)
    WHATSAPP_WEBHOOK_PORT      — Port for webhook server (default 8443)
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse
from queue import Queue, Empty

import config
from transport import MessageTransport, IncomingMessage, register_transport

logger = logging.getLogger(__name__)

# Optional: use requests if available, fall back to urllib
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    _HAS_REQUESTS = False


def _api_post(url: str, headers: dict, data: dict) -> dict:
    """POST JSON to the WhatsApp API, using requests or urllib."""
    if _HAS_REQUESTS:
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())


class WhatsAppWebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for incoming WhatsApp webhook events."""

    message_queue: Queue  # set by WhatsAppTransport before server starts

    def log_message(self, format, *args):
        logger.debug("Webhook: " + format, *args)

    def do_GET(self):
        """Handle webhook verification from Meta."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        mode = params.get("hub.mode", [None])[0]
        token = params.get("hub.verify_token", [None])[0]
        challenge = params.get("hub.challenge", [None])[0]

        verify_token = getattr(self.server, "verify_token", "")

        if mode == "subscribe" and token == verify_token and challenge:
            logger.info("Webhook verified successfully")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(challenge.encode())
        else:
            logger.warning("Webhook verification failed")
            self.send_response(403)
            self.end_headers()

    def do_POST(self):
        """Handle incoming WhatsApp messages."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        self.send_response(200)
        self.end_headers()

        try:
            payload = json.loads(body)
            self._process_webhook(payload)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("Failed to parse webhook payload: %s", e)

    def _process_webhook(self, payload: dict):
        """Extract messages from the WhatsApp webhook payload."""
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    if msg.get("type") != "text":
                        logger.debug("Skipping non-text message type: %s", msg.get("type"))
                        continue

                    text = msg.get("text", {}).get("body", "")
                    if not text:
                        continue

                    ts = int(msg.get("timestamp", 0))
                    incoming = IncomingMessage(
                        message_id=msg["id"],
                        text=text,
                        chat_identifier=msg["from"],  # sender's phone number
                        timestamp=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc),
                        transport="whatsapp",
                    )
                    self.server.message_queue.put(incoming)
                    logger.info(
                        "WhatsApp message from %s: %s",
                        incoming.chat_identifier, text[:80],
                    )


@register_transport("whatsapp")
class WhatsAppTransport(MessageTransport):
    """Sends and receives messages via the WhatsApp Business Cloud API."""

    GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        verify_token: Optional[str] = None,
        webhook_port: Optional[int] = None,
    ):
        self.access_token = access_token or getattr(config, "WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = phone_number_id or getattr(config, "WHATSAPP_PHONE_NUMBER_ID", "")
        self.verify_token = verify_token or getattr(config, "WHATSAPP_VERIFY_TOKEN", "interoperbot")
        self.webhook_port = webhook_port or getattr(config, "WHATSAPP_WEBHOOK_PORT", 8443)

        self._message_queue: Queue = Queue()
        self._webhook_server: Optional[HTTPServer] = None
        self._webhook_thread: Optional[threading.Thread] = None
        self._last_message_id: Optional[str] = None

        if not self.access_token:
            logger.warning("WHATSAPP_ACCESS_TOKEN not set — sending will fail")
        if not self.phone_number_id:
            logger.warning("WHATSAPP_PHONE_NUMBER_ID not set — sending will fail")

    @property
    def name(self) -> str:
        return "whatsapp"

    def start_webhook(self):
        """Start the webhook HTTP server in a background thread."""
        if self._webhook_server:
            return

        server = HTTPServer(("0.0.0.0", self.webhook_port), WhatsAppWebhookHandler)
        server.message_queue = self._message_queue
        server.verify_token = self.verify_token

        self._webhook_server = server
        self._webhook_thread = threading.Thread(
            target=server.serve_forever, daemon=True,
        )
        self._webhook_thread.start()
        logger.info("WhatsApp webhook listening on port %d", self.webhook_port)

    def stop_webhook(self):
        """Stop the webhook HTTP server."""
        if self._webhook_server:
            self._webhook_server.shutdown()
            self._webhook_server = None
            self._webhook_thread = None
            logger.info("WhatsApp webhook stopped")

    def get_initial_state(self) -> dict:
        """Return initial state. Webhook-based, so state is just a marker."""
        self.start_webhook()
        return {"last_message_id": None}

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
        """Send a text message via the WhatsApp Business Cloud API."""
        if not self.access_token or not self.phone_number_id:
            logger.error("WhatsApp not configured — cannot send message")
            return False

        url = f"{self.GRAPH_API_BASE}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": text},
        }

        try:
            result = _api_post(url, headers, data)
            msg_id = result.get("messages", [{}])[0].get("id", "unknown")
            logger.info("Sent WhatsApp reply to %s (msg_id=%s)", recipient, msg_id)
            return True
        except Exception as e:
            logger.error("WhatsApp API error sending to %s: %s", recipient, e)
            return False

    def send_template_message(
        self, recipient: str, template_name: str, language_code: str = "en_US",
    ) -> bool:
        """Send a template message (required for initiating conversations)."""
        if not self.access_token or not self.phone_number_id:
            logger.error("WhatsApp not configured — cannot send template")
            return False

        url = f"{self.GRAPH_API_BASE}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }

        try:
            result = _api_post(url, headers, data)
            logger.info("Sent WhatsApp template '%s' to %s", template_name, recipient)
            return True
        except Exception as e:
            logger.error("WhatsApp template error for %s: %s", recipient, e)
            return False

    def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read (sends blue ticks)."""
        if not self.access_token or not self.phone_number_id:
            return False

        url = f"{self.GRAPH_API_BASE}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        data = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            _api_post(url, headers, data)
            return True
        except Exception:
            return False
