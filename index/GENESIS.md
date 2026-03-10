# GENESIS — InteroperBot Kickoff

> **When to read this**: At project inception or when onboarding a new contributor. Covers mission, risks, and initial decisions.

## Mission Statement

InteroperBot bridges messaging platforms and Claude, creating an always-on AI assistant accessible through iMessage, WhatsApp, and the web on macOS. Every incoming message — regardless of transport — routes through a single `MessageRouter` and gets a thoughtful, context-aware response powered by the Claude CLI. No API key needed — uses your Claude subscription directly.

## Core Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| macOS Messages DB access denied | **Critical** | Full Disk Access grant required; `tests/probe_messages_db.py` validates |
| Claude CLI not installed/authenticated | **Critical** | `claude --version` health check; clear install instructions |
| AppleScript send failures | Medium | Graceful error handling, retry logic with iMessage→SMS fallback |
| Message DB schema changes (macOS updates) | Medium | Abstracted queries, version-aware parsing |
| CLI subprocess timeout | Medium | Configurable `CLI_TIMEOUT` (default 120s) |
| Baileys protocol breaks (WhatsApp updates) | Medium | WhatsApp is optional transport; bridge can be disabled |
| WhatsApp QR/pairing rate limiting | Low | Credential persistence in `auth/` directory; infrequent re-auth |
| Bridge subprocess crash | Medium | Detected by health checks; reported via `--status` |
| WebSocket disconnect (WhatsApp) | Low | Transport reports disconnection; router continues with other transports |

## Kickoff Probe

Before any development session, run the probe:

```bash
python tests/probe_messages_db.py
```

This validates the single most critical dependency: read access to `~/Library/Messages/chat.db`. Without it, the iMessage transport cannot function. Other transports (WhatsApp, Web) do not depend on this.

## Project Genesis Record

- **Created**: 2026-03-07
- **Lead**: Claude Opus (Project Lead)
- **First Commit**: iMessage-to-Claude bot with future-proofed storage layer
- **Architecture**: 5-layer stack — Transports → Routing → Persistence → Intelligence → Orchestration. See `ARCHITECTURE.md`.
- **Intelligence**: Claude CLI subprocess (`claude -p`) — no API key, uses subscription
- **Memory Model**: CLI sessions are primary memory (`--resume <session_id>`); SQLiteStore is the backup/recovery layer for when sessions expire
- **Storage**: SQLite default with `MessageStore` ABC for future backends

## Team Assembly

See `TEAM.md` for full team composition and council seat assignments.

## First Sprint Goals

1. Validate Messages DB access on target machine
2. Establish development workflow (git, testing, launch scripts)
3. Build Mission Control dashboard for visibility
4. Add health check and status reporting to bot
5. Document all conventions in CLAUDE.md

---

**See also**: `ARCHITECTURE.md` (5-layer stack details), `TEAM.md` (council seats), `research/whatsapp_rnd.md` (WhatsApp experiment results)
