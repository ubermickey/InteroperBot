# InteroperBot

iMessage bot powered by Claude. Monitors incoming iMessages on macOS and responds using the Anthropic API.

## Architecture

```
iMessage in → Transport → Store (log + load history) → AI (Claude) → Store (log reply) → Transport → iMessage out
```

Three decoupled layers:

- **Transport** (`imessage.py`) — reads/writes iMessages via macOS Messages DB + AppleScript
- **Storage** (`store.py`) — abstract `MessageStore` with SQLite default; swap in Notion/custom backend by implementing the interface
- **AI** (`ai.py`) — Claude conversations via Anthropic API

Conversations persist across restarts in `~/.interoperbot/conversations.db`.

## Prerequisites

- macOS with Messages.app signed into iMessage
- Python 3.10+
- Terminal app granted **Full Disk Access** (System Settings → Privacy & Security → Full Disk Access)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Anthropic API key
```

## Usage

```bash
python bot.py              # Run the bot
python bot.py --dry-run    # Print responses instead of sending
python bot.py --reset      # Clear conversation history
```

## Configuration

All settings via environment variables or `.env`:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `SYSTEM_PROMPT` | Helpful assistant prompt | System prompt for Claude |
| `ALLOWED_CONTACTS` | (empty = all) | Comma-separated phone numbers/emails |
| `POLL_INTERVAL` | `2` | Seconds between checking for new messages |
| `MAX_HISTORY` | `50` | Max messages per conversation sent to Claude |
| `DB_PATH` | `~/.interoperbot/conversations.db` | Path to conversation database |

## Extending the Storage Layer

To integrate with a different backend, subclass `MessageStore` from `store.py`:

```python
from store import MessageStore

class MyCustomStore(MessageStore):
    def log_message(self, contact_id, role, content, timestamp=None, metadata=None):
        ...
    def get_history(self, contact_id, limit=50):
        ...
    # ... implement all abstract methods
```

Then pass it to the bot in `bot.py` instead of `SQLiteStore`.
