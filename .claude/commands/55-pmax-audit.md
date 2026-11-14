---
description: On-demand plain irrelevant-keyword audit for Performance Max — the PMax analog of /55-keyword-audit, no branded/generic split, run interactively with explicit approval before anything is added
---

Run an interactive irrelevant-keyword audit of Performance Max search terms for client **$1** (optional: a lookback window, default 4 days — e.g. "last 7 days" → `--days 7`).

**This is the PMax counterpart to `/55-keyword-audit`, not a replacement for `/55-pmax-brand-generic-audit`.** It scans every ENABLED PMax campaign uniformly for terms that don't match what the client actually sells, per `client-brief.md`'s "Always Negate" categories — same judgment `/55-keyword-audit` applies to Search. It does **not** distinguish branded vs. generic PMax campaigns or check brand signal. If $1 has a branded PMax campaign, `/55-pmax-brand-generic-audit` is the right tool for that campaign specifically (it also has its own dedicated exclusion list and setup step); this command is for the general case and works with zero extra setup beyond what `/55-keyword-audit` already needs.

## Step 0 — Ask scope, before the first fetch for this client
Before running Step 1 for the first time in a session for this client, ask two questions (one AskUserQuestion call, two questions):
- **Lookback window**: last 7 days / last 30 days / custom (if $2 already specifies a window, e.g. "last 7 days", skip asking and use that instead)
- **Scope**: all search terms, or only the top 100 by spend, or only the top 100 by impressions — explain this trades completeness for fewer tokens spent classifying terms

Skip this question on a repeat run later in the same session where the user already answered it — reuse their prior choice rather than asking again.

## Step 1 — Fetch the data
Run this first, before doing anything else — it's read-only and its own output tells you what (if anything) is missing:

`.venv/bin/python3 scripts/pmax_audit.py fetch $1 --days <chosen_days> [--top 100 --sort-by <cost|impressions>]`

Omit `--top`/`--sort-by` entirely if the user chose "all search terms". Then handle whichever of these it reports:

**If it exits saying no `negative_list_id` is configured (exit code 3):** this is the exact same shared list `/55-keyword-audit` uses — it already printed the commands to list/set/create one via `negative_keyword_audit.py` (`list-lists`, `set-list --id <ID>`, or `create-list --name "..."`). Walk the user through picking or creating one the same way `/55-keyword-audit`'s Step 1 does, then re-run this command's Step 1 fetch — it only configures the list, it doesn't fetch data itself.

**If it exits saying no `clients/$1/client-brief.md` exists (exit code 2):** ask the user: "This client doesn't have a client-brief.md yet — paste their website URL and I'll auto-draft one (same logic the setup wizard uses), or say skip to write it by hand first."
- If they paste a URL: `.venv/bin/python3 scripts/generate_brief.py $1 <url>`. Tell them plainly afterward that this is an unreviewed draft and they should skim it now for anything obviously wrong (wrong products, wrong geography) before it drives real judgment in the next steps. Then re-run the Step 1 fetch command.
- If they skip: stop here and tell them to fill in `clients/$1/client-brief.md` by hand, then re-run this command.

**If it exits saying no ENABLED PMax campaigns were found (exit code 4):** say so and stop — nothing to audit.

**If it succeeds:** it printed the client brief and the merged PMax search terms (deduplicated across campaigns, since the same term can trigger more than one PMax campaign) — continue to Step 2.

## Step 2 — Classify using the client's own brief (judgment, not scripted)
Read the printed client brief carefully — it defines the client's actual products/categories, languages considered valid, and anything explicitly protected from negation. Classify each search term:
- **NEGATED (exact match)** — genuinely irrelevant to this client: wrong product category the client doesn't sell, informational/DIY queries, job searches, wrong audience, or wrong geography — per that specific client's brief, not a generic list. What counts as "irrelevant" varies entirely by client and vertical; don't assume a pattern from one client applies to another.
- **KEPT (borderline)** — flagged but not negated, with a one-line reason. PMax leans on Google's own automated targeting more than Search does, so when a term shows real product/purchase intent but arrived through looser matching, keep it — the bar for negating is the brief's "Always Negate" categories, not "this term looks unusual for PMax."
- **BROAD MATCH ADDITIONS** — a specific competitor brand name or a discontinued/unavailable product/model that recurs in 2+ of this run's exact-match negatives. Only the specific brand/model token itself, never a generic category/service/geography word even if it recurs.

Write the plan to a JSON file: `{"exact": [...], "broad": [...]}`.

## Step 3 — Show the full list and get explicit approval
Present all 4 sections before asking to proceed, same tagged format the scheduled `/55-keyword-audit` automation writes to its log (see `clients/$1/scripts/run_audit.sh` if it exists, for the exact convention):
1. **NEGATED** — every term added this run, one per line: `[NEGATED] term | reason (2 words max)`
2. **KEPT (borderline)** — every term flagged but not negated, with why: `[KEPT] term | reason`
3. **BROAD MATCH ADDITIONS** — recurring competitor brand/discontinued-model tokens added as broad negatives: `[BROAD] token | appeared in N exact-match terms above` (or "(none this run)")
4. **SUMMARY** — `Terms reviewed: N`, `Negated this run: N`, `Kept: N`, `Broad match additions: N` (this exact phrasing — the dashboard's report parser matches on it)

List every term in NEGATED and KEPT, not just counts — the point of this step is the user can see exactly which keywords were excluded and which were kept, same as they would from a `/55-keyword-audit` run. **Do not call the apply step until the user has explicitly approved this specific list** — approval of "run the audit" is not approval of the resulting negative list; that's a separate confirmation, same convention as `/55-keyword-audit`, `/55-keyword-expansion`, `/55-pmax-bucketing`, and `/55-pmax-brand-generic-audit`.

## Step 4 — Apply, only after approval
`.venv/bin/python3 scripts/add_shared_negatives.py $1 --plan <path> --confirm`

Same apply script `/55-keyword-audit` uses — it writes to the same shared list via `SharedCriterionService.mutate_shared_criteria`, EXACT match for the main list and BROAD match for the recurring-token additions. Without `--confirm` it's a dry run (prints what it would do, changes nothing) — useful to sanity-check the plan file itself before the real write.

## Step 5 — Report the result
State exactly what was added (counts for exact vs. broad, and call out any that failed — the apply script reports failures per-term, not just an aggregate). If you want this run to show up in the dashboard's report history, append the same 4-section output from Step 3 (full NEGATED/KEPT/BROAD lists, not just the summary counts) to `clients/$1/reports/pmax_audit_YYYY-MM-DD_HH-MM.log`, clearly labeled as a manual/interactive run so anyone reading the log later — including the dashboard's report view — can see exactly which keywords were excluded and which were kept, not just that the run happened.
