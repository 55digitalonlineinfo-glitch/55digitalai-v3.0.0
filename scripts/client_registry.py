#!/usr/bin/env python3
"""
55DigitalAI — Shared Client Registry
=============================================================
Purpose  : Single source of truth for client slug -> account metadata.
           Every script in this toolkit (daily_check.py, pmax_brand_generic_audit.py,
           build_dashboard.py, etc.) imports CLIENTS/resolve() from here
           instead of hardcoding customer IDs.

           Data lives in clients.json (repo root), not in this file — this
           file only loads and looks it up. That's deliberate for two
           reasons: a plain JSON file is safe for setup_wizard.py (or you,
           by hand) to read and write without risking corrupting Python
           syntax, which a hardcoded dict literal would; and clients.json is
           gitignored (ships as clients.json.example instead), so your real
           client data never accidentally ends up in this repo's git history
           — the same protection google-ads.yaml already has.

Usage    : from client_registry import CLIENTS, resolve, save_clients
Setup    : Run `python3 scripts/setup_wizard.py` (creates clients.json for
           you), or copy clients.json.example to clients.json by hand and
           edit it — either way, replace the "acme" example with your real
           client(s), then delete the example entry.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "clients.json"
EXAMPLE_PATH = ROOT / "clients.json.example"


def _load() -> dict:
    if not CONFIG_PATH.exists():
        if EXAMPLE_PATH.exists():
            shutil.copy(EXAMPLE_PATH, CONFIG_PATH)
            print(f"First run — copied {EXAMPLE_PATH.name} to {CONFIG_PATH.name}. "
                  f"Edit it (or run scripts/setup_wizard.py) to add your real client.")
        else:
            sys.exit(f"ERROR: neither {CONFIG_PATH} nor {EXAMPLE_PATH} found. "
                      f"Run `python3 scripts/setup_wizard.py` to create one.")
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: {CONFIG_PATH} is not valid JSON — {e}")


CLIENTS = _load()


def reload():
    """Re-read clients.json from disk — useful after setup_wizard.py writes a new entry
    in the same process (e.g. the wizard itself, or a REPL), since CLIENTS above is only
    loaded once at import time otherwise."""
    global CLIENTS
    CLIENTS = _load()
    return CLIENTS


def save_clients(data: dict) -> None:
    """Write the full CLIENTS dict back to clients.json, preserving readable formatting.
    Callers should read-modify-write via CLIENTS/reload(), not construct data from scratch."""
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve(slug_or_id: str) -> dict:
    """Look up a client by slug (e.g. 'acme') or raw customer_id. Raises KeyError if unknown."""
    if slug_or_id in CLIENTS:
        return {"slug": slug_or_id, **CLIENTS[slug_or_id]}
    for slug, meta in CLIENTS.items():
        if meta["customer_id"] == slug_or_id:
            return {"slug": slug, **meta}
    raise KeyError(f"Unknown client '{slug_or_id}' — expected one of: {', '.join(CLIENTS)}")


# Report language per client country (client PDFs). Override per client with a "language" key in clients.json.
COUNTRY_LANGUAGE = {"UA": "uk", "PL": "pl", "DE": "de", "AT": "de", "CH": "de", "FR": "fr", "ES": "es", "IT": "it"}


def client_language(slug_or_id: str, default: str = "en") -> str:
    """'uk' / 'pl' / ... for a known client, `default` (English) for an unknown slug or country."""
    try:
        c = resolve(slug_or_id)
    except KeyError:
        return default
    return c.get("language") or COUNTRY_LANGUAGE.get(c.get("country", ""), default)
