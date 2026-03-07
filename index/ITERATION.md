# ITERATION — Pass-Based Development Workflow

## Pass Structure

Each development iteration follows a structured pass:

### Pass 1: Probe
- Run `tests/probe_messages_db.py` to validate environment
- Check `python bot.py --help` works
- Verify `.env` exists with valid API key
- **Gate**: All probes pass before proceeding

### Pass 2: Implement
- Write code changes
- Follow the 4-layer architecture (don't cross boundaries)
- Keep changes focused — one feature or fix per pass
- **Gate**: Code runs without import errors

### Pass 3: Test
- Run smoke tests: `python -m pytest tests/test_smoke.py -v`
- Run `python bot.py --dry-run` if testing message flow
- Check `python bot.py --status` outputs valid JSON
- **Gate**: All tests pass

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

## Iteration Cadence

- Each pass should be completable in a single session
- Status updates after every pass (update `status.json`)
- Council review triggered by architecture-level decisions
- No pass should require user intervention (autonomous agents)
