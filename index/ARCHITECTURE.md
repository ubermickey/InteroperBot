# ARCHITECTURE — InteroperBot System Design

## Multi-Transport Stack

```
Layer 4: ORCHESTRATION     bot.py
         CLI args, signal handling, transport registration

Layer 3: INTELLIGENCE      ai.py
         Claude CLI subprocess with session persistence (--resume), fallback recovery

Layer 2: PERSISTENCE       store.py
         MessageStore ABC, SQLiteStore, contact management, metadata

Layer 1: ROUTING           core.py + transport.py
         MessageRouter (single brain), Transport ABC (pluggable transports)

Layer 0: TRANSPORTS        imessage.py, whatsapp.py, web.py
         iMessage (poll), WhatsApp (Baileys bridge), Web (FastAPI)
```

## Data Flow

```
    iMessage (chat.db)     WhatsApp (Baileys WS)     Web (HTTP POST)
         │                        │                        │
         ▼ poll()                 ▼ start()                ▼ /api/chat
    ┌─────────┐            ┌───────────┐            ┌───────────┐
    │ iMessage │            │ WhatsApp  │            │   Web     │
    │Transport │            │ Transport │            │ Transport │
    └────┬─────┘            └─────┬─────┘            └─────┬─────┘
         │                        │                        │
         └──── IncomingMessage ───┼──── IncomingMessage ───┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │  MessageRouter   │  core.py
                        │  handle_message()│
                        └────────┬─────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼             ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │  Store   │ │   AI     │ │  Store   │
              │ log user │ │ claude-p │ │ log reply│
              └──────────┘ └──────────┘ └──────────┘
                                 │
                                 ▼
                        transport.send(reply)
                        (AppleScript / HTTP / no-op)
```

## Key Design Decisions

### 1. Transport ABC — Pull vs Push
Transports implement `Transport` from `transport.py`. Two flavors:
- **Pull**: Override `poll(on_message)` — called every `POLL_INTERVAL` seconds. iMessage polls `chat.db`.
- **Push**: Override `start(on_message)` — starts a listener (WebSocket, webhook). WhatsApp receives via Baileys bridge WS.

Web is a special case: it's push (HTTP POST triggers `handle_message`) but `send()` is a no-op since the reply goes via HTTP response.

### 2. Single Router — No Duplicate Flows
Before the refactor, `bot.py` and `web.py` each had their own Store→AI→Store pipeline. Now `MessageRouter.handle_message()` is the single brain. Every transport routes through it. This eliminates logic duplication and means new transports need zero Store/AI wiring.

### 3. Read-Only DB Access
iMessage transport opens `chat.db` in `?mode=ro` (URI parameter). We never write to Apple's database — only read. Replies go through AppleScript, which is the sanctioned API.

### 4. CLI Session-Based Memory
The intelligence layer uses CLI sessions as the primary memory model:

```
New contact:      claude -p "msg" --output-format json    → capture session_id
Continuing:       claude -p "msg" --resume <sid> --output-format json
Session lost:     fallback → rebuild from SQLiteStore history, start fresh session
```

No API key needed — uses your Claude subscription. Per-contact session IDs stored in `contact_metadata` table.

### 5. Polling Architecture
The router's `run()` loop calls `transport.poll()` for pull transports with `time.sleep()`. This is intentional — `chat.db` is WAL-mode SQLite and fsevents on it are unreliable.

### 6. Per-Contact Conversation Isolation
Each sender (regardless of transport) gets their own conversation thread in the store. History is loaded per-contact and sent to Claude independently.

### 7. WhatsApp Bridge Pattern
WhatsApp uses a Node.js subprocess (`helpers/wa-bridge/`) running Baileys — the same subprocess helper pattern as `helpers/transcribe` (Swift) and `helpers/extract_keyframes.sh` (bash). Communication: HTTP for sends, WebSocket for incoming messages, all on `127.0.0.1:3456`.

## Database Schema

### Bot's Own Database (`~/.interoperbot/conversations.db`)
```sql
contacts (id, identifier, display_name, created_at)
messages (id, contact_id, role, content, timestamp, metadata_json)
contact_metadata (contact_id, key, value)    -- stores cli_session_id per contact
pending_deliveries (id, chat_identifier, content, services_tried, attempts, status, outgoing_rowid)
```

### Apple's Messages Database (read-only)
```sql
message (ROWID, text, attributedBody, date, is_from_me, associated_message_type, error, ...)
chat (ROWID, chat_identifier, ...)
chat_message_join (chat_id, message_id)
attachment (ROWID, mime_type, filename, transfer_name, total_bytes)
message_attachment_join (message_id, attachment_id)
```

Note: 94.5% of messages are stored only in `attributedBody` (NSAttributedString binary), not `text`. The transport's `_extract_attributed_text()` handles this.

## Extension Points

| What | How | Where |
|---|---|---|
| New transport | Implement `Transport` ABC, register in `bot.py` | `transport.py` |
| New storage backend | Implement `MessageStore` ABC | `store.py` |
| Different AI provider | Replace CLI subprocess call | `ai.py` |
| New attachment type | Add enrichment function | `attachments.py` |
| API endpoints | Add routes in `WebTransport._register_routes()` | `web.py` |
