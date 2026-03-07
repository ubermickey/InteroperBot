# GENESIS — InteroperBot Kickoff

## Mission Statement

InteroperBot bridges iMessage and Claude, creating an always-on AI assistant accessible through the most natural messaging interface on macOS. Every incoming iMessage gets a thoughtful, context-aware response powered by the Anthropic API.

## Core Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| macOS Messages DB access denied | **Critical** | Full Disk Access grant required; `tests/probe_messages_db.py` validates |
| API key exposure | High | `.env` file, never committed; `.gitignore` enforced |
| AppleScript send failures | Medium | Graceful error handling, retry logic |
| Message DB schema changes (macOS updates) | Medium | Abstracted queries, version-aware parsing |
| Runaway API costs | Medium | `MAX_HISTORY` cap, polling interval throttle |

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
- **Architecture**: Transport → Store → AI (3-layer pipeline)
- **Storage**: SQLite default with `MessageStore` ABC for future backends (Notion, etc.)

## Team Assembly

See `TEAM.md` for full team composition and council seat assignments.

## First Sprint Goals

1. Validate Messages DB access on target machine
2. Establish development workflow (git, testing, launch scripts)
3. Build Mission Control dashboard for visibility
4. Add health check and status reporting to bot
5. Document all conventions in CLAUDE.md
