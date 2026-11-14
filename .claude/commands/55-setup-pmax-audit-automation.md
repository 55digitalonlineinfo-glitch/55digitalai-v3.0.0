---
description: Set up the unattended scheduled plain PMax irrelevant-keyword automation for a client — choose a schedule, scaffold, review, test, and install in one guided flow
---

Set up scheduled automation for client **$1**. This turns the manual, one-off `/55-pmax-audit` into a standing routine that runs unattended on its own schedule and writes to the account with no human review — same pattern as `/55-setup-keyword-audit-automation`, just for Performance Max search terms instead of Search.

**This is the plain-scanner automation, not `/55-pmax-brand-generic-audit`'s.** It scans every ENABLED PMax campaign uniformly, no branded-vs-generic split, and writes to the same shared negative-keyword list the Search keyword audit uses. If $1 needs the branded/generic-split automation instead (or in addition), that's a separate setup — this command only covers `/55-pmax-audit`.

**This is not a read-only command.** The test step and every real scheduled run after it write live to the client's shared negative-keyword list, with `--dangerously-skip-permissions` and no approval step — that's the entire point of this automation, not a bug. Because of that, walk through the steps below in order and don't skip the confirmation in Step 4 just to save time.

## Step 0 — Check prerequisites
$1 needs, already set up before this command is useful:
- A `customer_id` **and** a `negative_list_id` in `clients.json` — the exact same fields `/55-setup-keyword-audit-automation` requires, since this writes to the same shared list (if `negative_list_id` is missing: `python3 scripts/negative_keyword_audit.py list-lists $1`, then `set-list`/`create-list`)
- A filled-in `clients/$1/client-brief.md` (not the unreviewed auto-draft — this brief drives the AI's judgment on every unattended run, so a thin or wrong brief means thin or wrong judgment with nobody reviewing it after the fact)
- At least one ENABLED Performance Max campaign on the account — if unsure, check with `.venv/bin/python3 scripts/pmax_audit.py fetch $1` (it exits with a clear message if there are none)

If any of these is missing, stop here and say so plainly — don't generate a script that will misfire or run against nothing.

## Step 1 — Ask which days to run, and how far back to look
Use one AskUserQuestion call with two questions:

- **Which days?** Recommend **Tuesday and Friday** as the default, same as the keyword-audit automation — it spreads review across the week and doesn't burn through Claude Pro session usage the way a daily run would. If $1 already has `/55-keyword-audit` scheduled, suggest matching the same days so both audits' launchd slots overlap and share the workspace lock efficiently rather than fragmenting across different days. Offer alternatives: daily (high-spend, fast-moving PMax accounts), or once a week (low-spend/stable accounts).
- **How many days to look back each run?** Recommend a lookback that covers the gap since the last run plus a small buffer — for the Tue/Fri default that's **4 days**. If the user picks a different schedule, adjust with them: daily → 2-3 days; once a week → 7-8 days.

Map their answer to the actual flags: `--weekdays mon,tue,wed,thu,fri,sat,sun` (comma-separated, any subset) and `--lookback-days N`.

## Step 2 — Generate the script
`.venv/bin/python3 scripts/scaffold_pmax_audit.py $1 --weekdays <chosen> --lookback-days <chosen>`

This only writes `clients/$1/scripts/run_pmax_audit.sh` from `client-brief.md` — no API calls, no writes, nothing live yet. If it already exists, ask before passing `--force` to overwrite a possibly hand-tuned version.

## Step 3 — Show the user what was generated
Read the generated prompt back and summarize in plain language what it will and won't negate, per the client's brief — this is their one chance to catch a wrong assumption before it runs unattended. Point out anything in the brief that seemed thin (e.g. no protected-terms section, vague geography) since that directly limits how good the automated judgment can be. Confirm the schedule and lookback window match what they chose in Step 1.

## Step 4 — Confirm, then run the live test
**Explicitly ask the user before running this** — don't treat proceeding past Step 3 as implied consent. Tell them plainly: this will write real negatives to the live shared list right now, the same as the first scheduled run would.

Once confirmed: `AUDIT_FORCE=1 bash clients/$1/scripts/run_pmax_audit.sh`

Report exactly what got added (check `clients/$1/reports/pmax_audit_YYYY-MM-DD.log` for the NEGATED/KEPT/BROAD MATCH sections) — same as reporting the result of any other write in this toolkit.

## Step 5 — Install the schedule
Only after the user is satisfied with the test result. This step is platform-specific — check which OS this machine is running and use the matching script; both mirror the same job list from `clients.json` and install the identical always-on half-hourly poller pattern, just via a different OS scheduler:
- **macOS**: `.venv/bin/python3 scripts/setup_launchd.py --only $1-pmax-audit`
- **Windows**: `.venv/bin/python3 scripts/setup_task_scheduler.py --only $1-pmax-audit` (requires Git for Windows for the `bash.exe` that runs `run_pmax_audit.sh` — see `scripts/setup_wizard.py`'s `ensure_claude_cli()` / `offer_scheduled_automation_setup()` for the other Windows prerequisites if not already run)

If neither applies (e.g. Linux), say so plainly and point to `SCHEDULING.md`'s cron section for the manual equivalent.

Use the full `$1-pmax-audit` label, not just `$1` — the bare slug would also match this client's existing `$1-audit` (keyword-audit) job if one is already installed, and reinstall it unintentionally.

## Step 6 — Report what's now running
State plainly the schedule that's now live (the days and lookback window chosen in Step 1), that it polls every 30 min but only acts within 09:00-22:00 Warsaw on the chosen days, and that it writes directly to the shared negative-keyword list with no further review. Point to `clients/$1/reports/` for future logs, and mention the platform-appropriate check-it's-loaded command: `launchctl list | grep $1-pmax-audit` on macOS, or `schtasks /Query /TN "\<label-prefix>\$1-pmax-audit" /FO LIST` on Windows.
