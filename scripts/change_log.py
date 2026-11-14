#!/usr/bin/env python3
"""
55DigitalAI — Shared Change Log
=============================================================
Purpose  : Every script that writes to a live Google Ads / Merchant Center
           account calls log_change() once per actual mutation, so there's
           one queryable record of "what did this toolkit ever change, on
           which account, when, and why" — instead of only free-text run
           logs under clients/<slug>/reports/*.log.

           This is local-only (SQLite file, gitignored, never leaves the
           machine) — it's an audit trail for you and your team, not
           telemetry sent anywhere.

Usage    : from change_log import log_change, new_run_id
           run_id = new_run_id()
           log_change(client_slug="acme", script="add_shared_negatives.py",
                      action="add_negative_keyword", resource_type="shared_criterion",
                      resource_id=list_id, detail=term, reason=None, run_id=run_id)

           Query from the CLI: python3 scripts/change_log.py show <client_slug> [--limit 50]
                                python3 scripts/change_log.py show --all [--limit 50]
"""

import argparse
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Windows' console defaults stdout to the system codepage (e.g. cp1250) instead
# of UTF-8, which crashes printing non-ASCII keyword text (Polish diacritics,
# etc.) below. No-op on macOS/Linux, and harmless if stdout is already UTF-8.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).resolve().parent.parent / "change_log.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    client_slug TEXT NOT NULL,
    script TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    detail TEXT,
    reason TEXT,
    run_id TEXT
)
"""


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(SCHEMA)
    return conn


def new_run_id() -> str:
    """One id per script invocation — groups every change from that run together."""
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def log_change(client_slug: str, script: str, action: str, resource_type: str = None,
                resource_id: str = None, detail: str = None, reason: str = None,
                run_id: str = None) -> None:
    """Record one real, already-applied mutation. Call this AFTER the API call
    succeeds, not before — this is a record of what happened, not a plan."""
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO changes (timestamp, client_slug, script, action, resource_type, "
            "resource_id, detail, reason, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), client_slug, script,
             action, resource_type, resource_id, detail, reason, run_id),
        )
    conn.close()


def query_changes(client_slug: str = None, limit: int = 50):
    conn = _connect()
    if client_slug:
        rows = conn.execute(
            "SELECT * FROM changes WHERE client_slug = ? ORDER BY id DESC LIMIT ?",
            (client_slug, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM changes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM changes LIMIT 0").description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def cmd_show(args):
    rows = query_changes(client_slug=None if args.all else args.client, limit=args.limit)
    if not rows:
        print("No changes logged yet.")
        return
    for r in rows:
        print(f"{r['timestamp']}  [{r['client_slug']}]  {r['script']} :: {r['action']}"
              f"{' -> ' + r['resource_id'] if r['resource_id'] else ''}"
              f"{'  ' + r['detail'] if r['detail'] else ''}"
              f"{'  (' + r['reason'] + ')' if r['reason'] else ''}")


def main():
    parser = argparse.ArgumentParser(description="Query the change log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="Print recent logged changes")
    p_show.add_argument("client", nargs="?", help="Client slug — omit with --all")
    p_show.add_argument("--all", action="store_true", help="Show changes across every client")
    p_show.add_argument("--limit", type=int, default=50)
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
