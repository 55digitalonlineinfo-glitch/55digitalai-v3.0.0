---
description: Year-over-year seasonality analysis at 4 levels — campaigns, product types, brands, individual products — distinguishing a seasonal dip from a real account problem
---

Run the seasonality analysis for client **$1** (optional: a target month like "March 2026" → `--month 2026-03`). Read-only — this never writes to the account.

## Step 1 — Run it
`.venv/bin/python3 scripts/seasonality.py $1 [--month YYYY-MM] [--top 10]`

Default target month is the most recently completed calendar month.

## Step 2 — Know the real limitations before presenting this to a client
Not every client can get the full 4-level treatment — check each client's actual data before assuming it works:

1. **Needs ~13 months of account history** (the target month, the month before it, the same month last year, and the month before that last year). Clients with less than that will only have a partial window — the script detects this and refuses to fake a shorter-window comparison, it just says so. If a client returns 0 months, that's a data-availability question to look into separately, not a bug in this script.
2. **Product types, brands, and individual products all require a Shopping/PMax product feed** (queried via `shopping_performance_view`). A client without a feed can't get levels 2-4, regardless of history length — check both conditions before promising the full treatment for a given client.
3. Even with enough history and a feed, **"product types" and "brands" can still collapse to a single row** if the feed's `product_type_l1/l2/l3` or `product_brand` fields aren't populated with distinguishing values per product line — that's a feed data-quality gap on the client's side (they'd need to set a distinguishing custom `product_type` value per product line, e.g. "Beer" / "Distillates" / "Gift Sets"), not something fixable in this script. "Individual products" is unaffected since `product_item_id`/`product_title` are already granular per SKU.

**In short: confirm which level(s) actually work for a given client before running this** — don't imply a level works when it structurally can't yet for that account.

## Step 3 — Read the verdicts correctly
Each row compares 4 numbers for the chosen metric (cost, by default): this month, last month, same month last year, and the month before that last year. The verdict:
- **SEASONAL** — this year's month-over-month move is within 15 percentage points of last year's same-calendar transition, same direction. Genuinely "this happens every year," safe to tell the client it's not an account problem.
- **MIXED** — same direction as last year, but a materially bigger swing (15-30pt gap) — probably still seasonal, but with something amplifying it worth a quick look.
- **ANOMALY** — different direction from last year, or a 30+pt gap. This is the one to actually investigate — e.g. a campaign whose cost jumps several-hundred-percent month-over-month with no matching pattern the year before. Always manually verify the raw numbers behind a flagged anomaly, don't just trust the label.
- **n/a — missing a comparison month** — the entity didn't exist (or had zero spend) in one of the 4 needed months, most often because a campaign is newer than the account's full history. Don't read this as "no verdict, ignore" — say explicitly it's a newer campaign with no prior-year baseline.

## Step 4 — Answer with commentary
Lead with ANOMALY rows first (they're the ones needing attention), then SEASONAL rows as reassurance ("this dip matches the same time last year, not a new problem"). Always name the actual entity and numbers, never just the verdict label.
