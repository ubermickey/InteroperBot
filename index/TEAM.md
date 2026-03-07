# TEAM — InteroperBot Development Team

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
| **Architect** | System design | Does this fit the 3-layer architecture? Is the abstraction right? |
| **Critic** | Risk & failure modes | What breaks? What's the security surface? PII exposure? |
| **Pragmatist** | Shipping velocity | Is this the simplest thing that works? Are we over-engineering? |
| **Oracle** | iMessage/messaging domain | How does macOS Messages actually behave? Edge cases in chat.db? |
| **Hacker** | Security & privacy | PII in message content, API key safety, DB access permissions |

## Council Seat Selection Rationale

InteroperBot has two domain-specific characteristics that shaped council selection:

### Oracle (Score: 3)
- iMessage/messaging domain expertise is critical (score: 3)
- Understanding macOS Messages DB internals, Apple date formats, chat identifiers
- Knowledge of AppleScript messaging quirks and failure modes

### Hacker (Score: 3)
- Handles PII directly — every message is personal data (score: 3)
- API key management is a core security concern
- Full Disk Access permission is a significant security surface

## Decision Protocol

1. Any team member can raise a decision for council review
2. Each seat votes: approve / reject / abstain
3. Majority rules; ties broken by Project Lead
4. All decisions logged to `status.json` council_log
