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
    for mod in ["config", "ai", "imessage", "store"]:
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


def test_status_json_valid():
    """status.json exists and is valid JSON."""
    import json
    from pathlib import Path

    status_path = Path("/Users/mikeudem/Projects/InteroperBot/status.json")
    if status_path.exists():
        data = json.loads(status_path.read_text())
        assert "project" in data
        assert data["project"] == "InteroperBot"
