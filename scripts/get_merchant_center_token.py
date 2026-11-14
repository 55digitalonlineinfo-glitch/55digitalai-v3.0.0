#!/usr/bin/env python3
"""
Merchant Center OAuth Token Generator
======================================
Purpose  : One-time setup. Generates OAuth credentials for the Merchant Center
           Content API and saves them to merchant-center-credentials.json in the
           workspace root. Run before using feed_audit.py.

Usage    : python3 scripts/get_merchant_center_token.py

Note     : merchant-center-credentials.json contains sensitive data — do not commit.
           It is already in .gitignore.
"""

import json
from pathlib import Path

import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = WORKSPACE_ROOT / "google-ads.yaml"
OUTPUT_PATH = WORKSPACE_ROOT / "merchant-center-credentials.json"

SCOPES = ["https://www.googleapis.com/auth/content"]


def main():
    with open(YAML_PATH) as f:
        config = yaml.safe_load(f)

    client_config = {
        "installed": {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    print("Opening browser for Merchant Center authorization...")
    print("Sign in with the Google account that has access to your Merchant Center account.")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": creds.refresh_token,
        "token": creds.token,
        "scopes": SCOPES,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print("\n" + "=" * 40)
    print("SUCCESS: CREDENTIALS SAVED")
    print("=" * 40)
    print(f"\nSaved to: {OUTPUT_PATH}")
    print("\nYou can now run: .venv/bin/python3 scripts/merchant_review.py <client_slug>")


if __name__ == "__main__":
    main()
