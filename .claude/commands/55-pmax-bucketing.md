---
description: PMax product segmentation — splits the Merchant Center feed into 4 performance tiers (Platinum/Gold/Silver/Bronze) and proposes separate campaigns with their own budget + target ROAS, so top performers aren't diluted by weak products sharing one campaign's Smart Bidding signal
---

Run PMax bucketing for client **$1**. Two-step, read-then-write process — never skip the approval step, even if the user already approved the general approach.

## Prerequisites
Reads `customer_id` from `client_registry.py`; the Merchant Center `merchant_id`/`feed_label` are read directly off the client's own enabled PMax campaigns, not from the registry, so no extra per-client setup is needed. Only a client with at least one ENABLED PMax campaign backed by a Merchant Center feed can use this command — the `check` step exits with a clear message (not a stack trace) if there are no ENABLED PMax campaigns or no ELIGIBLE feed products.

## Step 1 — Check (read-only)
Run: `.venv/bin/python3 scripts/pmax_bucketing.py $1 check --days 90 --out clients/$1/reports/pmax_bucketing_plan_$(date +%Y-%m-%d).json`

This pulls 90-day product performance across all enabled PMax campaigns, buckets every active feed product into a tier by cumulative revenue share (Platinum ≤50%, Gold 50–80%, Silver 80–100%, Bronze = zero revenue), and proposes a daily budget + target ROAS per tier. **Makes zero account changes.** Writes a plan JSON that Step 3 will read from.

## Step 2 — Present findings and get explicit approval
Show the user the full tier breakdown (SKU counts, revenue, ROAS, proposed budget/tROAS per tier) and the sample SKU list for Platinum/Gold. Flag two things every time:
- **Bronze is not a campaign proposal** — it's a recommendation to exclude proven-wasteful products (spent money, zero conversions) from spend. Only genuinely untested (zero-spend) SKUs get a token test allocation, and only if the user explicitly asks for it via `--include-bronze`. For most catalogs, the bulk of Bronze is proven-wasteful spend rather than untested inventory, so it doesn't warrant its own campaign by default.
- **If Platinum/Gold combined are only a handful of SKUs** — this happens with smaller catalogs — point out that a single-SKU campaign gives Smart Bidding very little to learn from. Offer the option to merge Platinum+Gold into one tier, or re-run Step 1 with `--days 180` for a bigger sample, before proceeding.

**Always stop here and wait for explicit approval before creating anything — do not run apply automatically, even if the user already approved the general approach.** Approval of the method is not approval of the specific resulting tier/budget/tROAS numbers.

## Step 3 — Apply (only after explicit approval)
Run: `.venv/bin/python3 scripts/pmax_bucketing.py $1 apply --plan <plan.json from Step 1> --confirm`

This creates one new "feed only" PMax campaign per tier (matching the account's existing feed-only pattern — no manual creative assets, just a final URL, relies on the Merchant Center feed) with its own budget, `MAXIMIZE_CONVERSION_VALUE` bidding at the approved target ROAS, and a listing-group-filter tree scoped to exactly that tier's product IDs plus a catch-all exclusion for everything else.

**Every new campaign is created PAUSED — never auto-enabled.** Tell the user what was created (campaign resource names, one per tier) and that they need to review and manually enable each in the Ads UI once satisfied. Nothing in this account is deleted or paused by this step — it runs safely alongside the existing campaigns; the old campaigns keep running with their current history and Smart Bidding learning untouched until the user decides to wind them down. Every created campaign is also recorded in the shared change log (`scripts/change_log.py show $1`).

Without `--confirm`, this step is also a dry run — it prints which campaigns it would create per tier and writes nothing, useful as a final sanity check on the plan before committing.

If the user wants Bronze's untested SKUs to also get a minimal test campaign, add `--include-bronze` to the apply command. Bronze's item list is only the genuinely zero-spend SKUs (the proven-wasteful ones are never bid on); its proposed tROAS is the blended Platinum/Gold/Silver ROAS used as a placeholder, since untested SKUs have no performance history of their own to base a target on.

## Re-running for a client that already has a prior bucketing run
If the client already has campaigns from an earlier bucketing run (check with `.venv/bin/python3 scripts/change_log.py show $1`, or search campaign names for "bucketing"), you have two different options depending on what the user actually wants:

**Re-bucket in place (move products, don't duplicate campaigns) — the usual choice.** Add `--sync` to `apply`. For any tier whose campaign already exists (matched by name), this reads its current product assignment, diffs it against the latest plan, and adds/moves/removes only the product listing-group-filters that changed — a product whose tier shifted (e.g. Silver → Platinum) gets moved out of one campaign's filters and into the other's. It never touches an existing campaign's budget or target ROAS (those stay exactly as set when created/last edited), and it never creates a duplicate campaign for a tier that already has one. Tiers with no existing campaign yet still go through the normal create path alongside it. Always preview first: `apply --plan <new plan.json> --sync` (no `--confirm`) prints exactly what would be added/moved-in/moved-out/removed per tier before anything changes. `--sync` cannot be combined with `--only` — a move touches both the source and destination tier's asset group in the same pass, so restricting to one tier could strand a product with nowhere to land.

**Stand up a second, fully parallel structure instead** — a genuinely different case, e.g. testing a new budget/tROAS approach side-by-side with the old one:
- Add `--suffix " - v2"` (or `" - v3"`, etc.) to create the new run's campaigns under distinct names alongside the old ones. Note this does **not** remove products from the old campaigns — the same SKU can end up targeted by both until you manually pause/adjust the old structure.
- Add `--only <Tier>` to (re-)create just one tier — useful when resuming after some tiers already succeeded in a prior partial run. (Not compatible with `--sync`.)

Without either `--sync` or a fresh `--suffix`, `apply` will hit `DUPLICATE_CAMPAIGN_NAME` on any tier whose name collides — this is expected and handled gracefully (no stack trace, no orphaned campaign), not a bug to route around manually; the printed hint points at `--sync` or `--suffix`.

If a tier's asset-group creation fails after its campaign was already created (e.g. a bad `final_url`/domain mismatch), `apply` automatically rolls back the partial campaign it just created rather than leaving an orphan — check the printed hint, fix the root cause (often the `domain` field in `clients.json` for this client), then re-run with `--only <Tier>`.
