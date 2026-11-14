---
description: Merchant Center product feed health in one place — approval status per destination, disapprovals with concrete reasons, free-listings monitoring, and (where enabled) price vs. competitor benchmark
---

Run the Merchant Center feed review for client **$1**. Read-only — this never writes to Merchant Center or Google Ads.

## Step 1 — Run it
`.venv/bin/python3 scripts/merchant_review.py $1`

If the client has no `merchant_center_id` in `scripts/client_registry.py`, the script says so — don't guess an ID. Only clients with an actual product feed will have this set.

## Step 2 — Read the output correctly
The output has 4 sections:
1. **Feed Overview** — total products and a per-destination table (Shopping, Free Listings/`SurfacesAcrossGoogle`, Display Ads). It shows Google's own top-level rollup (approved/disapproved/pending) *and* a separately-computed "actually blocking" count.
2. **Disapprovals & Issues** — every item-level issue code, grouped by destination, with severity (`BLOCKING` vs. `flagged, not blocking`), affected product count, and a concrete example (description + detail + product link).
3. **Free Listings Monitoring** — the servability-based eligibility read, scoped to `SurfacesAcrossGoogle`, **plus real impressions/clicks/CTR straight from Merchant Center's own `MerchantPerformanceView`** (segmented by `FREE_PRODUCT_LISTING` vs `SHOPPING_ADS`) — this is the authoritative traffic number, not an approximation — and a **top-10-products-by-free-listing-impressions table** (same view, segmented by `offer_id`/`title`) that flags any product getting real impressions but zero clicks as a listing-quality problem (title/image/price), not a visibility problem. A GA4 `Organic Shopping` channel cross-check runs alongside purely as a tracking-health sanity check — if Merchant Center reports meaningfully more impressions/clicks on free listings than GA4's Organic Shopping channel shows for the same window, that gap is usually GA4 undercounting (consent-mode cookie loss / channel-classification misses), not real clicks vanishing. Always trust the Merchant Center numbers as the real traffic figure.
4. **Price Comparison vs. Competitors** — only populates if Google's `PriceCompetitivenessProductView` is available for the account. This is **not** an API- or UI-enrollable "program" like free-listings/shopping-ads — per Google's own docs it's an auto-computed analytics view (Merchant Center → Analytics → Products → Competitors tab) gated on Google's internal eligibility (enough competitor/category benchmark data for that country/category), not something a merchant or this script can switch on. If unavailable, the API returns a 400 "invalid field name" — likely a data-coverage gap for that country/category, not a missing setup step. If a client wants real competitor pricing regardless, the alternative is a small scraper against named competitor product URLs the client supplies — not something this script can discover on its own.

**Read section 1/2/3's "rollup" vs. "actually blocking" numbers carefully — they can legitimately disagree.** Google's destination-level rollup can mark products "disapproved" for a destination even when the underlying issue's servability is `unaffected` for that destination — only issues whose servability is genuinely blocking for that destination represent a real problem. The script's own "CAVEAT" line calls this out explicitly whenever rollup and actually-blocking disagree. **Do not tell a client their whole feed is disapproved for Shopping based on the rollup number alone** — cross-check against Ads campaign performance (if a Shopping/PMax campaign fed by this feed is still getting real impressions/clicks, the destination is very likely still serving) and, for anything that looks like a genuine live problem, tell the user to confirm in Merchant Center's own Diagnostics page before acting.

## Step 3 — Answer with commentary
Lead with the concrete, currently-blocking issues (servability `BLOCKING` in section 2) — those are the ones that need merchant action. Treat "flagged, not blocking" issues as lower-priority housekeeping (e.g. image resolution). Only escalate a destination-level "disapproved" rollup as urgent if section 2 shows a matching blocking issue for that same destination — otherwise present it as the caveat it is, not a fire to put out.
