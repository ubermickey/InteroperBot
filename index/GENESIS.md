# GENESIS — InteroperBot Kickoff

## Mission Statement

InteroperBot bridges iMessage and Claude, creating an always-on AI assistant accessible through the most natural messaging interface on macOS. Every incoming iMessage gets a thoughtful, context-aware response powered by the Claude CLI — no API key needed, uses your Claude subscription directly.

## Core Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| macOS Messages DB access denied | **Critical** | Full Disk Access grant required; `tests/probe_messages_db.py` validates |
| Claude CLI not installed/authenticated | **Critical** | `claude --version` health check; clear install instructions |
| AppleScript send failures | Medium | Graceful error handling, retry logic |
| Message DB schema changes (macOS updates) | Medium | Abstracted queries, version-aware parsing |
| CLI subprocess timeout | Medium | Configurable `CLI_TIMEOUT` (default 120s) |

## Kickoff Probe

Before any development session, run the probe:

```bash
python tests/probe_messages_db.py
```

This validates the single most critical dependency: read access to `~/Library/Messages/chat.db`. Without it, nothing else matters.

## Project Genesis Record

- **Created**: 2026-03-07
- **Lead**: Claude Opus (Project Lead)
- **First Commit**: iMessage-to-Claude bot with future-proofed storage layer
- **Architecture**: Transport → Store → AI via Claude CLI (4-layer pipeline)
- **Intelligence**: Claude CLI subprocess (`claude -p`) — no API key, uses subscription
- **Persistent Memory**: SQLiteStore provides external conversation history to CLI prompts
- **Storage**: SQLite default with `MessageStore` ABC for future backends (Notion, etc.)

## Team Assembly

See `TEAM.md` for full team composition and council seat assignments.

## First Sprint Goals

1. Validate Messages DB access on target machine
2. Establish development workflow (git, testing, launch scripts)
3. Build Mission Control dashboard for visibility
4. Add health check and status reporting to bot
5. Document all conventions in CLAUDE.md
