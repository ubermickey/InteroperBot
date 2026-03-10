# TESTING — Quality Gates & Test Strategy

> **When to read this**: Before writing tests, before committing, or when a gate fails.

## Test Pyramid

```
         ┌─────────┐
         │  Manual  │  Run bot, send real messages (iMessage / WhatsApp / Web)
         │  (rare)  │
         ├─────────┤
         │  Probe   │  tests/probe_messages_db.py
         │          │  Validates macOS environment
         ├─────────┤
         │Transport │  Transport + router integration tests
         │          │  MockTransport, MockAssistant patterns
         ├─────────┤
         │  Smoke   │  tests/test_smoke.py (36 tests)
         │          │  Offline, no API key, no Messages DB
         └─────────┘
```

## Offline Smoke Tests (36 tests)

Run without any external dependencies (no API key, no Messages DB, no network):

```bash
python -m pytest tests/test_smoke.py -v
```

### Core Layer Tests
| Test | What It Validates |
|---|---|
| `test_bot_help` | CLI `--help` exits cleanly |
| `test_imports` | All modules import without error |
| `test_status_json_valid` | status.json schema validation |

### Store Layer Tests
| Test | What It Validates |
|---|---|
| `test_store_roundtrip` | SQLiteStore CRUD operations |
| `test_store_metadata` | Contact metadata get/set |
| `test_store_clear` | History clearing |
| `test_store_session_id_roundtrip` | CLI session ID persistence per contact |

### AI Layer Tests
| Test | What It Validates |
|---|---|
| `test_assistant_respond_returns_tuple` | ClaudeAssistant returns `(reply, session_id)` |
| `test_assistant_format_history` | History formatting for CLI prompts |

### iMessage Layer Tests
| Test | What It Validates |
|---|---|
| `test_apple_date_conversion` | Apple epoch timestamp conversion |
| `test_extract_attributed_text_basic` | NSAttributedString binary extraction |
| `test_extract_attributed_text_none` | Graceful handling of None attributedBody |
| `test_extract_attributed_text_prefers_text_over_metadata` | Text column priority |
| `test_pending_delivery_lifecycle` | Delivery tracking state machine |
| `test_imessage_transport_is_transport` | iMessage implements Transport ABC |

### Attachment Layer Tests
| Test | What It Validates |
|---|---|
| `test_attachment_dataclass` | Legacy Attachment dataclass |
| `test_classify_media_type` | MIME type classification |
| `test_expand_attachment_path` | `~/Library` path expansion |
| `test_incoming_message_with_attachments` | Messages carry attachment metadata |
| `test_incoming_message_attachment_only` | Attachment-only messages (no text) |
| `test_human_size` | Human-readable file sizes |
| `test_enrich_attachment_missing_file` | Graceful missing-file handling |
| `test_enrich_attachment_no_filename` | Graceful no-filename handling |
| `test_enrich_message_attachment_missing_file` | Transport-agnostic attachment enrichment |

### Video/Storyboard Tests
| Test | What It Validates |
|---|---|
| `test_describe_video_empty_frames` | Empty frame list handling |
| `test_describe_storyboard_panels_empty` | Empty storyboard handling |
| `test_storyboard_align_frames` | Frame-to-segment alignment |
| `test_storyboard_align_no_segments` | No audio segments edge case |
| `test_storyboard_align_empty` | Empty input edge case |

### Config Tests
| Test | What It Validates |
|---|---|
| `test_config_attachment_defaults` | Attachment config defaults |
| `test_config_whatsapp_defaults` | WhatsApp config defaults |

### Transport & Router Tests
| Test | What It Validates |
|---|---|
| `test_transport_abc_requires_send` | Transport ABC enforces `send()` |
| `test_message_attachment_dataclass` | Transport-agnostic attachment type |
| `test_transport_incoming_message` | Transport-agnostic IncomingMessage |
| `test_router_handle_message` | MessageRouter routes through Store→AI→Store |
| `test_router_stores_messages` | Router persists both user and AI messages |

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
- [ ] `python -m pytest tests/ -v` — all 36 tests pass
- [ ] No secrets in staged files (`.env`, credentials)
- [ ] Transport tests pass for any modified transport layer

### Pre-Deploy Gate
- [ ] All pre-commit gates pass
- [ ] `python tests/probe_messages_db.py` exits 0 (iMessage)
- [ ] If WhatsApp enabled: bridge starts and responds to health check
- [ ] `python bot.py --status` outputs valid JSON with transport health
- [ ] `status.json` consumed by `dashboard.html` without errors

### Hard Stop Rule
3 consecutive failures at any gate triggers a hard stop. Escalate to Project Lead before continuing. Document failures using the diagnostic format:

```
Symptom: [What happened]
Fix:     [What was changed]
Result:  [Outcome]
```

See `research/` for examples of this format in practice.

## Testing Conventions

- Tests live in `tests/` directory
- Test files named `test_*.py` (pytest discovery)
- Probes named `probe_*.py` (standalone scripts, not pytest)
- All smoke tests must run offline (no network, no Claude CLI, no Messages DB)
- Use `tmp_path` fixture for any DB-backed tests (no persistent state)
- Mock `ClaudeAssistant` with a class that has `respond(history, session_id=None)` returning `(reply_text, session_id)`
- Mock transports using `MockTransport` that implements `Transport` ABC
- Message content in test assertions is fine — privacy truncation is a runtime logging rule

---

**See also**: `OPERATIONS.md` (environment setup), `PHILOSOPHY.md` (fail-gracefully principle), `ITERATION.md` (pass workflow)
