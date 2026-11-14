---
description: Fast read-only Google Ads pulse-check for one client — conversion tracking, budget pacing, cost/CPA anomalies
---

Run a daily account pulse-check for client **$1**.

1. Run: `.venv/bin/python3 scripts/daily_check.py $1`
   - If `$1` looks wrong or isn't a known client slug, the script will list valid slugs — show that to the user and stop.
2. Read the report's four sections (CONVERSION TRACKING, BUDGET PACING, COST / CPA ANOMALIES, SUMMARY) and present findings conversationally, in plain English, most urgent first:
   - A `[FLAG]` under CONVERSION TRACKING (conversions dropped to zero vs a real baseline) is the highest priority — this can mean broken tracking and is worth surfacing first even if other flags exist.
   - Budget pacing and cost/CPA flags are informational context, not automatically urgent — note them, but don't invent a root cause the data doesn't support (e.g. don't guess "ads got disapproved" unless you actually check disapproval status).
   - If a public holiday note appears in the header, mention it as context for any low-traffic flags in that window.
   - If SUMMARY shows zero flags, just say so briefly — don't pad a clean result with manufactured concerns.
3. This command is strictly read-only — it never proposes or makes account changes. If the findings suggest a fix (e.g. a paused/disapproved ad), say what you'd check next, not what you'd change.
