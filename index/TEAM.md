# TEAM — InteroperBot Development Team

> **When to read this**: When assembling a team for a development session or invoking the council for a design decision.

## Composition

| Role | Agent | Responsibilities |
|---|---|---|
| **Project Lead** | Claude Opus | Architecture decisions, code review, council chair |
| **Senior Engineer** | Claude Sonnet | Feature implementation, testing, integration |
| **Speed Hacker** | Claude Haiku | Boilerplate generation, quick fixes, scaffolding |

## Council Seats

The development council evaluates design decisions through five lenses:

| Seat | Focus | Key Questions |
|---|---|---|
| **Architect** | System design | Does this fit the 5-layer architecture? Does it route through `MessageRouter`? Is the Transport ABC the right abstraction? See `ARCHITECTURE.md`. |
| **Critic** | Risk & failure modes | What breaks? What's the security surface? PII exposure? Bridge subprocess failure? |
| **Pragmatist** | Shipping velocity | Is this the simplest thing that works? Are we over-engineering? |
| **Oracle** | Messaging domain | How does macOS Messages DB behave? What are WhatsApp protocol quirks? Multi-transport edge cases? |
| **Hacker** | Security & privacy | PII in message content, bridge subprocess isolation, transport credential security (`auth/`), Full Disk Access permissions |

## Council Seat Selection Rationale

InteroperBot has two domain-specific characteristics that shaped council selection:

### Oracle (Score: 3)
- Messaging domain expertise is critical (score: 3)
- Understanding macOS Messages DB internals, Apple date formats, chat identifiers
- Knowledge of AppleScript messaging quirks and failure modes
- WhatsApp protocol behavior (Baileys library, QR auth, media handling)
- Multi-transport edge cases (same contact on multiple platforms, message ordering)

### Hacker (Score: 3)
- Handles PII directly — every message is personal data (score: 3)
- Bridge subprocess isolation — WhatsApp bridge runs as separate Node.js process on localhost
- Transport credential security — WhatsApp auth tokens in `helpers/wa-bridge/auth/` (gitignored)
- Full Disk Access permission is a significant security surface
- No API key exists in this project — Claude CLI uses subscription auth directly

## Decision Protocol

1. Any team member can raise a decision for council review
2. Each seat votes: approve / reject / abstain
3. Majority rules; ties broken by Project Lead
4. All decisions logged to `status.json` council_log

---

**See also**: `ARCHITECTURE.md` (5-layer stack), `PHILOSOPHY.md` (design principles)
