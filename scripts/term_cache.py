#!/usr/bin/env python3
"""
55DigitalAI — Search Term Classification Cache
=============================================================
Purpose  : Avoid re-sending the same search term to Claude for
           classification on every run. pmax_brand_generic_audit.py's analyze phase
           always looks at the top N terms by spend — since terms are
           fetched over a rolling window (e.g. last 4 days), a
           high-spend term recurs across many consecutive runs, and
           without caching gets re-classified (and re-billed) every time
           even though the client-brief rules that decide it haven't
           changed.

           Cache key is (client_slug, campaign_id, term, brief_hash) — the
           brief_hash means editing clients/<slug>/client-brief.md
           automatically invalidates every cached decision for that client,
           so a rule change takes effect immediately rather than needing a
           manual cache-clear.

Usage    : from term_cache import brief_hash, get_cached, set_cached
           bh = brief_hash(brief_text)
           cached, misses = get_cached(client_slug, campaign_id, terms, bh)
           # ... classify only `misses` with the AI ...
           set_cached(client_slug, campaign_id, bh, [{"term": t, "negate": bool, "reason": r}, ...])
"""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "term_cache.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS classifications (
    client_slug TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    term TEXT NOT NULL,
    brief_hash TEXT NOT NULL,
    negate INTEGER NOT NULL,
    reason TEXT,
    classified_at TEXT NOT NULL,
    PRIMARY KEY (client_slug, campaign_id, term, brief_hash)
)
"""


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(SCHEMA)
    return conn


def brief_hash(text: str) -> str:
    """Short, stable hash of the client brief — cache entries keyed to this
    become unreachable (effectively invalidated) the moment the brief changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_cached(client_slug: str, campaign_id: str, terms: list, bh: str):
    """Returns (cached: dict[term -> {"negate": bool, "reason": str}], misses: list[str])."""
    if not terms:
        return {}, []
    conn = _connect()
    placeholders = ",".join("?" * len(terms))
    rows = conn.execute(
        f"SELECT term, negate, reason FROM classifications "
        f"WHERE client_slug=? AND campaign_id=? AND brief_hash=? AND term IN ({placeholders})",
        (client_slug, campaign_id, bh, *terms),
    ).fetchall()
    conn.close()
    cached = {term: {"negate": bool(negate), "reason": reason} for term, negate, reason in rows}
    misses = [t for t in terms if t not in cached]
    return cached, misses


def set_cached(client_slug: str, campaign_id: str, bh: str, results: list) -> None:
    """results: [{"term": str, "negate": bool, "reason": str or None}, ...] — one row per
    term that was actually classified this run (both NEGATE and KEEP decisions)."""
    if not results:
        return
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = _connect()
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO classifications "
            "(client_slug, campaign_id, term, brief_hash, negate, reason, classified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(client_slug, campaign_id, r["term"], bh, int(bool(r["negate"])), r.get("reason"), now)
             for r in results],
        )
    conn.close()
