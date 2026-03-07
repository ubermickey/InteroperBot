# DESIGN — InteroperBot Interface Design

## Design Philosophy

InteroperBot is a **CLI-first** tool. There is no web UI for the bot itself — iMessage *is* the user interface. Design effort focuses on:

1. **Terminal output** — clear, scannable log output during bot operation
2. **Dashboard** — Mission Control for development visibility
3. **CLI flags** — intuitive command-line interface

## Terminal Output Design

### Log Format
```
2026-03-07 10:15:23 [INFO] bot: Bot started. Watching for new messages (after ROWID 12345)...
2026-03-07 10:15:25 [INFO] bot: Message from +15551234567: Hey, can you help me with...
2026-03-07 10:15:27 [INFO] bot: Sent reply to +15551234567
```

### Principles
- Timestamps always present (ISO-ish format via Python logging)
- Log level in brackets: `[INFO]`, `[ERROR]`, `[DEBUG]`
- Module name after level for traceability
- Message text truncated to 80 chars in logs (privacy + readability)
- No color codes in logs (pipe-friendly)

## CLI Interface

```
python bot.py              # Run the bot (default)
python bot.py --dry-run    # Print responses to stdout
python bot.py --reset      # Clear conversation history
python bot.py --status     # Output JSON status for dashboard
python bot.py --help       # Show help
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
- Response latency target: < 5 seconds from message to reply
- System prompt enforces conversational tone

## Dashboard Design

See `DASHBOARD.md` for the Mission Control interface specification.
The dashboard uses a dark terminal aesthetic to match the CLI-first philosophy.
