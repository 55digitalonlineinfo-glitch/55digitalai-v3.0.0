---
description: Set up the unattended scheduled PMax brand/generic-split search-term automation for a client — choose a schedule, scaffold, review, test, and install in one guided flow
---

Set up scheduled automation for client **$1**. This turns the manual, one-off `/55-pmax-brand-generic-audit` into a standing routine that runs unattended on its own schedule and writes to the account with no human review — same pattern as `/55-setup-pmax-audit-automation`, just for the branded/generic-split PMax audit instead of the plain scanner.

**This is the branded/generic-split automation, not `/55-pmax-audit`'s.** It classifies PMax campaigns as branded vs. generic by name and applies different judgment to each: branded campaigns get non-brand terms excluded, generic campaigns get irrelevant terms excluded per the client brief. Branded exclusions go to a dedicated `pmax_branded_generic_list_id` list; generic exclusions go to the same shared `negative_list_id` the Search keyword audit uses. If $1 needs the plain uniform scanner instead (or in addition), that's `/55-setup-pmax-audit-automation` — a separate setup.

**This is not a read-only command.** The test step and every real scheduled run after it write live to the account with `pmax_brand_generic_audit.py --confirm` and no approval step — that's the entire point of this automation, not a bug. Because of that, walk through the steps below in order and don't skip the confirmation in Step 4 just to save time.

## Step 0 — Check prerequisites
$1 needs, already set up before this command is useful:
- A `customer_id` **and** a `negative_list_id` in `clients.json` — same fields `/55-setup-pmax-audit-automation` requires
- A filled-in `clients/$1/client-brief.md` (not the unreviewed auto-draft — this brief drives the AI's judgment on every unattended run for generic campaigns, and its "## Brand Terms" section drives judgment for branded campaigns, so a thin or wrong brief means thin or wrong judgment with nobody reviewing it after the fact)
- At least one ENABLED Performance Max campaign — check with `.venv/bin/python3 scripts/pmax_brand_generic_audit.py $1 --phase-fetch --out /tmp/check.json --days 4` if unsure, or just look at `campaign_analyst.py list $1`
- **If $1 has any ENABLED PMax campaign with "branded" in its name**: `clients/$1/client-brief.md` needs a "## Brand Terms" section (comma-separated list), AND `clients.json` needs a `pmax_branded_generic_list_id` — run `.venv/bin/python3 scripts/pmax_brand_generic_audit.py $1 --setup` once if it's missing (creates the shared exclusion list, applies it to the branded campaign, prints the ID to add to `client_registry.py`). Without this, the scheduled run will error on that campaign's negatives instead of writing anywhere — it won't silently misfire, but it also won't do anything useful for that campaign.

If any of these is missing, stop here and say so plainly — don't generate a script that will misfire or run against nothing.

## Step 1 — Ask which days to run, and how far back to look
Use one AskUserQuestion call with two questions:

- **Which days?** Recommend **Tuesday and Friday** as the default, same as the keyword-audit and plain-PMax automations — it spreads review across the week and doesn't burn through Claude Pro session usage the way a daily run would. If $1 already has `/55-keyword-audit` or `/55-pmax-audit` scheduled, suggest matching the same days so all of this client's launchd slots overlap and share the workspace lock efficiently rather than fragmenting across different days. Offer alternatives: daily (high-spend, fast-moving PMax accounts), or once a week (low-spend/stable accounts).
- **How many days to look back each run?** Recommend a lookback that covers the gap since the last run plus a small buffer — for the Tue/Fri default that's **4 days**. If the user picks a different schedule, adjust with them: daily → 2-3 days; once a week → 7-8 days.

Map their answer to the actual flags: `--weekdays mon,tue,wed,thu,fri,sat,sun` (comma-separated, any subset) and `--lookback-days N`.

## Step 2 — Generate the script
`.venv/bin/python3 scripts/scaffold_pmax_brand_generic_audit.py $1 --weekdays <chosen> --lookback-days <chosen>`

This only writes `clients/$1/scripts/run_pmax_brand_generic_audit.sh` — no API calls, no writes, nothing live yet. Unlike the plain PMax audit's scaffold, this generated script doesn't embed its own AI prompt — it's a thin wrapper around `pmax_brand_generic_audit.py --confirm`, which already reads `client-brief.md` fresh and does its own fetch/analyze/apply internally. If the script already exists, ask before passing `--force` to overwrite a possibly hand-tuned version.

## Step 3 — Show the user what was generated
Since the judgment logic lives in `pmax_brand_generic_audit.py` (reads the brief live every run) rather than a baked-in prompt, there's no per-schedule prompt text to review — instead, walk the user through `clients/$1/client-brief.md`'s "Brand Terms" and "Always Negate"/"Protected" sections and confirm they're accurate and current, since that's what every unattended run will judge against. Point out anything that seemed thin (e.g. no Brand Terms section despite having a branded campaign, vague Always Negate categories). Confirm the schedule and lookback window match what they chose in Step 1, and confirm `pmax_branded_generic_list_id` is set if relevant (Step 0).

## Step 4 — Confirm, then run the live test
**Explicitly ask the user before running this** — don't treat proceeding past Step 3 as implied consent. Tell them plainly: this will write real negatives to the live account right now (branded campaigns' non-brand terms to `pmax_branded_generic_list_id`, generic campaigns' irrelevant terms to `negative_list_id`), the same as the first scheduled run would.

Once confirmed: `AUDIT_FORCE=1 bash clients/$1/scripts/run_pmax_brand_generic_audit.sh`

Report exactly what got added per campaign (check `clients/$1/reports/pmax_brand_generic_audit_YYYY-MM-DD.log` for the NEGATE lists and SUMMARY per campaign) — same as reporting the result of any other write in this toolkit.

## Step 5 — Install the schedule
Only after the user is satisfied with the test result. This step is platform-specific — check which OS this machine is running and use the matching script; both mirror the same job list from `clients.json` and install the identical always-on half-hourly poller pattern, just via a different OS scheduler:
- **macOS**: `.venv/bin/python3 scripts/setup_launchd.py --only $1-pmax-brand-generic-audit`
- **Windows**: `.venv/bin/python3 scripts/setup_task_scheduler.py --only $1-pmax-brand-generic-audit` (requires Git for Windows for the `bash.exe` that runs `run_pmax_brand_generic_audit.sh` — see `scripts/setup_wizard.py`'s `ensure_claude_cli()` / `offer_scheduled_automation_setup()` for the other Windows prerequisites if not already run)

If neither applies (e.g. Linux), say so plainly and point to `SCHEDULING.md`'s cron section for the manual equivalent.

Use the full `$1-pmax-brand-generic-audit` label, not just `$1` — the bare slug would also match this client's existing `$1-audit` (keyword-audit) or `$1-pmax-audit` (plain PMax audit) jobs if either is already installed, and reinstall them unintentionally.

## Step 6 — Report what's now running
State plainly the schedule that's now live (the days and lookback window chosen in Step 1), that it polls every 30 min but only acts within 09:00-22:00 Warsaw on the chosen days, and that it writes directly to the account with no further review — branded exclusions to one list, generic exclusions to another. Point to `clients/$1/reports/` for future logs, and mention the platform-appropriate check-it's-loaded command: `launchctl list | grep $1-pmax-brand-generic-audit` on macOS, or `schtasks /Query /TN "\<label-prefix>\$1-pmax-brand-generic-audit" /FO LIST` on Windows.
