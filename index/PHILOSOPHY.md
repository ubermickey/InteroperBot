# PHILOSOPHY — Kaizen-Unix Foundation

> **When to read this**: Before making any design decision. These principles are the project's immutable invariants.

## Core Principles

### 1. Do One Thing Well
InteroperBot has one job: route messages from any platform through Claude via a single intelligent router. Every design decision serves this singular purpose. The bot is not a framework, not a platform, not an SDK — it's a router.

### 2. Unix Philosophy
- **Text streams**: Messages flow as text through a pipeline (Transport → Router → Store → AI → Store → Transport)
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
- No API key in the project — Claude CLI uses your subscription auth
- Messages DB accessed read-only — never write to Apple's `chat.db`

### 5. Fail Gracefully
- CLI errors return a friendly fallback message, not a crash
- Expired CLI sessions trigger automatic recovery from SQLiteStore history
- Missing Messages DB is diagnosed, not panicked on
- AppleScript failures are logged and continued past
- Bridge subprocess crashes are detected and reported
- The bot should survive any single-point failure

### 6. Convention Over Configuration
- Sensible defaults for all settings (poll interval, history limit, model)
- `.env` for overrides, not required for basic operation (no API key needed)
- Directory structure is predictable and documented

## Immutable Design Rules

### Single Router Rule
Every transport routes through `MessageRouter.handle_message()` in `core.py`. The Store→AI→Store flow exists exactly once. No transport should duplicate this pipeline — new transports need zero Store/AI wiring. See `ARCHITECTURE.md` for the full data flow.

### Read-Only DB Rule
Never write to Apple's `chat.db`. Reads use `?mode=ro`. Sends go through AppleScript, which is the sanctioned API.

### No API Key Rule
Claude CLI uses your subscription directly. No `anthropic` package, no API key, no token management. See `ARCHITECTURE.md` § CLI Session-Based Memory.

### Transport ABC Pattern
Pull transports override `poll()` (iMessage), push transports override `start()` (WhatsApp, Web). All transports implement `send()`. See `ARCHITECTURE.md` § Transport ABC.

### Subprocess Helper Pattern
External tools (Node.js, Swift, bash) run as managed subprocesses — never as libraries. The WhatsApp bridge, image describer, audio transcriber, and keyframe extractor all follow this pattern. See `OPERATIONS.md` for the full directory structure.

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Instead |
|---|---|---|
| Duplicate flows | Multiple Store→AI→Store pipelines diverge and break independently | Route everything through `MessageRouter.handle_message()` |
| Premature optimization | 2-second poll interval is fine | Optimize when latency measurements demand it |
| Feature creep | Bot should route messages through Claude, period | New features get their own evaluation |
| Silent failures | Hiding errors makes debugging impossible | Log everything, fail loudly |
| Clever code | Tomorrow-you won't understand it | Write boring, obvious code |

---

**See also**: `ARCHITECTURE.md` (system design), `DESIGN.md` (interface principles), `research/` (diagnostic findings)
