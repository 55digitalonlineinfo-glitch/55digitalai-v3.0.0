---
description: Set up the unattended scheduled negative-keyword automation for a client — choose a schedule, scaffold, review, test, and install in one guided flow
---

Set up scheduled automation for client **$1**. This turns the manual, one-off `/55-keyword-audit` into a standing routine that runs unattended on its own schedule and writes to the account with no human review — same pattern already running for other clients, see SCHEDULING.md.

**This is not a read-only command.** The test step and every real scheduled run after it write live to the client's shared negative-keyword list, with `--dangerously-skip-permissions` and no approval step — that's the entire point of this automation, not a bug. Because of that, walk through the steps below in order and don't skip the confirmation in Step 4 just to save time.

## Step 0 — Check prerequisites
`$1` needs, already set up before this command is useful:
- A `customer_id` **and** a `negative_list_id` in `clients.json` (if `negative_list_id` is missing: `python3 scripts/negative_keyword_audit.py list-lists $1`, then `set-list`/`create-list`)
- A filled-in `clients/$1/client-brief.md` (not the unreviewed auto-draft — this brief drives the AI's judgment on every unattended run, so a thin or wrong brief means thin or wrong judgment with nobody reviewing it after the fact)

If either is missing, stop here and say so plainly — don't generate a script that will misfire against an incomplete setup.

## Step 1 — Ask which days to run, and how far back to look
Use one AskUserQuestion call with two questions:

- **Which days?** Recommend **Tuesday and Friday** as the default — it spreads review across the week, catches irrelevant search terms within a few days of them appearing, and doesn't burn through Claude Pro session usage the way a daily run would. Offer alternatives: daily (best for high-spend, fast-moving accounts where junk terms accumulate cost quickly — costs more in session usage), or once a week e.g. just Monday (best for low-spend/stable accounts where twice a week is overkill).
- **How many days to look back each run?** Recommend a lookback that covers the gap since the last run plus a small buffer, so nothing slips through if one run fails — for the Tue/Fri default that's **4 days** (covers the Fri→Tue gap with a day to spare). If the user picks a different schedule, adjust the recommendation with them: daily → 2-3 days is enough; once a week → 7-8 days to cover the full gap.

Map their answer to the actual flags: `--weekdays mon,tue,wed,thu,fri,sat,sun` (comma-separated, any subset) and `--lookback-days N`.

## Step 2 — Generate the script
`python3 scripts/scaffold_client_audit.py $1 --weekdays <chosen> --lookback-days <chosen>`

This only writes `clients/$1/scripts/run_audit.sh` from `client-brief.md` — no API calls, no writes, nothing live yet. If it already exists, ask before passing `--force` to overwrite a possibly hand-tuned version.

## Step 3 — Show the user what was generated
Read the generated prompt back and summarize in plain language what it will and won't negate, per the client's brief — this is their one chance to catch a wrong assumption before it runs unattended. Point out anything in the brief that seemed thin (e.g. no protected-terms section, vague geography) since that directly limits how good the automated judgment can be. Confirm the schedule and lookback window match what they chose in Step 1.

## Step 4 — Confirm, then run the live test
**Explicitly ask the user before running this** — don't treat proceeding past Step 3 as implied consent. Tell them plainly: this will write real negatives to the live shared list right now, the same as the first scheduled run would.

Once confirmed: `AUDIT_FORCE=1 bash clients/$1/scripts/run_audit.sh`

Report exactly what got added (check `clients/$1/reports/keywords_audit_YYYY-MM-DD.log` for the NEGATED/KEPT/BROAD MATCH sections) — same as reporting the result of any other write in this toolkit.

## Step 5 — Install the schedule
Only after the user is satisfied with the test result. This step is platform-specific — check which OS this machine is running (e.g. `uname` on macOS/Linux vs. knowing you're on Windows) and use the matching script; both mirror the same job list from `clients.json` and install the identical always-on half-hourly poller pattern, just via a different OS scheduler:
- **macOS**: `python3 scripts/setup_launchd.py --only $1` (installs a launchd job)
- **Windows**: `python3 scripts/setup_task_scheduler.py --only $1` (installs a Task Scheduler task; requires Git for Windows for the `bash.exe` that runs `run_audit.sh` — `scripts/setup_wizard.py`'s `ensure_claude_cli()` and `offer_scheduled_automation_setup()` cover the other Windows prerequisites, see those before this step if not already run)

If neither applies (e.g. Linux), say so plainly and point to `SCHEDULING.md`'s cron section for the manual equivalent — there's no automated installer for that platform yet.

## Step 6 — Report what's now running
State plainly the schedule that's now live (the days and lookback window chosen in Step 1), that it polls every 30 min but only acts within 09:00-22:00 Warsaw on the chosen days, and that it writes directly to the shared negative-keyword list with no further review. Point to `clients/$1/reports/` for future logs, and mention the platform-appropriate check-it's-loaded command: `launchctl list | grep <slug>` on macOS, or `schtasks /Query /TN "\<label-prefix>\<slug>-audit" /FO LIST` on Windows.
