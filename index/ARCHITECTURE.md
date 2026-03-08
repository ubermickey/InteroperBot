# ARCHITECTURE — InteroperBot System Design

## 4-Layer Stack

```
Layer 4: ORCHESTRATION     bot.py
         Signal handling, polling loop, CLI args, contact filtering

Layer 3: INTELLIGENCE      ai.py
         Claude CLI subprocess with session persistence (--resume), fallback recovery

Layer 2: PERSISTENCE       store.py
         MessageStore ABC, SQLiteStore, contact management, metadata

Layer 1: TRANSPORT          imessage.py
         macOS Messages DB reader, AppleScript sender, Apple date conversion
```

## Data Flow

```
                    macOS Messages
                    ~/Library/Messages/chat.db
                           │
                           ▼ (read-only SQL)
                    ┌──────────────┐
                    │  Transport   │  imessage.py
                    │  Layer 1     │  poll_new_messages()
                    └──────┬───────┘
                           │ IncomingMessage
                           ▼
                    ┌──────────────┐
                    │  Persistence │  store.py
                    │  Layer 2     │  log_message() + get_history()
                    └──────┬───────┘
                           │ [{"role": "user", "content": "..."}]
                           ▼
                    ┌──────────────┐
                    │ Intelligence │  ai.py
                    │  Layer 3     │  claude -p (CLI subprocess)
                    └──────┬───────┘
                           │ reply text
                           ▼
                    ┌──────────────┐
                    │ Orchestrator │  bot.py
                    │  Layer 4     │  route reply back
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  Transport   │  send_message()
                    │  Layer 1     │  via AppleScript
                    └──────────────┘
                           │
                           ▼
                    iMessage out to contact
```

## Key Design Decisions

### 1. Read-Only DB Access
Transport opens `chat.db` in `?mode=ro` (URI parameter). We never write to Apple's database — only read. Replies go through AppleScript, which is the sanctioned API.

### 2. CLI Session-Based Memory
The intelligence layer uses CLI sessions as the primary memory model:

```
New contact:      claude -p "msg" --output-format json    → capture session_id
Continuing:       claude -p "msg" --resume <sid> --output-format json
Session lost:     fallback → rebuild from SQLiteStore history, start fresh session
```

No API key needed — it uses your existing Claude subscription. The CLI binary is resolved via `config.CLAUDE_CLI` (default: `~/.local/bin/claude`).

### 3. Abstract Storage Interface
`MessageStore` is an ABC with 7 abstract methods. `SQLiteStore` is the default implementation. It serves as: (a) intrasession log and audit trail, (b) fallback recovery source when CLI sessions expire, and (c) enables future backends (Notion, Postgres, custom EA systems). The `contact_metadata` table stores per-contact `cli_session_id` values.

### 4. Polling Architecture
The bot uses a simple `time.sleep()` poll loop rather than filesystem watchers or notification APIs. This is intentional — it's the most reliable approach given that `chat.db` is WAL-mode SQLite and fsevents on it are unreliable.

### 5. Per-Contact Conversation Isolation
Each iMessage contact gets their own conversation thread in the store. History is loaded per-contact and sent to Claude independently. No cross-contamination of conversations.

## Database Schema

### Bot's Own Database (`~/.interoperbot/conversations.db`)
```sql
contacts (id, identifier, display_name, created_at)
messages (id, contact_id, role, content, timestamp, metadata_json)
contact_metadata (contact_id, key, value)
```

### Apple's Messages Database (read-only)
```sql
message (ROWID, text, date, is_from_me, ...)
chat (ROWID, chat_identifier, ...)
chat_message_join (chat_id, message_id)
```

## Extension Points

| What | How | Where |
|---|---|---|
| New storage backend | Implement `MessageStore` ABC | `store.py` |
| Different AI provider | Replace CLI subprocess call | `ai.py` |
| Non-iMessage transport | New transport class | new file |
| Message preprocessing | Add middleware in poll loop | `bot.py` |
