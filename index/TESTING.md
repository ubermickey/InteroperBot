# TESTING — Quality Gates & Test Strategy

## Test Pyramid

```
         ┌─────────┐
         │  Manual  │  Run bot, send real iMessages
         │  (rare)  │
         ├─────────┤
         │  Probe   │  tests/probe_messages_db.py
         │          │  Validates macOS environment
         ├─────────┤
         │  Smoke   │  tests/test_smoke.py
         │          │  Offline, no API key needed
         └─────────┘
```

## Offline Smoke Tests

Run without any external dependencies (no API key, no Messages DB):

```bash
python -m pytest tests/test_smoke.py -v
```

Tests included:
- `test_bot_help` — CLI `--help` exits cleanly
- `test_imports` — All modules import without error
- `test_store_roundtrip` — SQLiteStore CRUD operations
- `test_store_metadata` — Contact metadata get/set
- `test_store_clear` — History clearing
- `test_apple_date_conversion` — Apple epoch timestamp conversion
- `test_status_json_valid` — status.json schema validation

## Environment Probe

Validates the critical dependency — macOS Messages DB access:

```bash
python tests/probe_messages_db.py
```

Exit codes:
| Code | Meaning | Action |
|---|---|---|
| 0 | Full access confirmed | Ready to run |
| 1 | chat.db not found | Configure Messages.app |
| 2 | Permission denied | Grant Full Disk Access to Terminal |
| 3 | Query failed | Investigate DB schema |

## Quality Gates

### Pre-Commit Gate
- [ ] `python bot.py --help` exits 0
- [ ] `python -m pytest tests/test_smoke.py` all pass
- [ ] No secrets in staged files (`.env`, API keys)

### Pre-Deploy Gate
- [ ] All pre-commit gates pass
- [ ] `python tests/probe_messages_db.py` exits 0
- [ ] `python bot.py --status` outputs valid JSON
- [ ] `status.json` consumed by `dashboard.html` without errors

### Hard Stop Rule
3 consecutive failures at any gate triggers a hard stop. Escalate to Project Lead before continuing. Document failures using the diagnostic format:

```
Symptom: [What happened]
Fix:     [What was changed]
Result:  [Outcome]
```

## Testing Conventions

- Tests live in `tests/` directory
- Test files named `test_*.py` (pytest discovery)
- Probes named `probe_*.py` (standalone scripts, not pytest)
- All smoke tests must run offline (no network, no Claude CLI, no Messages DB)
- Use `tmp_path` fixture for any DB-backed tests (no persistent state)
