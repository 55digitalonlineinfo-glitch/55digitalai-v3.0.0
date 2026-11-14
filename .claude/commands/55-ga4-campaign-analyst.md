---
description: Eight-section GA4 deep dive for a single Google Ads campaign — engagement quality, landing pages, device/geo/new-vs-returning splits, attribution role, and a value trend, cross-referenced with Ads cost and conversions
---

Run the per-campaign deep dive for client **$1**, campaign **$2** (rest of the arguments, if any, may specify a lookback window like "last 60 days" — otherwise default to 30). Read-only — this never writes to the account.

## Step 0 — Make sure GA4 is wired up
If `scripts/client_registry.py`'s `resolve($1)` shows no `ga4_property_id`, don't ask the user for a property id directly — look it up automatically. But first confirm the lookup is even using the right Google account, since a wrong-account grant and a plain access gap both surface as the same 403/no-match from the API and are easy to confuse (this bit us live with a client whose GA4 access wasn't actually on the account we assumed — 2026-07-27).

1. Run `.venv/bin/python3 scripts/ga4_property_finder.py whoami` to identify the account behind the toolkit's current token (prints an email, or "Unknown" if the token predates the identity scope).
2. Ask the user via AskUserQuestion: *"GA4 lookups for **$1** will use the account **\<email or 'currently configured account (identity unknown)'>**. Is that the right account?"* — options **Yes, proceed** / **No, switch accounts**.
   - **Yes** — continue to step 3.
   - **No** — this requires an interactive browser login only the user can complete, so tell them that, then run `.venv/bin/python3 scripts/get_google_refresh_token.py` (no `--save` yet) in the background. It opens a consent screen; once it completes, show the user the signed-in email it printed and ask them to confirm before making it the toolkit's account (this replaces the credential for *every* client/script, not just this one). If confirmed, run it again with `--save` to write the new refresh token into `google-ads.yaml`. Then re-run `whoami` to verify, and go back to step 2.
3. `.venv/bin/python3 scripts/ga4_property_finder.py find $1`

This calls the GA4 Admin API, walks every property the connected Google account can see, and matches by web-stream domain against the client's `domain` field.
- **Exactly one match** — tell the user what was found (property id + domain), then run `.venv/bin/python3 scripts/ga4_property_finder.py find $1 --save` to write it into `clients.json`. This edits a shared config file, so confirm with the user before running `--save` (a plain "yes, save it" is enough — no need for a full approval workflow).
- **No match** — with the account already confirmed in step 2, this now means a genuine access gap: this Google account doesn't have GA4 access on that property yet, or the property lives under a different domain. Say so plainly and ask the user to grant access or provide the property id, rather than guessing.
- **Multiple matches** — show all candidates and ask the user which one via AskUserQuestion; don't save automatically.

## Step 1 — Find the campaign
If the user gave an exact campaign name, skip straight to Step 2. If they described it loosely ("the best sellers campaign", "our branded search") or you're not sure of the exact spelling, run:

`.venv/bin/python3 scripts/campaign_analyst.py list $1 [--days N]`

This lists every campaign with spend/clicks in the window, sorted by cost, with id/status/CPA — match the user's description to the closest name or id.

If no campaign was specified at all (**$2** is empty), always run the `list` command above first, then ask the user which campaign they want via AskUserQuestion — offer the top campaigns by cost from the list as options (include cost/CPA in each option's description so the choice is informed). Never guess a campaign in this case.

## Step 2 — Run the deep dive
`.venv/bin/python3 scripts/campaign_analyst.py run $1 "<exact campaign name or id>" [--days N]`

Matching works because these accounts use Google Ads autotagging with Ads↔GA4 linked, so GA4's `sessionCampaignName` is the literal Ads campaign name (confirmed live on a real client account, 2026-07-25) — the script matches by exact name, or by numeric id if you pass one.

The output has 8 sections:
1. **Business Overview & Cross-System Check** — Ads cost/clicks/conversions/value next to GA4 sessions/conversions. Flags only genuine anomalies (GA4 showing zero or much *fewer* conversions than Ads) — a GA4 count far *higher* than Ads is normal on these accounts since GA4's `conversions` metric sums every key event (view_item, add_to_cart, purchase...), not just the specific actions Ads is optimizing toward.
2. **Engagement Quality vs. account baseline** — bounce rate, engagement rate, avg session duration, pages/session for this campaign next to the account-wide average, so "cheap clicks, poor engagement" is visible at a glance.
3. **Landing Page Breakdown** — which pages this campaign's traffic lands on and each page's conversion rate.
4. **Device Breakdown**, **5. New vs Returning**, **6. Geo Breakdown (city)** — all scoped to this campaign only.
7. **First-Touch vs. Last-Touch Attribution Role** — compares session-based (last click) vs. first-user (first touch) conversions to show whether this campaign tends to *open* the journey (introduces users who convert later elsewhere) or *close* it (users already knew the brand, this campaign brought them back). Caveat always shown in the output: GA4's Data API doesn't expose full multi-touch path sequences (that needs GA4's UI-only Attribution reports or a BigQuery export) — this is a proxy, not a literal path.
8. **Customer Value Trend** — daily revenue + AOV for ecommerce clients; daily conversions + event value for lead-gen clients (event value is usually 0 unless the account assigns monetary value to leads — the script says so explicitly when that's the case, so read conversions as the trend instead).

## Step 3 — Answer with commentary
Don't just paste the table output. Lead with what the numbers say about whether this campaign's traffic "makes business sense" (the point of this command) — e.g. cheap CPA but weak engagement quality, or a campaign that's a strong opener but gets little direct credit. Call out any FLAG lines from section 1 explicitly. Reference specific numbers from the output.

If Step 0 couldn't find or confirm a `ga4_property_id`, don't try to guess one — the deep dive can't run without it.
