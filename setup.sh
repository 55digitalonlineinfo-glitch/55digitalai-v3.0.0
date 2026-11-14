#!/usr/bin/env bash
# One-command setup for Mac/Linux — creates .venv, installs dependencies into it,
# then runs the wizard. Every slash command in this toolkit invokes .venv/bin/python3
# directly, so the venv must exist at this exact path before any command works.
# Usage: bash setup.sh
# (works even if the execute bit was lost, e.g. after downloading a ZIP from GitHub)
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Refuses to continue if this folder is somewhere launchd's background jobs would
# silently lose file access (Desktop/Documents/Downloads/iCloud/Dropbox/Google Drive).
# Shared with setup_wizard.py so both entry points agree on the rule — see that
# script's docstring for why. Runs via bare python3 since .venv doesn't exist yet.
if ! python3 scripts/check_safe_location.py; then
    exit 1
fi

if [ ! -d .venv ]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi

echo "Installing dependencies into .venv..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

echo
.venv/bin/python3 scripts/setup_wizard.py
