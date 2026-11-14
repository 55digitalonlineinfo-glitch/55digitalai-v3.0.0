---
description: Build a self-contained, client-facing GA4 HTML dashboard (all 43 predefined reports, visualized) — always confirms which event counts as a real conversion before building
---

Build the GA4 HTML dashboard for client **$1**. Read-only — this never writes to the account.

## Step 1 — Find out what "conversion" really means for this account
Run: `.venv/bin/python3 scripts/ga4_dashboard.py $1 --list-events --days 30`

This prints every real event fired in the period, with two columns: GA4's native `conversions` count (a raw total of every event marked a "key event" in the property — **not** unique conversions, and often inflated by passive events like `view_item`/`page_view` also being marked as key events) and the true `eventCount` (real occurrences). It also prints a recommended `--conversion-event` pick.

**Never skip straight to building the dashboard on GA4's default blended `conversions` metric without checking this first** — on a real account this showed 22,066 "conversions" against 9,903 sessions, and the breakdown revealed `view_item` + `view_item_list` (pure browsing) made up 84% of that number, with actual `purchase` under 1%. Trusting the blended default without checking would have shipped a materially misleading headline number to the client.

## Step 2 — Ask the user which event(s) should count
Present the event breakdown and the recommended pick, then ask (don't just proceed on the recommendation silently):
- The recommended event (as the default option) — explain briefly why it was picked (e.g. "the standard ecommerce purchase event, present with real volume").
- **Use GA4's default blended `conversions` metric instead** — present as an explicit but not-recommended alternative, and say why it's not recommended (includes passive/structural events).
- A different event, or a comma-separated combination (e.g. `purchase,generate_lead` for a hybrid business) — free text.

If the recommendation came back low-confidence (no standard event name matched), say so plainly and lean harder on showing the user the real breakdown rather than pushing the guess.

## Step 3 — Build it
Run: `.venv/bin/python3 scripts/ga4_dashboard.py $1 --days 30 --conversion-event <their choice>` (omit `--conversion-event` entirely only if they explicitly chose the GA4 default).

This pulls all 43 predefined reports (24 for lead-gen clients — ecommerce-only ones auto-skip), classifies each into a KPI tile / trend chart / bar-and-table / table-only view, and writes a single self-contained HTML file to `clients/$1/reports/ga4_dashboard_<date>.html` (`--out <path>` to override). Takes a bit — it's 43 sequential GA4 Data API calls.

Whenever `--conversion-event` was used, the built dashboard visibly says so (a note under the period line, in the accent color) — every "Conversions" figure throughout the dashboard (Overview KPI, and any of the 15 reports that use the `conversions` metric: `acquisition_channels`, `source_medium`, `campaign_performance`, `first_touch_channels`, `country_breakdown`, `new_vs_returning`, `top_landing_pages`, `device_breakdown`, `os_breakdown`, `geo_breakdown`, `hourly_pattern`, `day_of_week_pattern`, `daily_trend`, `landing_page_channel_mix`, `conversion_rate_by_page`) now reflects the chosen event(s) instead of GA4's blended default.

## Step 4 — Report back
Tell the user what was built, the report/category counts, and open it for them: `open clients/$1/reports/ga4_dashboard_<date>.html`. Flag if any of the 43 reports failed to load (printed as `[FAILED]` during the build, embedded as a visible "couldn't load" card rather than silently dropped).

## Step 5 — Key-points analysis + SWOT (in chat, every time — don't wait to be asked)
Don't just hand over the file. Read the data actually embedded in the dashboard (the `<script id="dashboard-data" type="application/json">` block in the generated HTML — parse it with Python/`json`, don't eyeball raw HTML) and report on it in chat:

1. **Key points** — pull out what's actually notable across categories: standout channels/sources (esp. revenue-per-session efficiency, not just volume), device split, new-vs-returning behavior, top products, funnel drop-off points, and — critically — any `anomaly` field present on a report (these are the tool's own flagged tracking/data-quality issues, e.g. a later funnel stage exceeding an earlier one). Anomalies go first/prominently, not buried. Use concrete numbers, not vague characterizations.
2. **SWOT analysis** — close with a Strengths / Weaknesses / Opportunities / Threats summary built from what the data actually shows for this account (e.g. Strength: a channel with disproportionately high revenue efficiency; Weakness: a flagged tracking anomaly or a low view-to-cart rate; Opportunity: an underused high-converting channel or top product to push; Threat: over-reliance on one channel/geo, or a leaking funnel stage). Keep each point tied to a number from the dashboard — no generic filler.

This applies to every dashboard build, not just when asked — the file alone isn't the deliverable, the analysis is.
