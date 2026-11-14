---
description: Merchant Center misrepresentation pre-flight - checks Merchant Center settings and the client's website against each other and against Google's Shopping policies, with a fix list and review-request guidance
---

Run the Merchant Center policy & website alignment check for client **$1**. Read-only - this never writes to Merchant Center, Google Ads or the website.

Checklist this is built on (what each item means, why it matters, which are automatic vs manual): `system-prompts/frameworks/55-merchant-policy-checklist.md`. Read it before Step 3.

## Step 1 - Run the script
`.venv/bin/python3 -W ignore scripts/merchant_policy_check.py $1 [--sample 10]`

- Needs `domain` in `clients.json`. With `merchant_center_id` it runs all 7 sections; without it only the website-side checks run (useful before a new client's Merchant Center is set up).
- Takes ~2-4 minutes (fetches ~20 pages, rate-friendly). Writes `clients/<slug>/reports/policy_check_YYYY-MM-DD.log`, a `.json` copy of the results (input for the client PDF), and every key page's extracted text to `clients/<slug>/reports/policy_check_YYYY-MM-DD/<page>.txt`. The summary and the JSON are always ordered FAIL, then WARN, then PASS.
- The Content API sometimes returns a transient 409/410 "was sunset" error - the script retries; if a settings call still fails it says "Could not read ..." instead of reporting a false "not configured". Re-run in that case.
- If the homepage fetch reports a bot-check page, the website checks are incomplete - say so and verify those items in a browser.

## Step 2 - Read the saved page texts ([read] items)
Open `contact.txt`, `terms.txt`, `returns.txt`, `shipping.txt` (and `privacy.txt`/`about.txt`/`faq.txt`/`track.txt` if present) and check what a regex can't:
- Who the page says the seller is (legal entity, registration number, address) - same business as Merchant Center? Any text that obviously belongs to another shop (a copied template), or product categories in the terms the store doesn't sell?
- Shipping/returns wording vs Merchant Center settings (numbers, who pays, how to start a return), FAQ numbers vs policy numbers.
- Unrealistic or medical claims, "fast delivery" promises contradicted in small print.
- About page: does it read like the owner wrote it (when, where, why), or like generic AI copy?
- Confirm or drop every content-keyword WARN (tracking, business days, no-ship zones, refund timing/method, problem scenarios, cancellation, privacy/terms coverage, liability wording, header menu, payment methods) - these are stem matches; a page can say it in words the list doesn't know, and a stem can hit the wrong sentence. Quote what the page actually says.

Quote the exact sentence for every problem you find - don't paraphrase it.

## Step 3 - Report
**Order is fixed: every FAIL first, then every WARN, then every PASS** - in the chat report and in the PDF alike (house rule). One table with every check (not only the problems), sorted that way, each row with its section, status, check and evidence. Before the table, correct the script where the Step 2 read shows it was wrong (e.g. a "second address" that is the client's own clearly labelled shop is fine; a tax number picked up as a phone is not a finding) and say what you changed. Then:
1. **Most likely suspension causes** - the FAILs that match an *egregious* category in Google's policy (false identity/contact info, hidden fees/charges, dishonest pricing) first, then the rest.
2. **Fix list** - concrete, per page or per Merchant Center setting, with the exact text/value to change and where (e.g. "Merchant Center -> Shipping and returns -> '<shipping service name>': flat fee -> carrier rate, because checkout charges no shipping and the site says the buyer pays the carrier's tariff").
3. **Manual checks left** - the [manual] items from the checklist that the script can't verify for this client (Google Business Profile / Google Ads / social profiles consistency, real address not a PO box, phone answered, dropshipping disclosure, own product images vs supplier images, homepage range and niche focus, collections, broken links, tax and promotions in the MC UI).
4. **Review request** - only once every FAIL is fixed: the steps and the support message template from checklist section 6, filled in with this client's actual fixes.

Write client-facing text in the client's language when asked; internal reports in the user's language.

## Step 4 - Offer the client PDF
After the report, always ask: "Generate a client PDF of this audit?" If yes, build it with `scripts/policy_report_pdf.py` - never hand-roll a new generator. It reuses the `/55-feed-title-optimizer` report's look and PDF-safe rules (imports its CSS and real-PDF QA from `scripts/feed_report_pdf.py`) and **sorts findings FAIL -> WARN -> PASS itself**.

1. **Brand style from the client's own website**, exactly as `/55-feed-title-optimizer` does it: brand colors from the theme CSS/logo, the Google Font the site loads (display faces go in `heading_font`, keep a readable body `font`), the header logo (the version that reads on a dark background) copied into `clients/<slug>/reports/policy_pdf/`.
2. **Write `clients/<slug>/reports/policy_pdf/report_spec.json`** in the client's language (keys are documented in the script's docstring): `scope`, `account_status`, 3 `method` steps, `sources`, and `findings` [{status, area, title, found, fix}]. Write for the business owner, not for us: plain words, quote the site's own sentence in `<q>...</q>`, one concrete fix per finding with where to change it. **Always link the page each finding is about** - in both "found" and "fix" (and in PASS rows), as `<a href="https://...">domain/path/</a>`, so the client can click straight to the page to edit (house rule). When a fix comes from a change we already made in Merchant Center (e.g. a carrier price list copied into MC shipping rates), say so plainly ("in Merchant Center we duplicated ...", in the client's language) and give the exact text to add to the site. Merge duplicates (e.g. "no privacy page" and "no privacy link at checkout" = one finding), drop script false positives, and only list a PASS that was really verified (a keyword hit is not proof - e.g. a blog post titled "reviews" is not customer reviews).
3. **Run:** `.venv/bin/python3 scripts/policy_report_pdf.py <spec.json> --out "clients/<slug>/reports/policy_pdf/<Client> - Merchant Center audit.pdf"` (file name in the client's language). Fix any "content touching the footer" warning, then look at the real PDF pages in `policy_pdf/qa/` (`sips -Z 800`): cover, a FAIL page, the PASS page. Open it for the user with `open`.
4. Same content rules as the feed PDF: client's brand only, **no agency branding**, no em dashes (the script refuses), no "next steps" page beyond the review-request instruction on the account card.

## Rules
- **Always link every page you reference** - in the chat report, the fix list, the review-request message and the PDF alike. That means each website page a finding is about (contact, shipping, returns, terms, checkout, product pages...), each external page a fix relies on (e.g. a carrier's price list such as https://novaposhta.ua/shipping-cost/), and each Google policy page cited. Full clickable URLs, never just a page name like "the shipping page" (house rule).
- Never change anything on the site or in Merchant Center from this command. Fixes to policy pages are the client's/site developer's job; Merchant Center setting changes follow the usual rule - show the exact change and get explicit approval first.
- A WARN is not a verdict - say why it matters or why it's fine (e.g. a second phone that is clearly the shop's number).
- Never tell the client the account "will be reinstated" - Google decides; say what's now consistent and what's left.
## Status
Checks are keyword heuristics in several languages (English, Ukrainian, Russian, Polish, German); a WARN means "read the page", never a verdict. For a market in another language, extend the keyword groups at the top of `scripts/merchant_policy_check.py`. See the checklist's "Deliberately not in this checklist" section for what this command will never suggest (account-evasion tricks).
