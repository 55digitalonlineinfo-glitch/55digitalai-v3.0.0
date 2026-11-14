#!/usr/bin/env python3
"""
Generate and install the ~/Library/LaunchAgents plists for every scheduled
automation this workspace uses, on whatever Mac it's run from.

Purpose: LaunchAgents live in ~/Library/LaunchAgents, outside the repo, and
are machine-specific (hardcoded absolute paths) — so they're never checked
into git. This script rebuilds them from the job list below against wherever
this repo is actually cloned, so setting up a second Mac doesn't mean
hand-copying and path-editing XML files. The client-audit pollers are
generated automatically from clients.json — add a client there (and create
its clients/<slug>/scripts/run_audit.sh, e.g. via scaffold_client_audit.py)
and it gets a half-hourly poller with no edits needed here. Add any other
bespoke scheduled job (e.g. a client-specific PMax audit or a rotation
script) to JOBS by hand, same shape as the examples already there.

What this script does NOT do (must be done first, manually — see
SCHEDULING.md / the setup wizard for the full checklist):
  - Clone the repo
  - Create the venv and `pip install -r requirements.txt`
  - Place google-ads.yaml and any other gitignored credentials (never
    transferred by this script or by git — copy by hand, securely)
  - Install the Claude CLI (the setup wizard does this automatically)

Usage:
  python3 scripts/setup_launchd.py                    # generate + install all jobs
  python3 scripts/setup_launchd.py --dry-run           # show what would be written, install nothing
  python3 scripts/setup_launchd.py --only <slug>       # install only jobs whose label contains <slug>
  python3 scripts/setup_launchd.py --status            # just show launchctl state for these labels, no changes

Changelog:
  2026-07-26 — initial version
"""

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
HOME = Path.home()
LAUNCH_AGENTS_DIR = HOME / "Library" / "LaunchAgents"


def label_prefix():
    """Derived from brand_config.json's agency_name, so the launchd labels this
    installs are namespaced to your own agency instead of a hardcoded one.
    Falls back to a generic prefix if brand_config.json is missing/unset."""
    import re
    brand_path = WORKSPACE / "brand_config.json"
    name = "55digitalai"
    if brand_path.exists():
        try:
            agency_name = json.loads(brand_path.read_text()).get("agency_name", "")
            if agency_name and agency_name.strip().lower() != "your agency name":
                name = agency_name
        except (json.JSONDecodeError, OSError):
            pass
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "55digitalai"
    return f"com.{slug}."


LABEL_PREFIX = label_prefix()

# Hourly slots for any client's calendar-based StartCalendarInterval jobs: 09:00-22:00 inclusive.
HOURS_9_TO_22 = list(range(9, 23))


def calendar_slots(weekdays, hours=HOURS_9_TO_22):
    """weekdays: launchd Weekday ints, 1=Mon ... 7=Sun (2=Tue, 5=Fri)."""
    return [{"Weekday": wd, "Hour": h, "Minute": 0} for wd in weekdays for h in hours]


def client_slugs():
    """Every real client slug, straight from clients.json — the single source of
    truth. Adding a client there (and creating its run_audit.sh) is enough to
    get it a half-hourly audit poller; no editing this file required."""
    with open(WORKSPACE / "clients.json") as f:
        return sorted(json.load(f).keys())


# "script" is relative to the workspace root; resolved against wherever this
# script actually lives. Add your own bespoke jobs below the generated
# pollers, same shape as the commented-out example.
JOBS = [
    # --- Half-hourly, always-on pollers; each script self-gates on day/hour ---
    *[
        {"label": f"{slug}-audit", "script": f"clients/{slug}/scripts/run_audit.sh",
         "schedule": {"type": "interval", "seconds": 1800}, "run_at_load": False}
        for slug in client_slugs()
    ],

    # --- Half-hourly, always-on pollers for the plain PMax irrelevant-keyword
    # audit (/pmax-audit's scheduled counterpart) — opt-in per client, unlike
    # the keyword-audit pollers above: only clients that have actually been
    # scaffolded (clients/<slug>/scripts/run_pmax_audit.sh exists) get one,
    # since not every client runs Performance Max ---
    *[
        {"label": f"{slug}-pmax-audit", "script": f"clients/{slug}/scripts/run_pmax_audit.sh",
         "schedule": {"type": "interval", "seconds": 1800}, "run_at_load": False}
        for slug in client_slugs()
        if (WORKSPACE / f"clients/{slug}/scripts/run_pmax_audit.sh").exists()
    ],

    # --- Half-hourly, always-on pollers for the PMax brand/generic-split
    # search-term audit (/55-pmax-brand-generic-audit's scheduled
    # counterpart) — opt-in per client, same as the plain PMax audit
    # pollers above: only clients that have actually been scaffolded
    # (clients/<slug>/scripts/run_pmax_brand_generic_audit.sh exists) get
    # one, since not every client runs a branded/generic PMax split ---
    *[
        {"label": f"{slug}-pmax-brand-generic-audit", "script": f"clients/{slug}/scripts/run_pmax_brand_generic_audit.sh",
         "schedule": {"type": "interval", "seconds": 1800}, "run_at_load": False}
        for slug in client_slugs()
        if (WORKSPACE / f"clients/{slug}/scripts/run_pmax_brand_generic_audit.sh").exists()
    ],

    # --- Hourly, always-on, also fires on login/wake ---
    {"label": "dashboard-build", "script": "scripts/run_dashboard_build.sh",
     "schedule": {"type": "interval", "seconds": 3600}, "run_at_load": True},

    # --- Hourly, read-only pulse-check for every client in clients.json —
    # no AI judgment, no live writes, so (unlike the audit pollers) this
    # runs for all clients automatically, no per-client opt-in needed ---
    {"label": "daily-checks", "script": "scripts/run_daily_checks_all.sh",
     "schedule": {"type": "interval", "seconds": 3600}, "run_at_load": True},
]


def build_plist_dict(job):
    label = LABEL_PREFIX + job["label"]
    script_path = WORKSPACE / job["script"]
    plist = {
        "Label": label,
        "ProgramArguments": ["/bin/bash", str(script_path)],
        "WorkingDirectory": str(WORKSPACE),
        "StandardOutPath": f"/tmp/{label}.out.log",
        "StandardErrorPath": f"/tmp/{label}.err.log",
        "RunAtLoad": job["run_at_load"],
    }
    sched = job["schedule"]
    if sched["type"] == "interval":
        plist["StartInterval"] = sched["seconds"]
    elif sched["type"] == "calendar":
        plist["StartCalendarInterval"] = sched["slots"]
    else:
        raise ValueError(f"Unknown schedule type: {sched['type']}")
    return label, script_path, plist


def launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen; write nothing, load nothing")
    parser.add_argument("--only", help="Only process jobs whose label contains this substring")
    parser.add_argument("--status", action="store_true", help="Just report launchctl status for these labels")
    args = parser.parse_args()

    jobs = JOBS
    if args.only:
        jobs = [j for j in jobs if args.only in j["label"]]
        if not jobs:
            print(f"No job label contains '{args.only}'. Known labels:")
            for j in JOBS:
                print(f"  {j['label']}")
            sys.exit(1)

    if args.status:
        result = launchctl("list")
        for job in jobs:
            label = LABEL_PREFIX + job["label"]
            hit = [line for line in result.stdout.splitlines() if label in line]
            print(f"{label:45s} {'LOADED: ' + hit[0].split(chr(9))[0:2].__str__() if hit else 'NOT LOADED'}")
        return

    print(f"Workspace: {WORKSPACE}")
    print(f"LaunchAgents dir: {LAUNCH_AGENTS_DIR}")
    print(f"Jobs to process: {len(jobs)}\n")

    missing_scripts = []
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    for job in jobs:
        label, script_path, plist = build_plist_dict(job)
        plist_path = LAUNCH_AGENTS_DIR / f"{label}.plist"

        if not script_path.exists():
            missing_scripts.append((label, script_path))

        if args.dry_run:
            print(f"[DRY RUN] Would write {plist_path}")
            print(f"           script: {script_path} {'(MISSING)' if not script_path.exists() else ''}")
            continue

        already_loaded = label in launchctl("list").stdout
        if already_loaded:
            unload = launchctl("unload", str(plist_path))
            if unload.returncode != 0 and plist_path.exists():
                print(f"  [WARN] unload {label} failed: {unload.stderr.strip()}")

        with open(plist_path, "wb") as f:
            plistlib.dump(plist, f)

        load = launchctl("load", "-w", str(plist_path))
        status = "OK" if load.returncode == 0 else f"FAILED: {load.stderr.strip()}"
        flag = "" if script_path.exists() else "  [SCRIPT MISSING — job installed but will error every run]"
        print(f"  {label:40s} {status}{flag}")

    if missing_scripts and not args.dry_run:
        print("\nWARNING — these jobs were installed but their backing script doesn't exist yet in this clone:")
        for label, path in missing_scripts:
            print(f"  {label}: {path}")

    if not args.dry_run:
        print(f"\nDone. Verify with: launchctl list | grep {LABEL_PREFIX.rstrip('.')}")


if __name__ == "__main__":
    main()
