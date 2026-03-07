#!/usr/bin/env python3
"""Probe: Validate macOS Messages database access.

This is the core risk for InteroperBot — if we can't read chat.db,
the bot can't function. Run this to diagnose access issues.

Exit codes:
    0 — Full access confirmed
    1 — DB file missing
    2 — Permission denied (Full Disk Access needed)
    3 — DB readable but query failed
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

def probe():
    print(f"Probing Messages DB at: {DB_PATH}")

    # Check 1: File exists
    if not DB_PATH.exists():
        print("FAIL: chat.db not found. Is Messages.app configured?")
        return 1
    print("  [OK] File exists")

    # Check 2: Can open read-only
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        print(f"  FAIL: Cannot open DB — {e}")
        print("  FIX: Grant Full Disk Access to Terminal in System Settings")
        return 2
    print("  [OK] Database opened (read-only)")

    # Check 3: Can query
    try:
        row = conn.execute("SELECT MAX(ROWID) as max_id FROM message").fetchone()
        max_id = row[0] if row else 0
        print(f"  [OK] Query succeeded — {max_id} messages in DB")
    except sqlite3.OperationalError as e:
        print(f"  FAIL: Query failed — {e}")
        conn.close()
        return 3

    # Check 4: Chat table accessible
    try:
        count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
        print(f"  [OK] {count} chats found")
    except sqlite3.OperationalError as e:
        print(f"  WARN: Chat table query failed — {e}")

    conn.close()
    print("\nAll checks passed. InteroperBot can read Messages DB.")
    return 0

if __name__ == "__main__":
    sys.exit(probe())
