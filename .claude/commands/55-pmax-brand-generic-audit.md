---
description: On-demand PMax search term audit — analyzes branded/generic PMax campaigns for exclusion-worthy terms, run interactively with explicit approval before anything is added
---

Run an interactive PMax search-term audit for client **$1**.

Driven entirely by `scripts/client_registry.py` + `clients/$1/client-brief.md` — no hardcoded per-client constants. See "Prerequisites for a new client" below before running it on a client for the first time.

## Prerequisites for a new client
- `scripts/client_registry.py` must have a `negative_list_id` for $1 (general negatives — already required for `/55-keyword-audit`, so likely already set).
- If $1 has any PMax campaign with "branded" in its name, `clients/$1/client-brief.md` needs a `## Brand Terms` (or "Brand Term(s)") heading with a comma-separated list on the next line(s) — same section the negative-keyword audit already relies on.
- That same branded campaign also needs a dedicated exclusion list: run `.venv/bin/python3 scripts/pmax_brand_generic_audit.py $1 --setup` once (creates the shared set, applies it to the branded campaign, and prints the ID to add as `pmax_branded_generic_list_id` in `client_registry.py`). Skip this if $1 has no branded PMax campaign.

## Step 1 — Fetch (read-only, Ads API only)
```
.venv/bin/python3 scripts/pmax_brand_generic_audit.py $1 --phase-fetch --out <fetch.json> --days 4
```
Optional: `--branded-only` or `--generic-only` to scope to one side. Pulls all ENABLED PMax campaigns and up to 2,000 search terms per campaign over the last N days (default 4). If $1 has no ENABLED PMax campaigns, this returns an empty list — say so and stop, don't proceed to analyze.

## Step 2 — Analyze (forks to call `claude` per campaign, no Ads API — judgment step)
Add `--phase-analyze --in <fetch.json> --out <analyze.json> --limit 100 --model sonnet` to Step 1's command.
- **Branded campaigns:** flags terms with zero brand signal as NEGATE — those waste budget triggering a brand campaign on generic intent. Brand signals are read from `clients/$1/client-brief.md`'s "Brand Terms" section — fails loudly if that section is missing rather than silently negating everything.
- **Generic campaigns:** flags terms matching the client brief's "Always Negate" categories — reads `clients/$1/client-brief.md` internally, same brief the negative-keyword audit uses.
- Only the top `--limit` terms by spend per campaign go to the AI (default 100). If a campaign's `terms_total` exceeds `sent_count` in the output, say so when presenting results — the rest weren't reviewed this run.

## Step 3 — Show the full list and get explicit approval
For every campaign in `<analyze.json>`, present: campaign name + type (branded/generic), terms_total vs. sent_count, the full NEGATE list with reasons, and any `error` field (an AI analysis failure — report the campaign as skipped, don't silently treat it as "nothing to negate"). Close with a SUMMARY (campaigns analyzed, total terms negated across all). **Do not run Step 4 until the user explicitly approves this specific list** — same convention as `/55-keyword-audit`, `/55-keyword-expansion`, and `/55-pmax-bucketing`: approval of "run the pmax audit" is not approval of the resulting negate list, that's a separate confirmation.

## Step 4 — Apply, only after approval
`<analyze.json>` is already in the exact shape `--phase-apply` expects — it only reads `id`/`name`/`type`/`negate` per campaign and ignores the rest — so reuse it directly rather than reformatting: `scripts/pmax_brand_generic_audit.py $1 --phase-apply --in <analyze.json> --out <apply.json>`.

**Safe by default** — without `--confirm`, this only ever prints what it would add per campaign and writes nothing. Run it once without `--confirm` first to sanity-check, then add `--confirm` to actually write. Branded-campaign negatives go to `pmax_branded_generic_list_id`; generic-campaign negatives go to `negative_list_id` (both in `client_registry.py`). If a branded campaign has terms to negate but no `pmax_branded_generic_list_id` is set, the apply phase reports an `error` for that campaign instead of writing anywhere — run `--setup` (see Prerequisites) and re-apply.

## Step 5 — Report the result
Read `<apply.json>` and state exactly what was added per campaign (count + which list, e.g. "12 terms → PMax Branded - Generic Exclusions"). Every applied change is also recorded in the shared change log (`scripts/change_log.py show $1` to review it) — no need to hand-parse logs to answer "what has this tool ever changed on this account." If you want this manual run logged as text too, append a summary to `clients/$1/reports/pmax_brand_generic_audit_YYYY-MM-DD_HH-MM.log`, clearly labeled as a manual/interactive run so anyone reading the log later knows a human triggered it, not a scheduled job.
