# InteroperBot

Multi-transport messaging bot powered by Claude. Routes messages from iMessage, WhatsApp, and Web through a single `MessageRouter` — no API key needed, uses your Claude subscription directly via the CLI.

## Architecture

```
                ┌── iMessage  (poll macOS chat.db)
                │
MessageRouter ──┼── WhatsApp  (Baileys Node.js bridge)
(core.py)       │
                ├── Web       (FastAPI chat UI)
                │
                └── [future transports]
        ↕               ↕
    SQLiteStore    ClaudeAssistant
    (store.py)     (ai.py → claude CLI)
```

All transports implement a `Transport` ABC (`transport.py`). The router handles Store → AI → Store for every transport — no duplicate flows. CLI sessions are the primary memory (`--resume` maintains full context across turns). SQLiteStore logs every exchange as backup; if a session expires, history is rebuilt automatically.

## Prerequisites

- macOS with Messages.app signed into iMessage
- Python 3.10+
- Claude CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Terminal app granted **Full Disk Access** (System Settings > Privacy & Security)
- Node.js ≥18 for WhatsApp only (`brew install node`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # All settings optional — no API key needed
```

## Usage

```bash
# Run the bot (iMessage + web UI by default)
python bot.py

# Other modes
python bot.py --dry-run                    # Print responses instead of sending
python bot.py --reset                      # Clear conversation history
python bot.py --status                     # JSON status for dashboard
python web.py                              # Standalone web chat at http://localhost:8000

# WhatsApp setup
python bot.py --setup-whatsapp             # QR code scan
python bot.py --setup-whatsapp +1NNNNNN    # Pairing code (enter in WhatsApp)

# Run with WhatsApp active
WHATSAPP_ENABLED=true python bot.py

# Tests (36 offline smoke tests)
python -m pytest tests/ -v
```

## Configuration

All settings via `.env` (all optional):

| Variable | Default | Description |
|---|---|---|
| `SYSTEM_PROMPT` | Helpful assistant prompt | System prompt for Claude |
| `ALLOWED_CONTACTS` | (all) | Comma-separated phone numbers/emails |
| `POLL_INTERVAL` | `2` | Seconds between checking for new messages |
| `MAX_HISTORY` | `50` | Max messages per conversation sent to Claude |
| `CLI_TIMEOUT` | `120` | Seconds before Claude CLI call times out |
| `DB_PATH` | `~/.interoperbot/conversations.db` | Conversation database path |
| `CLAUDE_CLI` | `~/.local/bin/claude` | Path to Claude CLI binary |
| `WHATSAPP_ENABLED` | `false` | Enable WhatsApp transport |
| `WHATSAPP_BRIDGE_PORT` | `3456` | Baileys bridge port |
| `WEB_ENABLED` | `true` | Enable web UI alongside bot |
| `WEB_PORT` | `8000` | Web UI port |

## Extending

**New transport**: Implement `Transport` ABC from `transport.py`, register with `MessageRouter` in `bot.py`.

**New storage backend**: Implement `MessageStore` ABC from `store.py`:

```python
from store import MessageStore

class MyStore(MessageStore):
    def log_message(self, contact_id, role, content, timestamp=None, metadata=None): ...
    def get_history(self, contact_id, limit=50): ...
    # ... implement all abstract methods
```
