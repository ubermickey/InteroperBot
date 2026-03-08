# InteroperBot

iMessage bot powered by Claude. Monitors incoming iMessages on macOS and responds using the Claude CLI — no API key needed, uses your Claude subscription directly.

## Architecture

```
iMessage in → Transport → Store (log + load history) → AI (claude CLI) → Store (log reply) → Transport → iMessage out
```

Four decoupled layers:

- **Transport** (`imessage.py`) — reads/writes iMessages via macOS Messages DB + AppleScript
- **Storage** (`store.py`) — abstract `MessageStore` with SQLite default; logs every exchange for backup/audit
- **AI** (`ai.py`) — calls `claude -p` with `--resume <session_id>` for session-based persistent memory
- **Orchestration** (`bot.py`) — CLI args, signal handling, polling loop, session ID plumbing

CLI sessions are the primary memory — `--resume` lets the Claude CLI natively maintain full conversation context across turns. SQLiteStore logs every exchange as a backup; if a session expires or corrupts, history is rebuilt from the store and a fresh session starts automatically.

## Prerequisites

- macOS with Messages.app signed into iMessage
- Python 3.10+
- Claude CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Terminal app granted **Full Disk Access** (System Settings > Privacy & Security > Full Disk Access)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # All settings optional — no API key needed
claude --version               # Verify Claude CLI is available
```

## Usage

```bash
python bot.py              # Run the iMessage bot
python bot.py --dry-run    # Print responses instead of sending
python bot.py --reset      # Clear conversation history
python bot.py --status     # Output JSON status for dashboard
python web.py              # Web chat UI at http://localhost:8000
```

## Configuration

All settings via environment variables or `.env` (all optional):

| Variable | Default | Description |
|---|---|---|
| `SYSTEM_PROMPT` | Helpful assistant prompt | System prompt for Claude |
| `ALLOWED_CONTACTS` | (empty = all) | Comma-separated phone numbers/emails |
| `POLL_INTERVAL` | `2` | Seconds between checking for new messages |
| `MAX_HISTORY` | `50` | Max messages per conversation sent to Claude |
| `CLI_TIMEOUT` | `120` | Seconds before Claude CLI call times out |
| `DB_PATH` | `~/.interoperbot/conversations.db` | Path to conversation database |
| `CLAUDE_CLI` | `~/.local/bin/claude` | Path to Claude CLI binary |

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
