# CLAUDE.md — InteroperBot

## Project Overview

InteroperBot is an iMessage-to-Claude bot for macOS. It monitors incoming iMessages, sends them to the Claude CLI, and replies via iMessage. No API key needed — it uses your Claude subscription via the `claude` command. CLI sessions are the primary persistent memory (`--resume`); SQLiteStore logs every exchange as backup/audit.

## Architecture

```
iMessage in → Transport (imessage.py) → Store (store.py) → AI (ai.py → claude CLI) → Store → Transport → iMessage out
```

4-layer stack:
- **Layer 1 — Transport** (`imessage.py`): Reads macOS Messages DB (read-only), sends via AppleScript
- **Layer 2 — Persistence** (`store.py`): `MessageStore` ABC + `SQLiteStore` default — intrasession log + backup
- **Layer 3 — Intelligence** (`ai.py`): `ClaudeAssistant` calls `claude -p` with `--resume` for session persistence (no API key)
- **Layer 4 — Orchestration** (`bot.py`): CLI, signal handling, polling loop

### Memory Model — CLI Session Persistence

The AI layer uses CLI sessions as the primary memory:
- **First message**: `claude -p "msg" --output-format json` → captures `session_id`
- **Subsequent messages**: `claude -p "msg" --resume <session_id> --output-format json` → CLI natively maintains full context
- **Fallback**: If a session expires or corrupts, history is rebuilt from SQLiteStore and a fresh session starts
- **No API key required** — uses your existing Claude subscription
- **No SDK dependency** — uses `~/.local/bin/claude` (overridable via `CLAUDE_CLI` env var)

## Commands

```bash
# Run the bot
python bot.py

# Web chat UI
python web.py                          # http://localhost:8000

# Development / testing
python bot.py --dry-run        # Print replies to stdout (no iMessage send)
python bot.py --reset          # Clear all conversation history
python bot.py --status         # Output JSON status for dashboard
python bot.py --help           # Show CLI help

# Tests
python -m pytest tests/ -v                # Smoke tests (offline)
python tests/probe_messages_db.py         # Validate Messages DB access

# Dashboard
open dashboard.html                       # Mission Control UI
```

## Key Paths

| Path | Purpose |
|---|---|
| `bot.py` | Entry point (iMessage bot) |
| `web.py` | Web chat interface (FastAPI) |
| `ai.py` | Claude CLI subprocess wrapper |
| `store.py` | Storage abstraction (MessageStore ABC + SQLiteStore) |
| `imessage.py` | iMessage transport (read chat.db + AppleScript send) |
| `config.py` | Environment variable configuration |
| `~/.interoperbot/conversations.db` | Conversation database (auto-created) |
| `~/Library/Messages/chat.db` | macOS Messages database (read-only) |
| `dashboard.html` | Mission Control dashboard |
| `status.json` | Dashboard data file |
| `index/` | v4 framework documentation |
| `tests/` | Test infrastructure |

## Environment Variables

All configured via `.env` file (all optional — no API key needed):

| Variable | Required | Default |
|---|---|---|
| `SYSTEM_PROMPT` | No | Helpful assistant prompt |
| `ALLOWED_CONTACTS` | No | All contacts |
| `POLL_INTERVAL` | No | `2` seconds |
| `MAX_HISTORY` | No | `50` messages |
| `CLI_TIMEOUT` | No | `120` seconds |
| `DB_PATH` | No | `~/.interoperbot/conversations.db` |
| `CLAUDE_CLI` | No | `~/.local/bin/claude` |

## Conventions

- **Claude CLI, not SDK**: AI layer calls `claude -p` subprocess with `--resume` for session persistence. No API key, no `anthropic` package.
- **Session-based memory**: CLI sessions own conversation context; SQLiteStore logs for backup/recovery.
- **Layers don't skip**: Transport talks to Store, Store talks to AI. No layer skipping.
- **Messages DB is read-only**: Never write to Apple's chat.db. Use AppleScript for sends.
- **Privacy**: Truncate message content to 80 chars in logs.
- **Testing**: All smoke tests run offline. Use `tmp_path` for DB tests.
- **Storage extension**: Implement `MessageStore` ABC for new backends.
- **Diagnostic format**: `Symptom -> Fix -> Result` for all issue documentation.

## Prerequisites

- macOS with Messages.app signed into iMessage
- Python 3.10+
- Claude CLI installed (`npm install -g @anthropic-ai/claude-code`) and authenticated
- Terminal granted Full Disk Access (System Settings > Privacy & Security)
