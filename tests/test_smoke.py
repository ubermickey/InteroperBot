"""Smoke tests for InteroperBot — run without API key or Messages DB."""
import subprocess
import sys
import importlib

def test_bot_help():
    """bot.py --help exits cleanly."""
    result = subprocess.run(
        [sys.executable, "bot.py", "--help"],
        capture_output=True, text=True, timeout=10,
        cwd="/Users/mikeudem/Projects/InteroperBot"
    )
    assert result.returncode == 0
    assert "InteroperBot" in result.stdout

def test_imports():
    """All modules import without error."""
    for mod in ["config", "ai", "imessage", "store", "transport", "whatsapp", "waha"]:
        importlib.import_module(mod)

def test_store_roundtrip(tmp_path):
    """SQLiteStore can create, log, and retrieve messages."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from store import SQLiteStore

    db = str(tmp_path / "test.db")
    s = SQLiteStore(db_path=db)

    cid = s.get_or_create_contact("+15551234567")
    assert isinstance(cid, int)

    s.log_message(cid, "user", "hello")
    s.log_message(cid, "assistant", "hi there")

    history = s.get_history(cid)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

def test_store_metadata(tmp_path):
    """Metadata round-trip works."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from store import SQLiteStore

    db = str(tmp_path / "test.db")
    s = SQLiteStore(db_path=db)
    cid = s.get_or_create_contact("test@example.com")

    assert s.get_metadata(cid, "key1") is None
    s.set_metadata(cid, "key1", "value1")
    assert s.get_metadata(cid, "key1") == "value1"

def test_store_clear(tmp_path):
    """Clear history works."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from store import SQLiteStore

    db = str(tmp_path / "test.db")
    s = SQLiteStore(db_path=db)
    cid = s.get_or_create_contact("+15559999999")
    s.log_message(cid, "user", "msg1")
    s.log_message(cid, "assistant", "msg2")

    s.clear_history(cid)
    assert s.get_history(cid) == []

def test_apple_date_conversion():
    """Apple date conversion produces reasonable timestamps."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import _apple_date_to_datetime
    from datetime import datetime, timezone

    # 0 should return current time
    dt = _apple_date_to_datetime(0)
    assert dt.tzinfo is not None

    # A known timestamp (roughly 2024-01-01 in Apple nanoseconds)
    apple_ns = 725846400 * 1_000_000_000  # Jan 1, 2024 in seconds since 2001
    dt = _apple_date_to_datetime(apple_ns)
    assert dt.year == 2024
    assert dt.month == 1

def test_assistant_respond_returns_tuple():
    """ClaudeAssistant.respond() returns (reply, session_id) tuple."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from ai import ClaudeAssistant

    a = ClaudeAssistant()
    # Empty messages → error tuple
    result = a.respond([])
    assert isinstance(result, tuple)
    assert len(result) == 2
    reply, sid = result
    assert isinstance(reply, str)
    assert sid is None

def test_assistant_format_history():
    """_format_history produces User/Assistant prefixed lines."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from ai import ClaudeAssistant

    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "bye"},
    ]
    out = ClaudeAssistant._format_history(msgs)
    assert "User: hello" in out
    assert "Assistant: hi" in out
    # Last message excluded (it's the "latest" in respond())
    assert "bye" not in out

def test_store_session_id_roundtrip(tmp_path):
    """cli_session_id can be stored and retrieved via metadata."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from store import SQLiteStore

    db = str(tmp_path / "test.db")
    s = SQLiteStore(db_path=db)
    cid = s.get_or_create_contact("session-test@example.com")

    assert s.get_metadata(cid, "cli_session_id") is None
    s.set_metadata(cid, "cli_session_id", "abc-123-def")
    assert s.get_metadata(cid, "cli_session_id") == "abc-123-def"

    # Overwrite works (upsert)
    s.set_metadata(cid, "cli_session_id", "new-session-456")
    assert s.get_metadata(cid, "cli_session_id") == "new-session-456"

def test_pending_delivery_lifecycle(tmp_path):
    """Pending deliveries can be created, queried, updated, and cleared."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from store import SQLiteStore

    db = str(tmp_path / "test.db")
    s = SQLiteStore(db_path=db)

    # Add a pending delivery
    did = s.add_pending_delivery("+15551234567", "Hello!", outgoing_rowid=100)
    assert isinstance(did, int)

    # Retrieve pending
    pending = s.get_pending_deliveries()
    assert len(pending) == 1
    assert pending[0]["chat_identifier"] == "+15551234567"
    assert pending[0]["content"] == "Hello!"
    assert pending[0]["attempts"] == 1

    # Update: bump attempts and add service
    s.update_delivery(did, attempts=2, services_tried="iMessage,SMS")
    pending = s.get_pending_deliveries()
    assert pending[0]["attempts"] == 2
    assert "SMS" in pending[0]["services_tried"]

    # Mark delivered → disappears from pending
    s.update_delivery(did, status="delivered")
    assert s.get_pending_deliveries() == []
    assert s.clear_delivered() == 1

def test_status_json_valid():
    """status.json exists and is valid JSON."""
    import json
    from pathlib import Path

    status_path = Path("/Users/mikeudem/Projects/InteroperBot/status.json")
    if status_path.exists():
        data = json.loads(status_path.read_text())
        assert "project" in data
        assert data["project"] == "InteroperBot"


# --- Transport abstraction tests ---

def test_transport_abc():
    """MessageTransport ABC has required abstract methods."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import MessageTransport, IncomingMessage
    import inspect

    # Verify ABC can't be instantiated directly
    try:
        MessageTransport()
        assert False, "Should not be able to instantiate ABC"
    except TypeError:
        pass

    # Verify IncomingMessage dataclass fields
    fields = {f.name for f in IncomingMessage.__dataclass_fields__.values()}
    assert fields == {"message_id", "text", "chat_identifier", "timestamp", "transport"}


def test_transport_registry():
    """Built-in transports register correctly."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import TRANSPORT_REGISTRY, _load_builtin_transports

    _load_builtin_transports()
    assert "imessage" in TRANSPORT_REGISTRY
    assert "whatsapp" in TRANSPORT_REGISTRY
    assert "waha" in TRANSPORT_REGISTRY


def test_create_transports_factory():
    """create_transports factory instantiates correct transport types."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import create_transports

    # Single transport
    transports = create_transports("whatsapp")
    assert len(transports) == 1
    assert transports[0].name == "whatsapp"

    # Multiple transports
    transports = create_transports("imessage,whatsapp")
    assert len(transports) == 2
    names = {t.name for t in transports}
    assert names == {"imessage", "whatsapp"}

    # Unknown transport raises
    try:
        create_transports("telegram")
        assert False, "Should raise ValueError for unknown transport"
    except ValueError as e:
        assert "telegram" in str(e)


def test_whatsapp_transport_offline():
    """WhatsAppTransport can be instantiated without API credentials."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from whatsapp import WhatsAppTransport

    t = WhatsAppTransport(access_token="", phone_number_id="")
    assert t.name == "whatsapp"
    assert t.supports_delivery_tracking() is False
    assert t.get_service_fallback_order() == ["whatsapp"]

    # send_message fails gracefully without credentials
    assert t.send_message("+15551234567", "test") is False


def test_whatsapp_webhook_parsing():
    """WhatsApp webhook handler correctly parses Meta webhook payloads."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from queue import Queue
    from whatsapp import WhatsAppWebhookHandler
    from transport import IncomingMessage

    # Create a mock payload matching Meta's webhook format
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "wamid.abc123",
                        "from": "+15551234567",
                        "timestamp": "1704067200",  # 2024-01-01 00:00:00 UTC
                        "type": "text",
                        "text": {"body": "Hello from WhatsApp!"},
                    }]
                }
            }]
        }]
    }

    # Create a handler instance and process the payload
    queue = Queue()

    # Use the internal _process_webhook method via a minimal mock
    class MockHandler(WhatsAppWebhookHandler):
        def __init__(self):
            # Skip real HTTP init
            self.server = type("Server", (), {"message_queue": queue, "verify_token": "test"})()

    handler = MockHandler()
    handler._process_webhook(payload)

    assert not queue.empty()
    msg = queue.get()
    assert isinstance(msg, IncomingMessage)
    assert msg.message_id == "wamid.abc123"
    assert msg.chat_identifier == "+15551234567"
    assert msg.text == "Hello from WhatsApp!"
    assert msg.transport == "whatsapp"
    assert msg.timestamp.year == 2024


def test_waha_transport_offline():
    """WAHATransport can be instantiated without a running WAHA server."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from waha import WAHATransport

    t = WAHATransport(api_url="http://localhost:3000", session_name="test")
    assert t.name == "waha"
    assert t.supports_delivery_tracking() is False
    assert t.get_service_fallback_order() == ["waha"]

    # send_message fails gracefully when WAHA is not running
    assert t.send_message("+15551234567", "test") is False


def test_waha_jid_conversion():
    """JID <-> phone number conversion works correctly."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from waha import _jid_to_phone, _phone_to_jid

    # JID to phone
    assert _jid_to_phone("1234567890@c.us") == "+1234567890"
    assert _jid_to_phone("+1234567890@c.us") == "+1234567890"

    # Phone to JID
    assert _phone_to_jid("+1234567890") == "1234567890@c.us"
    assert _phone_to_jid("1234567890") == "1234567890@c.us"
    assert _phone_to_jid("+1-234-567-890") == "1234567890@c.us"


def test_waha_webhook_parsing():
    """WAHA webhook handler correctly parses incoming message events."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from queue import Queue
    from waha import WAHAWebhookHandler
    from transport import IncomingMessage

    # Create a mock WAHA webhook payload
    payload = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "true_1234567890@c.us_ABCDEF",
            "timestamp": 1704067200,  # 2024-01-01 00:00:00 UTC
            "from": "1234567890@c.us",
            "to": "0987654321@c.us",
            "body": "Hello from WAHA!",
            "fromMe": False,
            "hasMedia": False,
        },
    }

    queue = Queue()

    class MockHandler(WAHAWebhookHandler):
        def __init__(self):
            self.server = type("Server", (), {"message_queue": queue})()

    handler = MockHandler()
    handler._process_webhook(payload)

    assert not queue.empty()
    msg = queue.get()
    assert isinstance(msg, IncomingMessage)
    assert msg.message_id == "true_1234567890@c.us_ABCDEF"
    assert msg.chat_identifier == "+1234567890"
    assert msg.text == "Hello from WAHA!"
    assert msg.transport == "waha"
    assert msg.timestamp.year == 2024


def test_waha_webhook_skips_outgoing():
    """WAHA webhook handler skips messages sent by us (fromMe=True)."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from queue import Queue
    from waha import WAHAWebhookHandler

    payload = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "outgoing_msg_123",
            "timestamp": 1704067200,
            "from": "0987654321@c.us",
            "to": "1234567890@c.us",
            "body": "This is my own message",
            "fromMe": True,
        },
    }

    queue = Queue()

    class MockHandler(WAHAWebhookHandler):
        def __init__(self):
            self.server = type("Server", (), {"message_queue": queue})()

    handler = MockHandler()
    handler._process_webhook(payload)

    assert queue.empty(), "Outgoing messages should be skipped"


def test_waha_transport_registry():
    """WAHA transport registers in the transport registry."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import TRANSPORT_REGISTRY, _load_builtin_transports

    _load_builtin_transports()
    assert "waha" in TRANSPORT_REGISTRY


def test_waha_create_transport():
    """create_transports factory can instantiate WAHA transport."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import create_transports

    transports = create_transports("waha")
    assert len(transports) == 1
    assert transports[0].name == "waha"


def test_imessage_transport_implements_abc():
    """iMessageTransport properly implements MessageTransport ABC."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import iMessageTransport
    from transport import MessageTransport

    assert issubclass(iMessageTransport, MessageTransport)
    t = iMessageTransport.__new__(iMessageTransport)
    assert t.name == "imessage"
    assert t.supports_delivery_tracking() is True
    assert t.get_service_fallback_order() == ["iMessage", "SMS"]
