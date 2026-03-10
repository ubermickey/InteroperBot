# OPERATIONS — Development Environment & Workflow

> **When to read this**: When setting up the project, adding dependencies, or looking up file paths and launch commands.

## Environment Setup

### Prerequisites
- macOS with Messages.app signed into iMessage
- Python 3.10+
- Claude CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Terminal granted **Full Disk Access** (System Settings > Privacy & Security > Full Disk Access)
- Node.js ≥18 (for WhatsApp transport only — `brew install node`)

### First-Time Setup
```bash
cd /Users/mikeudem/Projects/InteroperBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # All settings optional — no API key needed
claude --version             # Verify Claude CLI is available
```

### Validate Environment
```bash
python tests/probe_messages_db.py    # Check Messages DB access (iMessage)
python bot.py --help                  # Verify CLI works
python -m pytest tests/ -v           # Run 36 smoke tests (all offline)
```

### WhatsApp Setup (Optional)
```bash
python bot.py --setup-whatsapp       # Bootstrap bridge, install deps, scan QR code
WHATSAPP_ENABLED=true python bot.py  # Run with WhatsApp active
```

## Git Workflow

### Branch Strategy
- `main` — stable, tested code
- `claude/*` — development branches (created by Claude Code sessions)
- Feature branches merge to main via PR

### Commit Convention
```
<type>: <short description>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ops`

### Protected Files
Never commit: `.env`, `*.db`, `__pycache__/`, `.DS_Store`, `helpers/wa-bridge/auth/`, `helpers/wa-bridge/node_modules/`, `status.json`

## Launch Scripts

### Quick Start (launch.command)
Double-click to start the bot:
```bash
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || { echo "Run setup first"; exit 1; }
python bot.py
```

### Development Mode
```bash
source .venv/bin/activate
python bot.py --dry-run    # Safe testing — prints replies instead of sending
```

### Multi-Transport Mode
```bash
# iMessage + Web (default)
python bot.py

# iMessage + WhatsApp + Web
WHATSAPP_ENABLED=true python bot.py

# Standalone web chat
python web.py              # http://localhost:8000
```

### Status Check
```bash
python bot.py --status     # Outputs JSON with transport health info
open dashboard.html        # View Mission Control
```

## Directory Structure

```
InteroperBot/
├── bot.py              # Entry point (Layer 4: Orchestration)
├── core.py             # MessageRouter — single handle_message() flow (Layer 1: Routing)
├── transport.py        # Transport ABC, IncomingMessage, MessageAttachment (Layer 1)
├── imessage.py         # iMessage transport — poll chat.db, send via AppleScript (Layer 0)
├── whatsapp.py         # WhatsApp transport — Baileys bridge HTTP/WS (Layer 0)
├── web.py              # Web transport — FastAPI + chat UI (Layer 0)
├── ai.py               # Claude CLI subprocess with --resume (Layer 3: Intelligence)
├── store.py            # MessageStore ABC + SQLiteStore (Layer 2: Persistence)
├── attachments.py      # Attachment enrichment — images, audio, video
├── storyboard.py       # Video storyboard generation (frame alignment)
├── config.py           # Environment configuration (dotenv)
├── chat.html           # Web chat UI
├── dashboard.html      # Mission Control UI (reads status.json)
├── status.json         # Dashboard data (gitignored, runtime)
├── launch.command      # macOS double-click launcher
├── requirements.txt    # Python dependencies
├── .env.example        # Template for settings (no API key needed)
├── CLAUDE.md           # Claude Code instructions
├── README.md           # Project documentation
├── .gitignore          # Git exclusions
├── helpers/
│   ├── wa-bridge/      # WhatsApp Baileys bridge (Node.js subprocess)
│   │   ├── index.js    # Bridge server (HTTP + WS on 127.0.0.1:3456)
│   │   ├── package.json
│   │   └── auth/       # WhatsApp credentials (gitignored)
│   ├── describe_image  # Compiled Swift — Vision framework labels + OCR
│   ├── transcribe      # Compiled Swift — SFSpeechRecognizer
│   └── extract_keyframes.sh  # Bash — ffmpeg video frame extraction
├── index/              # v4 Framework documentation
│   ├── ARCHITECTURE.md # System design (5-layer stack, data flow)
│   ├── PHILOSOPHY.md   # Core principles and invariants
│   ├── GENESIS.md      # Kickoff ritual, mission, risks
│   ├── TEAM.md         # Team composition, council seats
│   ├── DESIGN.md       # Interface design (CLI, messaging UIs)
│   ├── OPERATIONS.md   # This file
│   ├── TESTING.md      # Quality gates, test pyramid
│   ├── ITERATION.md    # Pass workflow
│   └── DASHBOARD.md    # Dashboard specification
├── research/           # Experimental findings and diagnostics
│   ├── imessage-db-findings.md
│   └── whatsapp_rnd.md
└── tests/
    ├── __init__.py
    ├── test_smoke.py   # 36 offline smoke tests
    └── probe_messages_db.py  # Environment probe (standalone)
```

## Monitoring

- `dashboard.html` — visual Mission Control (reads `status.json`)
- `python bot.py --status` — JSON status including transport health
- Bot logs to stdout via Python logging module
- All message content truncated to 80 chars in logs (privacy)

## Design Rules Enforced Here

- **No API key**: All settings in `.env` are optional. Claude CLI uses your subscription.
- **Read-only DB**: iMessage transport opens `chat.db` with `?mode=ro`. Sends via AppleScript.
- **Single router flow**: All transports route through `MessageRouter.handle_message()` in `core.py`.
- **Subprocess helpers**: Node.js bridge, Swift helpers, and bash scripts all run as managed subprocesses.

---

**See also**: `TESTING.md` (quality gates), `GENESIS.md` (risk assessment), `ARCHITECTURE.md` (layer map)
