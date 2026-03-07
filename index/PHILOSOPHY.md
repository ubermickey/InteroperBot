# PHILOSOPHY — Kaizen-Unix Foundation

## Core Principles

### 1. Do One Thing Well
InteroperBot has one job: bridge iMessage and Claude. Every design decision serves this singular purpose. The bot is not a framework, not a platform, not an SDK. It's a bridge.

### 2. Unix Philosophy
- **Text streams**: Messages flow as text through a pipeline (Transport → Store → AI → Transport)
- **Composability**: Each layer is independent and replaceable
- **Transparency**: All state is inspectable (SQLite DB, JSON status, stdout logs)
- **Simplicity**: Prefer the obvious approach over the clever one

### 3. Kaizen (Continuous Improvement)
- Small, incremental improvements over big rewrites
- Every session should leave the codebase measurably better
- Document what you learn for the next session (CLAUDE.md, status.json)
- Retrospect: what worked, what didn't, what to try next

### 4. Privacy First
- Message content is PII — treat it accordingly
- Never log full message content (truncate to 80 chars)
- Conversation DB is local-only (`~/.interoperbot/`)
- API key never leaves `.env` (gitignored)
- Messages DB accessed read-only

### 5. Fail Gracefully
- API errors return a friendly fallback message, not a crash
- Missing Messages DB is diagnosed, not panicked on
- AppleScript failures are logged and continued past
- The bot should survive any single-point failure

### 6. Convention Over Configuration
- Sensible defaults for all settings (poll interval, history limit, model)
- `.env` for overrides, not required for basic operation (except API key)
- Directory structure is predictable and documented

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Instead |
|---|---|---|
| Over-abstracting | Only one transport exists (iMessage) | Abstract when the second implementation arrives |
| Premature optimization | 2-second poll interval is fine | Optimize when latency measurements demand it |
| Feature creep | Bot should respond to messages, period | New features get their own evaluation |
| Silent failures | Hiding errors makes debugging impossible | Log everything, fail loudly |
| Clever code | Tomorrow-you won't understand it | Write boring, obvious code |
