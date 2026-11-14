---
description: Comprehensive 20-section Google Ads full account audit (structure, tracking, bid strategy, competitors, GA4, Merchant Center, keywords, Search/PMax/Display/YouTube deep dives) — checks available APIs/tools first, delivers a text report, offers a PDF afterward
---

Run a comprehensive full-account audit for client **$1**, following the checklist in `system-prompts/agents/ppc-audit-agent.md`. Read-only — this never writes to any account. Default lookback is 90 days unless a specific item in that checklist says otherwise.

## Step 0 — Check what you actually have access to, before starting

Don't start pulling data until this is resolved — several sections of the checklist depend on access this session may or may not have, and guessing Pass/Fail on an unreachable data source is worse than saying so upfront.

1. Look up `$1` in `clients.json` (via `scripts/client_registry.py`'s `resolve()`). Confirm `customer_id` is set — required, this is the one thing the audit can't run without. Note `business_type` (`ecommerce` vs `lead_gen` — decides which **(Ecomm)**/**(Lead Gen)**-tagged items in the checklist apply) and which of `ga4_property_id`, `merchant_center_id`, `negative_list_id`, `pmax_branded_generic_list_id` are actually set (`null` means that section is out of scope for this client, not a Fail).
2. Run `.venv/bin/python3 scripts/check_extended_access.py` and read only $1's row — it tells you whether this Google account can actually reach GA4, Search Console, and Merchant Center for this client's domain right now (a separate permission grant from Ads MCC access — an ID configured in `clients.json` doesn't guarantee this session can read it).
3. The checklist itself already tags a fixed set of items **Manual check** that no API in this toolkit can ever answer (PageSpeed Insights, Microsoft Clarity, Google Ads Transparency Center, Recommendations auto-apply, Google Ads Scripts, Consent Mode, GA4 UI-only settings like Google Signals, Merchant Center diagnostics). These are always `Manual` in the output regardless of access — that's expected, not a gap worth flagging to the user here.
4. Summarize for the user before proceeding: what's live and auto-checkable this run (Ads API always; GA4 only if configured *and* reachable per step 2), what's configured but unreachable or not configured at all (name which checklist sections that pushes to Gaps instead of Pass/Fail — e.g. no `ga4_property_id` takes out §6 GA4 entirely), and the fixed Manual-check list from point 3. Ask: proceed now at this scope, or pause so they can grant missing access first (e.g. share the GA4 property with this Google account)?

## Step 1 — Run the audit

Read `system-prompts/agents/ppc-audit-agent.md` in full and follow it exactly as written: query `$1`'s `customer_id` directly via GAQL (`.venv/bin/python3` with `GoogleAdsClient.load_from_storage('google-ads.yaml')`; use `gaql_helper.safe_search` — it catches the common query mistakes and gives friendlier errors), pull GA4 via `scripts/ga4_reports.py` / `scripts/ga4_dashboard.py`'s existing report definitions for whatever Step 0 found configured and reachable, and treat every **Manual check** item as genuinely unverifiable this pass — route those to Gaps, never guess a Pass/Fail for them. Skip **(Ecomm)** items for lead-gen clients and **(Lead Gen)** items for ecommerce clients, per `business_type`.

Every finding must cite real campaign/ad group/keyword/search-term names and real numbers pulled this run — never a hypothetical or estimated figure.

## Step 2 — Write the report (text only — no PDF at this step)

Produce the full output exactly per `ppc-audit-agent.md`'s "Output Format" section — Executive Summary, Account Health Score, Findings Table, Critical/High/Medium/Low Priority, What's Working Well, Action Checklist, and the complete "All Failed Items" list — with one change: **do not generate a PDF here.**

Save two files:
- `clients/$1/reports/full_account_audit_<date>.md` — the complete narrative report, identical content to what goes in chat in Step 3.
- `clients/$1/reports/full_account_audit_<date>.json` — the same findings restructured into the schema `scripts/generate_audit_pdf.py` expects: `client_name`, `business_type`, `domain`, `date`, `health_score` (e.g. `"7/10"`), `health_summary`, `scope_note`, `critical`/`high`/`medium` (arrays of imperative action strings, same wording as the Action Checklist), `sections` (array of `{id, title, note?, items: [{item, status, evidence}]}}`, `working_well` (array of strings), `gaps` (array of strings — the Manual-check / unreachable items from Step 0). Building this now is what makes Step 4's PDF possible without re-running the whole audit later.

## Step 3 — Deliver in chat

Post the complete report in chat too, in full — same rule as the source checklist: never abridge to "see the file," chat and the saved `.md` carry identical content, including the full "All Failed Items" list.

## Step 4 — Offer a PDF, only after the text report is already delivered

Ask: "Want this rendered as a branded, client-ready PDF too?" If no, stop — the text report and the two saved files are the complete deliverable.

If yes, before generating:

1. **Client display name on the cover page** — confirm the name to print (default: `clients.json`'s `name` field for `$1`, e.g. "Acme" — ask if they'd rather use a fuller display name, e.g. "Acme Retail Co."). If they want something other than the default, update the audit JSON's `client_name` field to match before rendering.
2. **Agency branding** — read `brand_config.json`'s `agency_name`. If it's missing or still the placeholder `"Your Agency Name"`, ask the user for their actual agency name and write it into `brand_config.json` (`agency_name` field) so every future client's PDF is branded correctly without asking again. If it's already set to something real, don't ask — just proceed.

Then: `.venv/bin/python3 scripts/generate_audit_pdf.py $1 clients/$1/reports/full_account_audit_<date>.json`, and tell them where the PDF landed.
