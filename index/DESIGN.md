# DESIGN — InteroperBot Interface Design

> **When to read this**: When designing user-facing behavior — CLI output, message formatting, or transport-specific UX.

## Design Philosophy

InteroperBot is a **CLI-first** tool with three transports: iMessage (poll-based), WhatsApp (bridge-based), and Web (HTTP-based). Design effort focuses on:

1. **Terminal output** — clear, scannable log output during bot operation
2. **Dashboard** — Mission Control for development visibility (see `DASHBOARD.md`)
3. **CLI flags** — intuitive command-line interface
4. **Messaging UIs** — iMessage bubbles, WhatsApp bubbles, web chat

## Terminal Output Design

### Log Format
```
2026-03-07 10:15:23 [INFO] bot: Bot started. Watching for messages...
2026-03-07 10:15:25 [INFO] bot: [iMessage] Message from +15551234567: Hey, can you help me with...
2026-03-07 10:15:27 [INFO] bot: [iMessage] Sent reply to +15551234567
2026-03-07 10:16:01 [INFO] bot: [WhatsApp] Message from +15559876543: What's the weather...
```

### Principles
- Timestamps always present (ISO-ish format via Python logging)
- Log level in brackets: `[INFO]`, `[ERROR]`, `[DEBUG]`
- Transport identifier in brackets for multi-transport traceability
- Message text truncated to 80 chars in logs (privacy + readability)
- No color codes in logs (pipe-friendly)

## CLI Interface

```
python bot.py                       # Run bot (iMessage + Web by default)
python bot.py --dry-run             # Print responses to stdout (no sends)
python bot.py --reset               # Clear all conversation history
python bot.py --status              # Output JSON status for dashboard
python bot.py --setup-whatsapp      # Bootstrap WhatsApp bridge, scan QR
python bot.py --help                # Show help

WHATSAPP_ENABLED=true python bot.py # Run with WhatsApp transport

python web.py                       # Standalone web chat at http://localhost:8000
python web.py --port 3000           # Custom port
```

### Flag Design Rules
- Short flags only for frequently-used options
- Long flags are self-documenting
- No positional arguments (all flags)
- Exit codes: 0 = success, 1 = config error, 2 = permission error

## iMessage as UI

The user's iMessage conversation *is* the interface. Design constraints:
- Responses must be concise (iMessage bubbles are narrow)
- No markdown rendering (plain text only)
- Emoji used sparingly and intentionally
- Response latency target: < 5 seconds from poll to reply
- System prompt enforces conversational tone
- Delivery tracking: iMessage → SMS fallback if delivery fails

## WhatsApp as UI

WhatsApp conversations follow similar constraints to iMessage:
- Plain text responses (WhatsApp has limited formatting: bold, italic, monospace)
- Media handling: images, voice notes, and videos can be received and enriched
- QR code or pairing code required for initial authentication
- Typing indicators handled by the bridge
- Response latency depends on bridge subprocess health
- Auth credentials persist in `helpers/wa-bridge/auth/` (gitignored)

## Web as UI

Browser-based chat via `web.py` + `chat.html`:
- Full markdown rendering in the browser
- Real-time responses (no polling delay)
- Unified API endpoints: `/api/status`, `/api/transports`, `/api/send`, `/api/chat`
- No authentication required (local use)

## Dashboard Design

See `DASHBOARD.md` for the Mission Control interface specification.
The dashboard uses a dark terminal aesthetic to match the CLI-first philosophy.

---

**See also**: `ARCHITECTURE.md` (transport details), `DASHBOARD.md` (monitoring UI), `PHILOSOPHY.md` (privacy rules)
