# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InteroperBot is a multi-transport messaging bot powered by Claude CLI for macOS. Messages from iMessage, WhatsApp, and Web all route through a single `MessageRouter` (core.py) that handles the Store → AI → Store flow. No API key — uses your Claude subscription via the `claude` CLI binary with `--resume` for session persistence.

## Commands

```bash
# Run the bot (iMessage + web UI by default)
source .venv/bin/activate
python bot.py

# Standalone web chat
python web.py                          # http://localhost:8000

# WhatsApp
python bot.py --setup-whatsapp         # Bootstrap bridge, scan QR code
WHATSAPP_ENABLED=true python bot.py    # Run with WhatsApp active

# Other bot flags
python bot.py --dry-run                # Print replies to stdout (no sends)
python bot.py --reset                  # Clear all conversation history
python bot.py --status                 # JSON status for dashboard

# Tests (36 smoke tests, all offline, no API key or Messages DB needed)
python -m pytest tests/ -v
python -m pytest tests/test_smoke.py::test_router_handle_message -v   # single test

# Validate Messages DB access (diagnostic)
python tests/probe_messages_db.py
```

## Architecture

```
                ┌── iMessageTransport (poll chat.db)
                │
MessageRouter ──┼── WhatsAppTransport (Baileys bridge)
(core.py)       │
                ├── WebTransport (FastAPI)
                │
                └── [future transports]
        ↕               ↕
    SQLiteStore    ClaudeAssistant
    (store.py)     (ai.py → claude CLI)
```

**`Transport` ABC** (`transport.py`): Pull transports override `poll()`, push transports override `start()`. Transport-agnostic types: `IncomingMessage`, `MessageAttachment`.

**`MessageRouter`** (`core.py`): Single `handle_message()` flow for all transports — receive → store → enrich attachments → Claude CLI → store → send. No transport should duplicate this flow.

**AI layer** (`ai.py`): `ClaudeAssistant` calls `claude -p` subprocess with `--resume <session_id>` and `--output-format json`. Session IDs stored per-contact in `contact_metadata` table. Falls back to history reconstruction if a session expires.

**iMessage specifics** (`imessage.py`): Opens `chat.db` in `?mode=ro` — never writes to Apple's DB. Sends via AppleScript. Handles delivery tracking with iMessage→SMS fallback. The `attributedBody` column (NSAttributedString binary) contains 94.5% of messages; the `text` column alone is insufficient.

**Attachment pipeline** (`attachments.py`): Enriches images (Vision framework labels + OCR), audio (SFSpeechRecognizer), and video (ffmpeg frames → Claude reads frames via Read tool). Compiled Swift helpers at `helpers/describe_image` and `helpers/transcribe`; bash helper at `helpers/extract_keyframes.sh`.

**WhatsApp bridge** (`helpers/wa-bridge/`): Node.js subprocess running Baileys. HTTP on `127.0.0.1:3456` for sends, WebSocket for incoming messages. Auth credentials in `helpers/wa-bridge/auth/` (gitignored).

## Key Conventions

- **Claude CLI, not SDK**: AI layer calls `~/.local/bin/claude` subprocess. No `anthropic` package, no API key. `config.CLAUDE_CLI` resolves the binary path.
- **Messages DB is read-only**: Never write to `~/Library/Messages/chat.db`. Use AppleScript for sends.
- **Privacy**: Truncate message content to 80 chars in all log output.
- **Two IncomingMessage types coexist**: `imessage.IncomingMessage` (iMessage-specific with `rowid`, `chat_identifier`) and `transport.IncomingMessage` (transport-agnostic with `transport`, `sender`). The iMessage transport's `poll()` converts between them.
- **Two attachment types coexist**: `imessage.Attachment` (legacy, used by `enrich_attachment()`) and `transport.MessageAttachment` (used by `enrich_message_attachment()`). Both route to the same enrichment helpers.
- **Diagnostic format**: `Symptom → Fix → Result` for issue documentation (see `research/` directory).
- Use `python3` outside the venv (`python` is not on PATH without `.venv` activation).
- `status.json`, `helpers/wa-bridge/auth/`, and `helpers/wa-bridge/node_modules/` are gitignored runtime data.

## Environment Variables

All optional (configured via `.env`):

| Variable | Default | Notes |
|---|---|---|
| `CLAUDE_CLI` | `~/.local/bin/claude` | Path to Claude CLI binary |
| `ALLOWED_CONTACTS` | (all) | Comma-separated phone numbers/emails |
| `POLL_INTERVAL` | `2` | Seconds between chat.db polls |
| `CLI_TIMEOUT` | `120` | Claude CLI subprocess timeout |
| `WHATSAPP_ENABLED` | `false` | Enable WhatsApp transport |
| `WEB_ENABLED` | `true` | Enable web UI (embedded in bot.py) |
| `WEB_PORT` | `8000` | Web UI port |
| `WHATSAPP_BRIDGE_PORT` | `3456` | Baileys bridge port |

## Testing

Tests are in `tests/test_smoke.py` — all run offline with no API key, no Messages DB, no network. Use `tmp_path` for any test that needs a SQLiteStore. Mock `ClaudeAssistant` with a class that has `respond(history, session_id=None)` returning `(reply_text, session_id)`.

## Prerequisites

- macOS with Messages.app signed into iMessage
- Python 3.10+ with venv at `.venv/`
- Claude CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Terminal granted Full Disk Access (System Settings > Privacy & Security)
- Node.js ≥18 for WhatsApp only (`brew install node`)
