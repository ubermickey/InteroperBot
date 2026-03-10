# ITERATION — Pass-Based Development Workflow

> **When to read this**: At the start of every development session. Follow this pass structure for each iteration.

## Pass Structure

Each development iteration follows a structured pass:

### Pass 1: Probe
- Run `tests/probe_messages_db.py` to validate iMessage environment
- Check `python bot.py --help` works
- Verify `.env` exists (all settings optional — no API key needed)
- If WhatsApp enabled: verify bridge responds on `127.0.0.1:3456`
- **Gate**: All probes pass before proceeding

### Pass 2: Implement
- Write code changes
- Follow the 5-layer architecture — don't cross boundaries (see `ARCHITECTURE.md`)
- Route all message handling through `MessageRouter.handle_message()` — never duplicate the Store→AI→Store flow
- New transports: implement `Transport` ABC, register in `bot.py`
- Keep changes focused — one feature or fix per pass
- **Gate**: Code runs without import errors

### Pass 3: Test
- Run smoke tests: `python -m pytest tests/ -v` (36 tests, all offline)
- Run `python bot.py --dry-run` if testing message flow
- Check `python bot.py --status` outputs valid JSON
- **Gate**: All tests pass. See `TESTING.md` for quality gate details.

### Pass 4: Integrate
- Update `status.json` with new state
- Update `CLAUDE.md` if conventions changed
- Log activity to council log if decisions were made
- **Gate**: Dashboard reflects current state

## Hard Stop Rule

**3 consecutive failures at any gate = hard stop.** Escalate to Project Lead for reassessment before continuing. This prevents thrashing on broken assumptions.

## Diagnostic Format

When issues arise, document them as:

```
Symptom: [What's happening]
Fix:     [What was changed]
Result:  [Outcome after fix]
```

This format is used across the project — see `research/` for real examples.

## Iteration Cadence

- Each pass should be completable in a single session
- Status updates after every pass (update `status.json`)
- Council review triggered by architecture-level decisions
- No pass should require user intervention (autonomous agents)

---

**See also**: `TESTING.md` (quality gates), `OPERATIONS.md` (commands and file paths), `PHILOSOPHY.md` (kaizen principle)
