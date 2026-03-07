# CLAUDE.md — InteroperBot

## Project Overview

InteroperBot is an iMessage-to-Claude bot for macOS. It monitors incoming iMessages, sends them to the Anthropic API, and replies via iMessage. Conversations persist in a local SQLite database.

## Architecture

```
iMessage in → Transport (imessage.py) → Store (store.py) → AI (ai.py) → Store → Transport → iMessage out
```

4-layer stack:
- **Layer 1 — Transport** (`imessage.py`): Reads macOS Messages DB (read-only), sends via AppleScript
- **Layer 2 — Persistence** (`store.py`): `MessageStore` ABC + `SQLiteStore` default
- **Layer 3 — Intelligence** (`ai.py`): `ClaudeAssistant` wrapping Anthropic API
- **Layer 4 — Orchestration** (`bot.py`): CLI, signal handling, polling loop

## Commands

```bash
# Run the bot
python bot.py

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

# Launch (double-click in Finder)
# launch.command
```

## Key Paths

| Path | Purpose |
|---|---|
| `bot.py` | Entry point |
| `ai.py` | Claude API wrapper |
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

All configured via `.env` file:

| Variable | Required | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-20250514` |
| `SYSTEM_PROMPT` | No | Helpful assistant prompt |
| `ALLOWED_CONTACTS` | No | All contacts |
| `POLL_INTERVAL` | No | `2` seconds |
| `MAX_HISTORY` | No | `50` messages |
| `DB_PATH` | No | `~/.interoperbot/conversations.db` |

## Conventions

- **Layers don't skip**: Transport talks to Store, Store talks to AI. No layer skipping.
- **Messages DB is read-only**: Never write to Apple's chat.db. Use AppleScript for sends.
- **Privacy**: Truncate message content to 80 chars in logs. Never log API keys.
- **Testing**: All smoke tests run offline. Use `tmp_path` for DB tests.
- **Storage extension**: Implement `MessageStore` ABC for new backends.
- **Diagnostic format**: `Symptom → Fix → Result` for all issue documentation.

## Prerequisites

- macOS with Messages.app signed into iMessage
- Python 3.10+
- Terminal granted Full Disk Access (System Settings > Privacy & Security)
- Anthropic API key in `.env`
