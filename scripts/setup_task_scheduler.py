#!/usr/bin/env python3
"""
55DigitalAI — Windows Task Scheduler setup (Windows counterpart to setup_launchd.py)
=============================================================
Purpose  : Generates and installs Windows Scheduled Tasks for every scheduled
           automation this workspace uses, mirroring setup_launchd.py's job
           list and always-on-poller pattern exactly: each task fires on a
           fixed interval (30 min for the audit pollers, 60 min for
           daily-checks), every day, and the underlying bash script itself
           self-gates on day-of-week/hour where relevant (via
           TZ="Europe/Warsaw" checks) — the scheduler itself does no day/time
           filtering. This matches the Mac pattern instead of trying to
           encode the Warsaw business-hours window into Task Scheduler's own
           trigger (which would run in whatever timezone Windows itself is
           set to, not necessarily Warsaw).

           Runs each client's existing bash script via Git Bash (bash.exe)
           rather than reimplementing its lock/log/timeout/guard logic in
           PowerShell — that logic already exists and is proven on macOS;
           Windows just needs something to invoke it on a schedule.
           Requires Git for Windows (bash.exe) to already be installed.

Prereqs  : - Git for Windows (provides bash.exe) on this machine
           - Standalone Claude CLI installed (scripts/setup_wizard.py's
             ensure_claude_cli() does this automatically on Windows)
           - This workspace marked trusted in ~/.claude.json (see
             setup_wizard.py's offer_scheduled_automation_setup())
           - clients/<slug>/scripts/run_audit.sh does NOT need to exist yet —
             matching setup_launchd.py, the {slug}-audit task installs
             unconditionally for every client in clients.json and just errors
             harmlessly each tick until scaffold_client_audit.py creates the
             script, at which point it starts working with no re-run needed.
             (The PMax audit variants ARE existence-gated, since those are
             opt-in per client rather than universal.)

Usage    : python3 scripts/setup_task_scheduler.py                 # install all jobs
           python3 scripts/setup_task_scheduler.py --dry-run        # show what would run, install nothing
           python3 scripts/setup_task_scheduler.py --only <slug>    # only jobs whose name contains <slug>
           python3 scripts/setup_task_scheduler.py --status         # show current schtasks state, no changes

Logon note: tasks are created with default logon type (run only while this
Windows user is logged on — a locked screen still counts as logged on, a
full sign-out or reboot does not). Surviving a full logoff/reboot requires
storing this Windows account's password via schtasks /RU /RP, which this
script does NOT do automatically since that's a materially bigger, more
sensitive commitment than anything else in this setup — do that by hand
via Task Scheduler's GUI (Properties → General → "Run whether user is
logged on or not") if you need it.

Changelog: 2026-07-30 — initial version, Windows counterpart to setup_launchd.py
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Console codepage on non-English Windows installs (e.g. cp1250) can't encode
# the -> / -- punctuation used below; reconfigure so this never crashes mid-run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path(__file__).resolve().parent.parent
# Generated per-job hidden-window launchers live here (see write_job_launcher).
# Machine-specific (bakes in this install's absolute paths) — gitignored,
# excluded from build_release.sh, regenerated fresh on every run.
LAUNCHER_DIR = WORKSPACE / "scripts" / "_scheduled"


def label_prefix():
    """Same brand_config.json-derived namespacing as setup_launchd.py, so task
    names in Task Scheduler match the launchd label convention on Mac."""
    brand_path = WORKSPACE / "brand_config.json"
    name = "55digitalai"
    if brand_path.exists():
        try:
            agency_name = json.loads(brand_path.read_text(encoding="utf-8")).get("agency_name", "")
            if agency_name and agency_name.strip().lower() != "your agency name":
                name = agency_name
        except (json.JSONDecodeError, OSError):
            pass
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "55digitalai"
    return f"{slug}-"


LABEL_PREFIX = label_prefix()


def client_slugs():
    """Every real client slug, straight from clients.json — same single source
    of truth as setup_launchd.py. Adding a client there (and creating its
    run_audit.sh) is enough to get it a half-hourly poller with no edits here."""
    with open(WORKSPACE / "clients.json", encoding="utf-8") as f:
        return sorted(json.load(f).keys())


# Mirrors setup_launchd.py's JOBS list exactly, including which jobs check
# script existence up front vs. which install unconditionally:
# - {slug}-audit: NO existence check (matches Mac) — installed even before
#   run_audit.sh exists, so it's already armed and fires correctly the moment
#   scaffold_client_audit.py creates the script, with no need to remember to
#   re-run this installer. Flagged in the missing-scripts warning at the end.
# - {slug}-pmax-audit / {slug}-pmax-brand-generic-audit: existence-gated
#   (matches Mac) — these are opt-in per client, unlike the base audit.
# - dashboard-build / daily-checks: static, no client involved.
# "minutes" is per-job since daily-checks/dashboard-build run hourly while the
# audit pollers run half-hourly, matching setup_launchd.py's own StartInterval
# values (1800s vs 3600s) for the same jobs.
JOBS = [
    *[
        {"label": f"{slug}-audit", "script": f"clients/{slug}/scripts/run_audit.sh", "minutes": 30}
        for slug in client_slugs()
    ],
    *[
        {"label": f"{slug}-pmax-audit", "script": f"clients/{slug}/scripts/run_pmax_audit.sh", "minutes": 30}
        for slug in client_slugs()
        if (WORKSPACE / f"clients/{slug}/scripts/run_pmax_audit.sh").exists()
    ],
    *[
        {"label": f"{slug}-pmax-brand-generic-audit", "script": f"clients/{slug}/scripts/run_pmax_brand_generic_audit.sh", "minutes": 30}
        for slug in client_slugs()
        if (WORKSPACE / f"clients/{slug}/scripts/run_pmax_brand_generic_audit.sh").exists()
    ],
    # Hourly, always-on dashboard rebuild — matches Mac's standalone job. (Its
    # practical effect is already mostly covered by daily-checks also calling
    # run_dashboard_build.sh at the end of its own run, but this keeps the
    # dashboard fresh even if daily-checks is ever disabled independently.)
    {"label": "dashboard-build", "script": "scripts/run_dashboard_build.sh", "minutes": 60},
    # Hourly, read-only pulse-check for every client in clients.json — no AI
    # judgment, no live writes, so (unlike the audit pollers) this is safe to
    # install unconditionally for all clients, no per-client opt-in needed.
    {"label": "daily-checks", "script": "scripts/run_daily_checks_all.sh", "minutes": 60},
]


def find_bash() -> str:
    """Resolves for any Windows user/install, not just this machine: PATH first,
    then both of Git for Windows' two common install roots (system-wide Program
    Files, or per-user AppData — the installer lets you pick either), checking
    both usr\\bin (where bash.exe actually lives) and bin (a compatibility copy
    Git also places there) under each, same set of candidates the generated
    run_audit.sh's own PATH-fix checks."""
    found = shutil.which("bash")
    if found:
        return found
    for root in (Path(r"C:\Program Files\Git"), Path.home() / "AppData" / "Local" / "Programs" / "Git"):
        for sub in ("usr/bin", "bin"):
            candidate = root / sub / "bash.exe"
            if candidate.exists():
                return str(candidate)
    print("ERROR: bash.exe not found (Git for Windows required). Install Git for Windows first.")
    sys.exit(1)


def find_wscript() -> str:
    """wscript.exe is a core Windows component, always under System32 — but
    resolve via SystemRoot rather than hardcoding C:\\Windows in case Windows
    is installed on a different drive (rare, but the same portability
    principle as find_bash())."""
    found = shutil.which("wscript")
    if found:
        return found
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe")


def vbs_quote(s: str) -> str:
    """Escapes a Python string as a VBScript string literal (doubling embedded
    quotes), including the surrounding quotes."""
    return '"' + s.replace('"', '""') + '"'


def write_job_launcher(label: str, bash_exe: str, script_path: Path) -> Path:
    """Bakes bash_exe/script_path into a small per-job .vbs file rather than
    passing them as run_hidden.vbs command-line args. schtasks caps /TR at 261
    characters, and passing both paths as CLI args put this workspace's path
    in the command twice (once for the launcher, once for the script) —
    overflows that limit on deeply nested install paths (e.g. a GitHub zip
    extracted with its usual doubled folder name). Baking the paths into the
    file itself means /TR only has to reference this one generated path."""
    LAUNCHER_DIR.mkdir(parents=True, exist_ok=True)
    vbs_path = LAUNCHER_DIR / f"{label}.vbs"
    runtime_command = f'"{bash_exe}" "{script_path}"'
    vbs_path.write_text(
        'Set objShell = CreateObject("WScript.Shell")\n'
        f'exitCode = objShell.Run({vbs_quote(runtime_command)}, 0, True)\n'
        'WScript.Quit(exitCode)\n',
        encoding="utf-8",
    )
    return vbs_path


def task_name(label: str) -> str:
    return f"\\{LABEL_PREFIX.rstrip('-')}\\{label}"


def schtasks(*args):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen; create nothing")
    parser.add_argument("--only", help="Only process jobs whose label contains this substring")
    parser.add_argument("--status", action="store_true", help="Just show schtasks state for these jobs, no changes")
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
        for job in jobs:
            name = task_name(job["label"])
            result = schtasks("/Query", "/TN", name)
            state = "NOT INSTALLED" if result.returncode != 0 else "installed"
            print(f"{name:45s} {state}")
        return

    bash_exe = find_bash()
    wscript_exe = find_wscript()
    print(f"Workspace: {WORKSPACE}")
    print(f"Git Bash: {bash_exe}")
    print(f"Jobs to process: {len(jobs)}\n")

    missing_scripts = []
    too_long = []

    for job in jobs:
        name = task_name(job["label"])
        script_path = WORKSPACE / job["script"]
        # Each job gets its own tiny generated .vbs (see write_job_launcher)
        # so bash.exe's console window stays suppressed without blowing past
        # schtasks' 261-char /TR limit — see that function's docstring for why.
        launcher_vbs = write_job_launcher(job["label"], bash_exe, script_path)
        command = f'"{wscript_exe}" //B "{launcher_vbs}"'
        minutes = str(job.get("minutes", 30))

        if not script_path.exists():
            missing_scripts.append((name, script_path))

        if len(command) > 261:
            too_long.append((name, len(command)))
            print(f"  {name:45s} SKIPPED: /TR would be {len(command)} chars (limit 261) — install path is too long")
            continue

        if args.dry_run:
            print(f"[DRY RUN] Would create task {name}")
            print(f"           /TR {command}")
            print(f"           /SC MINUTE /MO {minutes}")
            print(f"           script exists: {script_path.exists()}")
            continue

        # Install even if the script doesn't exist yet — matches setup_launchd.py:
        # the task is armed and fires correctly the moment the script appears
        # (e.g. via scaffold_client_audit.py later), no need to re-run this
        # installer. Until then it just errors harmlessly each tick.
        create = schtasks(
            "/Create", "/F",
            "/TN", name,
            "/TR", command,
            "/SC", "MINUTE",
            "/MO", minutes,
            "/RL", "LIMITED",
        )
        status = "OK" if create.returncode == 0 else f"FAILED: {create.stderr.strip()}"
        flag = "  [SCRIPT MISSING — task installed but will error every run]" if not script_path.exists() else ""
        print(f"  {name:45s} {status}{flag}")

    if too_long and not args.dry_run:
        print("\nWARNING — these tasks were NOT installed because the install path is too long:")
        for name, length in too_long:
            print(f"  {name}: {length} chars — move this project to a shorter path and re-run")

    if missing_scripts and not args.dry_run:
        print("\nWARNING — these tasks were installed but their backing script doesn't exist yet in this clone:")
        for name, path in missing_scripts:
            print(f"  {name}: {path}")

    if not args.dry_run:
        print(f"\nDone. Verify with: schtasks /Query /TN \"\\{LABEL_PREFIX.rstrip('-')}\" /FO LIST")
        print("\nNote: tasks run only while this Windows user is logged on (locked screen is")
        print("fine; full logoff/reboot is not). For 'run whether logged on or not', use Task")
        print("Scheduler's GUI (Properties → General) — that requires storing this account's")
        print("password, which this script deliberately does not do for you.")


if __name__ == "__main__":
    main()
