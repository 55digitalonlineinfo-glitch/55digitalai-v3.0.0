#!/usr/bin/env python3
"""
55DigitalAI — Agency Brand Constants
=============================================================
Purpose  : Single source of truth for the agency's name/colors/logo used in
           client-facing PDFs, loaded from brand_config.json (repo root) so
           every buyer's PDFs are branded as their own agency, not a
           hardcoded default. Edit brand_config.json directly — no code
           changes needed.

Usage    : from brand import COLORS, LOGO_PATH, AGENCY_NAME
Changelog: 2026-07-25  Generalised — was hardcoded to one specific agency's
                       colors/name/logo; now loads from brand_config.json.
"""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "brand_config.json"

_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}

AGENCY_NAME = _config.get("agency_name", "Your Agency Name")
COLORS = _config.get("colors", {
    "primary": "#07153F", "accent": "#3E5CE7", "accent_alt": "#324ECF",
    "secondary": "#444751", "text": "#6F7176", "bg_light": "#F4F7FC", "white": "#FFFFFF",
    "pass": "#1E8E3E", "pass_bg": "#E6F4EA", "fail": "#D93025", "fail_bg": "#FCE8E6",
    "warn": "#F9AB00", "warn_bg": "#FEF7E0", "na": "#9AA0A6", "na_bg": "#F1F3F4",
})
LOGO_PATH = Path(_config["logo_path"]) if _config.get("logo_path") else Path(__file__).resolve().parent.parent / "logo.png"
