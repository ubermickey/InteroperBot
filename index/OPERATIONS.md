# OPERATIONS — Development Environment & Workflow

## Environment Setup

### Prerequisites
- macOS with Messages.app signed into iMessage
- Python 3.10+
- Claude CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code`)
- Terminal granted **Full Disk Access** (System Settings > Privacy & Security > Full Disk Access)

### First-Time Setup
```bash
cd /Users/mikeudem/Projects/InteroperBot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # All settings optional — no API key needed
claude --version             # Verify Claude CLI is available
```

### Validate Environment
```bash
python tests/probe_messages_db.py    # Check Messages DB access
python bot.py --help                  # Verify CLI works
python -m pytest tests/ -v           # Run smoke tests
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
Never commit: `.env`, `*.db`, `__pycache__/`, `.DS_Store`

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

### Status Check
```bash
python bot.py --status     # Outputs JSON for dashboard consumption
open dashboard.html        # View Mission Control
```

## Directory Structure

```
InteroperBot/
├── bot.py              # Entry point (Layer 4: Orchestration)
├── ai.py               # Claude CLI subprocess (Layer 3: Intelligence)
├── store.py            # Storage abstraction (Layer 2: Persistence)
├── imessage.py         # iMessage transport (Layer 1: Transport)
├── config.py           # Environment configuration
├── requirements.txt    # Python dependencies
├── web.py              # Web chat interface (FastAPI)
├── chat.html           # Web chat UI
├── .env.example        # Template for settings (no API key needed)
├── .gitignore          # Git exclusions
├── CLAUDE.md           # Claude Code instructions
├── README.md           # Project documentation
├── dashboard.html      # Mission Control UI
├── status.json         # Dashboard data (gitignored)
├── launch.command      # macOS double-click launcher
├── index/              # v4 Framework documentation
│   ├── GENESIS.md      # Kickoff ritual
│   ├── TEAM.md         # Team composition
│   ├── ARCHITECTURE.md # System design
│   ├── DASHBOARD.md    # Dashboard spec
│   ├── DESIGN.md       # Interface design
│   ├── ITERATION.md    # Pass workflow
│   ├── OPERATIONS.md   # This file
│   ├── TESTING.md      # Quality gates
│   └── PHILOSOPHY.md   # Principles
└── tests/              # Test infrastructure
    ├── __init__.py
    ├── test_smoke.py   # Offline smoke tests
    └── probe_messages_db.py  # Environment probe
```

## Monitoring

- `dashboard.html` — visual Mission Control (reads `status.json`)
- `python bot.py --status` — programmatic status output
- Bot logs to stdout via Python logging module
