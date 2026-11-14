#!/usr/bin/env python3
"""Refuses to proceed if this project sits inside a macOS-protected folder
(Desktop/Documents/Downloads, or an iCloud/Dropbox/Google Drive sync folder).
launchd's background jobs (daily-checks, scheduled keyword audits) silently
lose file access there unless /bin/bash is manually granted Full Disk Access
in System Settings — a plain folder like ~/ needs no such grant.

Shared by setup.sh (called as a subprocess, before .venv even exists) and
setup_wizard.py (imported directly, in case someone runs the wizard without
going through setup.sh) so both entry points agree on what counts as
"protected" instead of maintaining two copies of this rule that can drift.

Override: set ALLOW_PROTECTED_FOLDER=1 to skip this check.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def is_protected(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    home = Path.home()
    protected_roots = [home / "Downloads", home / "Desktop", home / "Documents"]
    if path in protected_roots or any(p in path.parents for p in protected_roots):
        return True
    path_str = str(path)
    return "/Library/CloudStorage/" in path_str or "/Library/Mobile Documents/" in path_str


def check(path: Path = ROOT) -> bool:
    """Returns True if it's safe to proceed. Prints an explanation and
    returns False otherwise (caller decides whether to exit)."""
    if os.environ.get("ALLOW_PROTECTED_FOLDER") == "1":
        return True
    if not is_protected(path):
        return True

    print(f"This project is inside a macOS-protected folder:\n  {path}\n")
    print("Desktop, Documents, Downloads, and iCloud/Dropbox/Google Drive sync folders are")
    print("gated by macOS privacy controls (TCC). The scheduled automation this wizard sets")
    print("up (daily checks, keyword audits) runs via launchd in the background, and launchd")
    print("processes get silently blocked from reading/writing files in these locations")
    print("unless you manually grant /bin/bash Full Disk Access in System Settings > Privacy")
    print("& Security. Manual runs from a Terminal you've already authorized may work fine —")
    print("the scheduled background runs are what silently break.\n")
    target = Path.home() / path.name
    print("Move the project out first, e.g.:")
    print(f'  mv "{path}" "{target}"')
    print(f'  cd "{target}" && bash setup.sh\n')
    print("(If you're sure you want to proceed here anyway, e.g. no scheduled automation")
    print("planned, re-run with ALLOW_PROTECTED_FOLDER=1)")
    return False


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
