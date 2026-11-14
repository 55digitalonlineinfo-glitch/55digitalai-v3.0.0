---
description: On-demand negative keyword audit — same analysis as the scheduled Tue/Fri automation, run interactively with explicit approval before anything is added
---

Run an interactive negative-keyword audit for client **$1** (optional: a lookback window, default 4 days, matching the scheduled routine — e.g. "last 7 days" → `--days 7`).

**This is the interactive counterpart to the scheduled automation already documented in CLAUDE.md's "Automated Routines" section for this client — same rules, same shared list, same judgment process. The difference is entirely about consent:** the scheduled automation is a pre-approved standing routine that writes unattended every Tue/Fri; this command is a manual, one-off run, and manual runs always show the full proposed list and get explicit approval before writing anything — never skip the confirmation step just because "the automated version doesn't ask." A user running this by hand is asking for a review, not a silent apply.

## Step 0 — Ask scope, before the first fetch for this client
Before running Step 1 for the first time in a session for this client, ask two questions (one AskUserQuestion call, two questions):
- **Lookback window**: last 7 days / last 30 days / custom (if $2 already specifies a window, e.g. "last 7 days", skip asking and use that instead)
- **Scope**: all search terms, or only the top 100 by spend, or only the top 100 by impressions — explain this trades completeness for fewer tokens spent classifying terms

Skip this question on a repeat run later in the same session where the user already answered it — reuse their prior choice rather than asking again.

## Step 1 — Fetch the data
Run this first, before doing anything else — it's read-only and its own output tells you what (if anything) is missing:

`.venv/bin/python3 scripts/negative_keyword_audit.py fetch $1 --days <chosen_days> [--top 100 --sort-by <cost|impressions>]`

Omit `--top`/`--sort-by` entirely if the user chose "all search terms". Then handle whichever of these it reports:

**If it exits saying no `negative_list_id` is configured (exit code 3):** it already printed the account's existing shared negative-keyword lists (ID, name, keyword count, campaigns attached), if any exist. Don't just stop here — help the user pick one:
- If lists were printed: show them to the user and ask which to use (or whether to create a new one instead). Once chosen: `.venv/bin/python3 scripts/negative_keyword_audit.py set-list $1 --id <ID>`.
- If none exist (script said so explicitly): ask the user for a name for a new list (default suggestion: "`<client name>` - Negative Keywords") and whether to attach it to every enabled campaign now. Then: `.venv/bin/python3 scripts/negative_keyword_audit.py create-list $1 --name "..." [--attach-all]`.
- Either way, re-run the Step 1 fetch command afterward — `set-list`/`create-list` only configure the list, they don't fetch data.

**If it exits saying no `clients/$1/client-brief.md` exists (exit code 2):** ask the user: "This client doesn't have a client-brief.md yet — paste their website URL and I'll auto-draft one (same logic the setup wizard uses), or say skip to write it by hand first."
- If they paste a URL: `.venv/bin/python3 scripts/generate_brief.py $1 <url>`. Tell them plainly afterward that this is an unreviewed draft — same as the wizard's own warning — and they should skim it now for anything obviously wrong (wrong products, wrong geography) before it drives real judgment in the next steps. Then re-run the Step 1 fetch command.
- If they skip: stop here and tell them to fill in `clients/$1/client-brief.md` by hand, then re-run this command.

**If it succeeds:** it printed the client brief and the search terms — continue to Step 2.

## Step 2 — Classify using the client's own brief (judgment, not scripted)
Read the printed client brief carefully — it defines the client's actual products/categories, languages considered valid, and anything explicitly protected from negation. Classify each search term:
- **NEGATED (exact match)** — genuinely irrelevant to this client: wrong product category the client doesn't sell, informational/DIY queries, job searches, wrong audience, or wrong geography — per that specific client's brief, not a generic list. What counts as "irrelevant" varies entirely by client and vertical; don't assume a pattern from one client (an off-topic beverage category, say) applies to another (a different client's off-topic categories will be different products entirely).
- **KEPT (borderline)** — flagged but not negated, with a one-line reason.
- **BROAD MATCH ADDITIONS** — a specific competitor brand name or a discontinued/unavailable product/model that recurs in 2+ of this run's exact-match negatives. Only the specific brand/model token itself, never a generic category/service/geography word even if it recurs (a recurring generic word usually means real, legitimate demand — negating it broadly would block the client's own traffic, not save spend).

Write the plan to a JSON file: `{"exact": [...], "broad": [...]}`.

## Step 3 — Show the full list and get explicit approval
Present all 4 sections before asking to proceed, same format as the scheduled automation's log output: NEGATED (numbered, with a short reason each), KEPT (borderline, with reason), BROAD MATCH ADDITIONS (or "none this run"), and a SUMMARY (terms reviewed / negated / kept / broad additions). **Do not call the apply step until the user has explicitly approved this specific list** — approval of "run the audit" is not approval of the resulting negative list; that's a separate confirmation, same convention as `/55-keyword-expansion` and `/55-pmax-bucketing`.

## Step 4 — Apply, only after approval
`.venv/bin/python3 scripts/add_shared_negatives.py $1 --plan <path> --confirm`

Without `--confirm` it's a dry run (prints what it would do, changes nothing) — useful to sanity-check the plan file itself before the real write. Uses `SharedCriterionService.mutate_shared_criteria` (same `add_negatives` pattern as `scripts/pmax_brand_generic_audit.py`), EXACT match for the main list and BROAD match for the recurring-token additions.

## Step 5 — Report the result
State exactly what was added (counts for exact vs. broad, and call out any that failed — the apply script reports failures per-term, not just an aggregate). If you want this run to show up in the same report history as the scheduled automation, append a summary to `clients/$1/reports/keywords_audit_YYYY-MM-DD.log`, clearly labeled as a manual/interactive run (not to be confused with an automated one) so anyone reading the log later knows a human triggered it.

## Step 6 — Offer to schedule this going forward
Only ask this if `clients/$1/scripts/run_audit.sh` doesn't already exist (if it does, this client is already scheduled or already declined it — don't ask again every run). Ask one question: "Want this client's keyword audit to run automatically going forward (e.g. every Tue/Fri) instead of by hand each time?" If yes, run `/55-setup-keyword-audit-automation $1`. If no, stop — nothing further needed, they can just run `/55-keyword-audit $1` manually again whenever.
