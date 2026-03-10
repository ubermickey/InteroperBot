# DASHBOARD — Mission Control Specification

> **When to read this**: When modifying the dashboard, updating status.json schema, or adding monitoring for new transports.

## Overview

`dashboard.html` is a self-contained Mission Control interface for InteroperBot. It reads project state from `status.json` and renders real-time system status without requiring a server.

## Panels

| Panel | Data Source | Refresh |
|---|---|---|
| System Status | `status.json` → status, uptime_since, messages_today | 30s |
| Transport Status | `status.json` → transports{} | 30s |
| Active Threads | `status.json` → threads[] | 30s |
| TODO Tracker | `status.json` → todos[] | 30s |
| Council Log | `status.json` → council_log[] | 30s |
| Health Monitors | `status.json` → health{} | 30s |
| Team Activity Log | `status.json` → activity_log[] | 30s |
| War Room | `status.json` → war_room{} | 30s |

### Transport Status Panel

Per-transport health monitoring:

| Transport | Health Signal | Status Values |
|---|---|---|
| iMessage | chat.db readable, AppleScript functional | connected / permission_denied / unavailable |
| WhatsApp | Bridge subprocess alive on `:3456` | connected / disconnected / disabled |
| Web | FastAPI port bound | listening / stopped / disabled |

Data sourced from `bot.py --status`, which includes a `transports` key:

```json
{
  "transports": {
    "imessage": { "status": "connected", "last_poll": "2026-03-09T10:15:23" },
    "whatsapp": { "status": "connected", "bridge_pid": 12345 },
    "web": { "status": "listening", "port": 8000 }
  }
}
```

## Usage

```bash
open dashboard.html
# or
python -m http.server 8080  # if fetch from file:// is blocked
```

## Updating Status

The dashboard is read-only. Update `status.json` to change what it displays:

```bash
# Bot's --status flag outputs current state including transport health
python bot.py --status > status.json

# Or update programmatically
python -c "
import json
data = json.load(open('status.json'))
data['health']['bot_process'] = True
json.dump(data, open('status.json', 'w'), indent=2)
"
```

## Design System

- Dark mode (#0d1117 background, #161b22 cards)
- Accent colors: green (#3fb950), blue (#58a6ff), orange (#d29922), red (#f85149)
- Font: JetBrains Mono (monospace fallback)
- Auto-refresh with countdown timer

---

**See also**: `OPERATIONS.md` (monitoring commands), `ARCHITECTURE.md` (transport layer)
