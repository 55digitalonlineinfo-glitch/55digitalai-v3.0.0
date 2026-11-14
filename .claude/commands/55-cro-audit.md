---
description: Website CRO audit - 342 conversion checks across general, home, category, landing, product, cart, checkout and thank-you pages, with a completeness gate so no point is skipped, text report first, then an optional client PDF
---

Run the CRO (conversion rate optimization) audit for client **$1**. Read-only - this never changes the website or any ad account.

Source of truth for the checks: `system-prompts/frameworks/cro-audit-checklist.txt` (342 checks, 8 sections). Backing script: `scripts/cro_audit.py` - it owns the IDs, the per-section counts and the completeness gate. **Never type the checklist from memory and never audit from a shortened list; always read it through the script.**

## Why this is built the way it is (read once)
A 342-item checklist fails by silently skipping items. So: every check has an ID (GEN-01...TYP-23); the script pins the expected count per section and refuses to run if the file drifted; `scaffold` creates a results file with every selected check set to TODO; `validate`, `report` and the PDF all refuse to finish while anything is TODO or has no evidence. A skipped check is an error, not a shorter report. Work through the checks in ID order, section by section, and never batch-mark a group "PASS" without looking.

## Step 1 - Propose the sections (always first, never skip)
Run `.venv/bin/python3 scripts/cro_audit.py list` and show the user the **complete** output in the chat as text - every section, its count, and every single check with its ID and priority. Do not summarize or shorten it. Then ask which sections to audit:

1. General & Navigation (25)  2. Home page (20)  3. Category page (46)  4. Landing page (75)  5. Product page (78)  6. Cart page (30)  7. Checkout page (45)  8. Thank-you page (23)  - or **ALL (342)**.

Recommend a default from the client type (ecommerce: all except Landing page unless they run one; lead-gen: General, Home, Landing page, Thank-you). Wait for the answer before capturing anything. Also ask for the URLs you cannot discover (a sample category, a sample product, the landing page ads point to, thank-you page URL if it can't be reached without a purchase). Domain is in `clients.json`.

## Step 1b - Sales funnel from GA4 (ECOMMERCE CLIENTS ONLY - `business_type` in `clients.json`; the script refuses for lead-gen; before capturing anything)
Ask the user first: **"Do you already have data on where users drop off, or should I pull the ecommerce journey from Google Analytics and benchmark it against industry standards?"** (AskUserQuestion: Use GA4 (recommended) / I have my own data / Skip.) If they give their own data, use it and skip the GA4 pull.

If GA4: run `.venv/bin/python3 scripts/cro_audit.py funnel $1 [--start YYYY-MM-DD --end YYYY-MM-DD]` (default: the same 30 days the audit covers; it saves `clients/$1/reports/cro_audit_YYYY-MM-DD/ga4_funnel.json`, which the client PDF picks up automatically). Optionally also `scripts/ga4_reports.py run $1 purchase_funnel|ecommerce_funnel_by_channel|device_breakdown` for the channel and device cuts.
Then **show the funnel in the chat, start to end, as a table**: every stage in order (visit the site -> view product -> add to cart -> start checkout -> purchase), the number of users at each stage, **how many (and what %) go on to the next stage and how many drop off**, the overall visit-to-purchase %, the device split, and the typical range for each transition with its verdict (IMPROVE / OK / GOOD / GAP; rough benchmark, say it is directional).
- The export is an **open** funnel: a stage can be bigger than the one before it. That is a **tracking gap** (event missing upstream or firing without a real previous step) - flag it explicitly, add a GEN-04 finding, and say it must be fixed in GTM before the rates are trusted.
- Name the **weakest stage** (biggest drop vs the typical range), then propose which audit sections to fix for it (checkout drop -> CHK + CART + GEN-04; add-to-cart drop -> PDP; view-product drop -> CAT/HOME/LP) and ask the user to confirm the sections in Step 1.
- Lead-gen clients have no sales funnel: use `ga4_reports.py run $1 lead_funnel` instead and skip the PDF funnel page.

## Step 2 - Capture the pages (Playwright first, user screenshots only as fallback)
`.venv/bin/python3 scripts/cro_audit.py capture $1 --page home=URL --page category=URL --page pdp=URL ...`
- Saves desktop (1440) and mobile (390) fold + full-page screenshots and `signals.json` (load time, forms and hidden `gclid` fields, sticky/fixed elements, search box, cookie banner, popups, schema types, analytics tags, trust/payment/urgency words, breadcrumbs, filters, sort, wishlist, etc.) to `clients/$1/reports/cro_audit_YYYY-MM-DD/capture/`.
- View screenshots cheaply: `sips -Z 1400 <png> --out <small.png>` then Read it. Use the signals as evidence, but judge visually - a keyword hit is not proof.
- **Cart / checkout:** with Playwright add a product to an anonymous cart and walk to the checkout page, take screenshots of each step. **Never submit an order, never enter payment details.**
- If a page is blocked (bot check, 403, login wall) or a step can't be reached, say so, do NOT try to get around the block (no user-agent spoofing), and ask the user for **screenshots or a screen recording of the whole process, both mobile and PC** (product page, add to cart, cart, every checkout step up to but not including payment, footer, first visit for the cookie banner). The user sends the file path of the recording. Don't guess.
- **Reading a screen recording (no ffmpeg needed, macOS only):** `swift scripts/video_frames.swift <video> <outdir> <every_seconds> <width_px>` extracts frames with AVFoundation (prints duration and size). Build a contact sheet with PIL (`.venv/bin/python`), read it, then re-extract key moments at ~520 px wide to check details. Save the key frames next to the audit in `capture/` as evidence and note the video path in `pages` / `notes`. Judge only what is visible; mark the rest MANUAL with what to record next.
- **Cannot be verified from outside - mark MANUAL and say exactly what is needed, never PASS/FAIL by assumption:** payment-provider redirect on success/failure (GEN-05, GEN-06 - needs a test order or the GA4/GTM purchase event), order confirmation email and invoice (CHK Order confirmation, TYP), thank-you page content when it needs a real order, form delivery into the CRM, retargeting ads running, A/B tests and heatmaps in use, bounce rate (ask for GA4 / `scripts/ga4_reports.py` data instead - it can answer funnel, bounce, device and speed-related questions read-only).

## Step 3 - Judge every selected check
1. `.venv/bin/python3 scripts/cro_audit.py scaffold $1 --sections <codes or ALL>` -> `clients/$1/reports/cro_audit_YYYY-MM-DD.json` (all TODO). Fill `pages` with the URLs used.
2. Go section by section, ID by ID. For each check set `status` (PASS / FAIL / PARTIAL / N/A / MANUAL), `evidence` (what you actually saw, on which page, quoting the visible text or the signal value) and, for FAIL / PARTIAL / MANUAL, `fix` (concrete: what to add, where, example wording). N/A needs a real reason (e.g. "no products to filter - lead-gen site"). Write results to the JSON after each section, not at the end.
3. Run `.venv/bin/python3 scripts/cro_audit.py validate <results.json>` after each section and at the end. It lists every still-TODO id. **Do not move on to the report until it prints COMPLETE.** If you run short of budget, say which sections remain - never fill them with placeholder verdicts.
4. Priority labels (High / Medium / Low) come from the checklist; use them to order fixes, not to skip Low ones.

## Step 4 - Text report (the output the user reads)
**Order of the chat message (house rule): FIRST a short summary of the main things to fix and how, segmented into High / Medium / Low priority (grouped by theme, each with the concrete fix, not one line per check), THEN the full per-item audit result.** Never lead with the full table.
`.venv/bin/python3 scripts/cro_audit.py report <results.json>` prints and saves `.md`: summary table per section (counts must sum to the section size), the **fix list** (FAIL before PARTIAL, High before Medium before Low), then the **full checklist, every point with its ID, status, evidence and fix**. Show it to the user in the chat as text - the full list, not only the problems (user rule: always a full per-item table, never a prose summary of new findings only).
- Link every page you reference with its full URL (house rule).
- No em dashes (use a hyphen). Plain, simple wording.
- Internal reports in the user's language; client-facing text in the client's language.

## Step 5 - Offer the client PDF
Always ask: "Generate a client PDF of this audit?" If yes:
1. Brand from the client's own site (colors, Google Font, header logo copied next to the output), exactly as in `/55-merchant-policy-check` Step 4. Save `brand.json` (shape in `scripts/cro_report_pdf.py` docstring) in `clients/$1/reports/cro_audit_YYYY-MM-DD/cro_pdf/`. The PDF is written to `clients/$1/reports/cro_pdf/`, so copy the logo file there too or the logo shows as broken.
1b. **Find the language the business runs in first, do not ask for it:** `.venv/bin/python3 scripts/cro_audit.py lang $1` (reads the homepage's visible text, then its `<html lang>`, then the country in `clients.json`; never retries with a disguised user agent). Tell the user the detected language and how it was found; only if the source line says "confirm with the user" ask them to confirm. The PDF has full label sets for `uk`, `pl` and `en` (a business in any other language gets `en` until a label set is added in `cro_report_pdf.py`).
2. Rewrite the `evidence` / `fix` texts in the client's language for the business owner (plain words, `<a href>` links to the pages, no agency branding). **Do it as an overlay, not by editing `results.json`** (the English file stays the internal record): write `clients/$1/reports/cro_audit_YYYY-MM-DD_<lang>_texts.json` with `sections`, `groups` (English group name -> local), `prio`, `sources` and `items.<ID>.{title,evidence,fix}` for EVERY audited check (the PDF refuses to build if one is missing), and pass it with `--texts`. Put the client's name, date label, scope and `method` in a `brand_<lang>.json`. Keep section names and priority labels short (long ones overflow the pass table) and use `--lang <lang>`; Ukrainian packs at 0.70 so it fits.
3. `.venv/bin/python3 scripts/cro_report_pdf.py <results.json> --brand <brand.json> [--lang auto|en|uk|pl]` (default `auto` = the detected business language) - refuses to build unless validate is COMPLETE, so the PDF cannot be a silently shortened audit. Fix any "content touching the footer" warning, then look at `qa/pageN.png` (`sips -Z 800`) for the cover, a FAIL page and the pass table. `open` the PDF for the user.
4. Same layout rules as `/55-feed-title-optimizer` and `/55-merchant-policy-check` (shared renderer).
5. **Page 2 of the PDF (right after the cover) is the sales funnel, visualised** (a bar per stage with its user count, a line between stages saying how many % continue and how many drop off, the overall visit-to-purchase %, and for each transition the client's own rate next to the typical industry range ("Yours 26.8%  Typical 40-55%") with a flag - **Improve** (below the range), **On par**, **Above typical** or **Fix tracking** (a stage larger than the previous one) - and a short "What this means" box naming the biggest gap and the first area to fix. Ranges live in `FUNNEL_BENCH` in `scripts/cro_audit.py` (add-to-cart per product view 5-10%, checkout per add-to-cart 50-70%, purchase per checkout 40-55%); they are rough, general ecommerce figures, labelled as a guide on the slide - adjust them there if you have better numbers). It is built automatically from `ga4_funnel.json` (Step 1b) and localised for `--lang en|uk|pl`; if Step 1b was skipped it is simply omitted. After building, look at `qa/page2.png` to confirm it rendered.

## Rules
- Read-only. Fixes are the client's/developer's job; this command only reports.
- Evidence or it didn't happen: no verdict without something you saw or measured.
- Don't recommend ad-copy / quality-score work; this audit is about the site.

## Status
Built 2026-10-28 from a 342-check CRO checklist. Completeness gate, report and PDF tested with synthetic results (all 342 recorded, PDF packs without footer overflow).
