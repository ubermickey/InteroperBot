# ARCHITECTURE — InteroperBot System Design

## 4-Layer Stack

```
Layer 4: ORCHESTRATION     bot.py
         Signal handling, polling loop, CLI args, contact filtering

Layer 3: INTELLIGENCE      ai.py
         Claude API wrapper, conversation context, system prompts

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
                    │  Layer 3     │  ClaudeAssistant.respond()
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

### 2. Abstract Storage Interface
`MessageStore` is an ABC with 7 abstract methods. `SQLiteStore` is the default implementation. This enables future backends (Notion, Postgres, custom EA systems) without touching bot logic.

### 3. Polling Architecture
The bot uses a simple `time.sleep()` poll loop rather than filesystem watchers or notification APIs. This is intentional — it's the most reliable approach given that `chat.db` is WAL-mode SQLite and fsevents on it are unreliable.

### 4. Per-Contact Conversation Isolation
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
| Different AI provider | Replace `ClaudeAssistant` | `ai.py` |
| Non-iMessage transport | New transport class | new file |
| Message preprocessing | Add middleware in poll loop | `bot.py` |
