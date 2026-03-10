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
    for mod in ["config", "ai", "imessage", "store", "attachments",
                "transport", "core", "whatsapp"]:
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


def test_extract_attributed_text_basic():
    """_extract_attributed_text extracts text from a synthetic typedstream blob."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import _extract_attributed_text

    # Simulate a typedstream blob: binary header + readable text + binary metadata
    header = b'\x04\x0b\x73\x74\x72\x65\x61\x6d\x74\x79\x70\x65\x64'  # "streamtyped"
    padding = b'\x81\x00\x01\x02'
    text_content = b'Hi Mike, thanks for your time. My clients are David and Marcela.'
    trailer = b'\x00\x86\x84\x00\x8c\x04\x01'

    blob = header + padding + text_content + trailer
    result = _extract_attributed_text(blob)
    assert result is not None
    assert "Hi Mike" in result
    assert "David and Marcela" in result


def test_extract_attributed_text_none():
    """_extract_attributed_text handles None and empty blobs."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import _extract_attributed_text

    assert _extract_attributed_text(None) is None
    assert _extract_attributed_text(b'') is None
    # Pure binary with no printable runs
    assert _extract_attributed_text(b'\x00\x01\x02\x03') is None


def test_extract_attributed_text_prefers_text_over_metadata():
    """_extract_attributed_text skips Apple class name runs."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import _extract_attributed_text

    # Blob where the longest run is a metadata class name
    metadata_run = b'NSMutableAttributedString'
    actual_text = b'Hello from iMessage!'
    blob = b'\x00' + metadata_run + b'\x00\x04\x02' + actual_text + b'\x00'
    result = _extract_attributed_text(blob)
    assert result is not None
    assert "Hello from iMessage" in result


def test_attachment_dataclass():
    """Attachment dataclass constructs correctly."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import Attachment
    att = Attachment(
        rowid=42,
        mime_type="image/heic",
        filename="/Users/test/Library/Messages/Attachments/ab/photo.heic",
        transfer_name="photo.heic",
        total_bytes=3_200_000,
        media_type="image",
    )
    assert att.rowid == 42
    assert att.media_type == "image"
    assert att.total_bytes == 3_200_000


def test_classify_media_type():
    """_classify_media_type maps MIME types to broad categories."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import _classify_media_type
    assert _classify_media_type("image/heic") == "image"
    assert _classify_media_type("image/jpeg") == "image"
    assert _classify_media_type("audio/x-m4a") == "audio"
    assert _classify_media_type("video/quicktime") == "video"
    assert _classify_media_type("application/pdf") == "document"
    assert _classify_media_type(None) == "document"


def test_expand_attachment_path():
    """_expand_attachment_path replaces ~/ with home directory."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import _expand_attachment_path
    from pathlib import Path
    result = _expand_attachment_path("~/Library/Messages/Attachments/ab/photo.heic")
    assert result.startswith(str(Path.home()))
    assert "~/Library" not in result
    assert _expand_attachment_path(None) is None


def test_incoming_message_with_attachments():
    """IncomingMessage can hold attachments."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import IncomingMessage, Attachment
    from datetime import datetime, timezone
    msg = IncomingMessage(
        rowid=1, text="Check this out",
        chat_identifier="+15551234567",
        timestamp=datetime.now(timezone.utc),
        attachments=[
            Attachment(rowid=10, mime_type="image/jpeg",
                       filename="/tmp/photo.jpg", transfer_name="photo.jpg",
                       total_bytes=1024, media_type="image"),
        ],
    )
    assert len(msg.attachments) == 1
    assert msg.attachments[0].media_type == "image"


def test_incoming_message_attachment_only():
    """Attachment-only messages have empty text."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import IncomingMessage, Attachment
    from datetime import datetime, timezone
    msg = IncomingMessage(
        rowid=1, text="",
        chat_identifier="+15551234567",
        timestamp=datetime.now(timezone.utc),
        attachments=[
            Attachment(rowid=10, mime_type="image/heic",
                       filename="/tmp/photo.heic", transfer_name="photo.heic",
                       total_bytes=5_000_000, media_type="image"),
        ],
    )
    assert msg.text == ""
    assert len(msg.attachments) == 1


def test_human_size():
    """_human_size formats byte counts readably."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from attachments import _human_size
    assert _human_size(500) == "500 B"
    assert _human_size(1024) == "1.0 KB"
    assert _human_size(2_500_000) == "2.4 MB"
    assert _human_size(1_500_000_000) == "1.4 GB"


def test_enrich_attachment_missing_file():
    """enrich_attachment returns metadata-only for missing files."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from attachments import enrich_attachment
    from imessage import Attachment
    att = Attachment(
        rowid=1, mime_type="image/jpeg",
        filename="/nonexistent/photo.jpg",
        transfer_name="photo.jpg",
        total_bytes=1024, media_type="image",
    )
    desc = enrich_attachment(att, timeout=5)
    assert "photo.jpg" in desc
    assert "file unavailable" in desc


def test_enrich_attachment_no_filename():
    """enrich_attachment handles None filename."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from attachments import enrich_attachment
    from imessage import Attachment
    att = Attachment(
        rowid=1, mime_type="image/jpeg",
        filename=None, transfer_name="photo.jpg",
        total_bytes=2048, media_type="image",
    )
    desc = enrich_attachment(att, timeout=5)
    assert "photo.jpg" in desc
    assert "file unavailable" in desc


def test_config_attachment_defaults():
    """Attachment config defaults are sensible."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    import config
    assert config.ENABLE_ATTACHMENTS is True
    assert config.ATTACHMENT_TIMEOUT == 30
    assert config.MAX_VIDEO_FRAMES == 30


def test_describe_video_empty_frames():
    """describe_video returns empty string when given no frames."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from ai import ClaudeAssistant

    a = ClaudeAssistant()
    result = a.describe_video([], [], "unknown")
    assert isinstance(result, str)
    assert result == ""


def test_describe_storyboard_panels_empty():
    """describe_storyboard_panels returns empty list for no panels."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from ai import ClaudeAssistant

    a = ClaudeAssistant()
    result = a.describe_storyboard_panels([], "unknown")
    assert result == []


def test_storyboard_align_frames():
    """Frame-to-speech alignment picks nearest frame by midpoint."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from storyboard import align_frames_to_segments

    frames = [
        {"path": "/tmp/f1.jpg", "time": 0.0},
        {"path": "/tmp/f2.jpg", "time": 1.0},
        {"path": "/tmp/f3.jpg", "time": 2.0},
        {"path": "/tmp/f4.jpg", "time": 3.0},
        {"path": "/tmp/f5.jpg", "time": 4.0},
    ]
    segments = [
        {"text": "Hello there", "start": 0.0, "end": 0.6},   # midpoint 0.3 → f1
        {"text": "How are you", "start": 2.8, "end": 3.5},    # midpoint 3.15 → f4
    ]

    panels = align_frames_to_segments(frames, segments)

    # Should have speech panels + some silence panels
    speech_panels = [p for p in panels if p["transcript"] != "[silence]"]
    assert len(speech_panels) == 2
    assert speech_panels[0]["frame"]["time"] == 0.0   # nearest to 0.3
    assert speech_panels[1]["frame"]["time"] == 3.0   # nearest to 3.15

    # All panels sorted by timestamp
    times = [p["timestamp"] for p in panels]
    assert times == sorted(times)


def test_storyboard_align_no_segments():
    """Alignment with no speech creates silence panels from frames."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from storyboard import align_frames_to_segments

    frames = [
        {"path": "/tmp/f1.jpg", "time": 0.0},
        {"path": "/tmp/f2.jpg", "time": 1.0},
        {"path": "/tmp/f3.jpg", "time": 2.0},
    ]
    panels = align_frames_to_segments(frames, [])
    assert len(panels) > 0
    assert all(p["transcript"] == "[silence]" for p in panels)


def test_storyboard_align_empty():
    """Alignment with no frames returns empty."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from storyboard import align_frames_to_segments
    assert align_frames_to_segments([], []) == []


def test_status_json_valid():
    """status.json exists and is valid JSON."""
    import json
    from pathlib import Path

    status_path = Path("/Users/mikeudem/Projects/InteroperBot/status.json")
    if status_path.exists():
        data = json.loads(status_path.read_text())
        assert "project" in data
        assert data["project"] == "InteroperBot"


# --- Transport layer tests ---


def test_transport_abc_requires_send():
    """Transport ABC cannot be instantiated without send()."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import Transport
    import pytest
    with pytest.raises(TypeError):
        Transport()


def test_message_attachment_dataclass():
    """MessageAttachment constructs correctly."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import MessageAttachment
    att = MessageAttachment(
        mime_type="image/jpeg",
        filename="photo.jpg",
        local_path="/tmp/photo.jpg",
        size_bytes=1024,
        media_type="image",
    )
    assert att.media_type == "image"
    assert att.size_bytes == 1024
    assert att.local_path == "/tmp/photo.jpg"


def test_transport_incoming_message():
    """Transport-level IncomingMessage constructs correctly."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from transport import IncomingMessage
    from datetime import datetime, timezone
    msg = IncomingMessage(
        transport="test",
        sender="+15551234567",
        text="hello",
        timestamp=datetime.now(timezone.utc),
    )
    assert msg.transport == "test"
    assert msg.sender == "+15551234567"
    assert msg.attachments == []


def test_router_handle_message(tmp_path):
    """MessageRouter processes a message through the full flow."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from core import MessageRouter
    from transport import Transport, IncomingMessage
    from store import SQLiteStore
    from datetime import datetime, timezone

    class MockTransport(Transport):
        name = "mock"
        sent = []
        def send(self, recipient, text):
            self.sent.append((recipient, text))
            return True

    class MockAssistant:
        def respond(self, history, session_id=None):
            return "mock reply", "session-123"

    store = SQLiteStore(db_path=str(tmp_path / "test.db"))
    router = MessageRouter(store, MockAssistant())
    mock = MockTransport()
    router.register(mock)

    msg = IncomingMessage(
        transport="mock",
        sender="+15551234567",
        text="hello",
        timestamp=datetime.now(timezone.utc),
    )
    reply = router.handle_message(msg)
    assert reply == "mock reply"
    assert len(mock.sent) == 1
    assert mock.sent[0] == ("+15551234567", "mock reply")


def test_router_stores_messages(tmp_path):
    """MessageRouter logs user and assistant messages in store."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from core import MessageRouter
    from transport import Transport, IncomingMessage
    from store import SQLiteStore
    from datetime import datetime, timezone

    class NoopTransport(Transport):
        name = "noop"
        def send(self, recipient, text):
            return True

    class MockAssistant:
        def respond(self, history, session_id=None):
            return "reply", None

    store = SQLiteStore(db_path=str(tmp_path / "test.db"))
    router = MessageRouter(store, MockAssistant())
    router.register(NoopTransport())

    msg = IncomingMessage(
        transport="noop",
        sender="test@example.com",
        text="hi",
        timestamp=datetime.now(timezone.utc),
    )
    router.handle_message(msg)

    cid = store.get_or_create_contact("test@example.com")
    history = store.get_history(cid)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_config_whatsapp_defaults():
    """WhatsApp config defaults are sensible."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    import config
    assert config.WHATSAPP_ENABLED is False
    assert config.WHATSAPP_BRIDGE_PORT == 3456
    assert config.WEB_ENABLED is True
    assert config.WEB_PORT == 8000


def test_enrich_message_attachment_missing_file():
    """enrich_message_attachment returns metadata-only for missing files."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from attachments import enrich_message_attachment
    from transport import MessageAttachment
    att = MessageAttachment(
        mime_type="image/jpeg",
        filename="photo.jpg",
        local_path="/nonexistent/photo.jpg",
        size_bytes=1024,
        media_type="image",
    )
    desc = enrich_message_attachment(att, timeout=5)
    assert "photo.jpg" in desc
    assert "file unavailable" in desc


def test_imessage_transport_is_transport():
    """iMessageTransport implements Transport ABC."""
    sys.path.insert(0, "/Users/mikeudem/Projects/InteroperBot")
    from imessage import iMessageTransport
    from transport import Transport
    assert issubclass(iMessageTransport, Transport)
    assert iMessageTransport.name == "imessage"
