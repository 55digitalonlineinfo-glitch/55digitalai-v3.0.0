---
description: Product feed optimization — title restructuring with conversion-weighted keywords and description rewriting (both check + apply), for client $1
---

This command has two modes. Ask the user which one they want if it isn't obvious from their message — "titles" / "what's missing from my titles" means Title Mode; "descriptions" / "rewrite the description" / "bake in keywords" means Description Mode.

**Standing rule (added 2026-09-16): a title request always comes with a description proposal too, by default.** Whenever the user asks for title work on a product, run Title Mode's process, but also propose that same product's description alongside it in the same response — reuse the category term/evidence already gathered for the title (no need to re-derive from scratch) and apply Description Mode's own rules (conversion-weighted frequency, its own occasion-justification check, its own apply step). Present both as one before/after per product, not two separate asks. Only skip the description half if the user explicitly says title-only.

**Standing rule: always present an explicit before/after, for both title and description, before any apply step — every time, not just when the user asks to see it.** Show the current value and the proposed value side by side (a table or a clearly labeled Before/After pair) with title character counts, even for a single product, even when the proposed description is unchanged (say so explicitly rather than omitting it). Never describe a change in prose only ("I'd add X to the title") and never apply anything without having shown this pair first — approval always happens against the literal before/after text, not a summary of it.

## OBLIGATORY - landing-page fact check before anything is shown, applied, or put in a PDF (added 2026-10-07)

Every new title and description must say only what that product's own landing page says (same facts, or a plain synonym of them), so the feed never promises the shopper something the page doesn't back up. This runs in **both** modes, **after** writing the proposals and **before** showing them to the user, before any `apply`, and before the client PDF. It is not optional and not skipped for "obvious" products. It exists because a real first draft (written from the shop's category page) still contained claims the specific product's page never made.

**How (the method that caught real errors in practice):**
1. Fetch each product's own page (`curl -sL -A "Mozilla/5.0" <url>`), strip it to plain text, and keep the spec/feature section and the description body. A product page that 404s or no longer exists in the client's language = the product can't be verified - tell the user and leave it out unless they confirm the facts themselves (in practice: one product only had a page in another language and one had no page at all - both were dropped).
2. Split every proposed title and description into individual claims (each feature, number, material, compatibility, use case, benefit) and search the page text for each one. Build a claim x product table (claim -> hit count per product), and read the context of every low or zero hit. A hit on a "related products" widget is **not** evidence (e.g. the word "pot" matched only a cookware cross-sell widget on a cooktop page, not the cooktop's own text).
3. Classify each claim: **confirmed** (stated on this product's page) / **synonym** (same fact in the shopper's words, e.g. "flameless" for "no open flame" - allowed) / **inferred** (true in practice but not written on the page, e.g. the page lists LPG/propane variants and the title says "for bottled gas") / **not on the page**. Remove or rewrite every "not on the page" claim. Show every "inferred" one to the user and only keep it if they confirm.
4. Watch for these traps (all found in real runs):
   - **Copy-pasted template text across sibling products** is not evidence for the specific model (e.g. every page in a product line repeated "four burners", including the 2-burner model) - use the spec table for numbers/counts.
   - **Line-level claims** (e.g. "no knobs", "works with any pot", "no greasy residue") may only appear on some product lines' pages - check each product, never copy a claim from a sibling.
   - **Invented use cases / audiences** ("for a small kitchen", "for a bigger family") are never allowed unless the page says it.
   - **Comparisons with competing categories** (e.g. induction) are left out unless the user wants them - they can also pull in the wrong search traffic.
5. In the answer, tell the user in one short table what was removed or changed by the check and why, and list any inferred claims awaiting their OK. Only then present the final proposals.

# Title Mode — check (fetch-candidates) + apply

## Step 0 — Ask which products, before running anything
Same question as Description Mode, and for the same reason — don't default to "all" silently. Ask:
- **All products in the feed** — warn first: can mean a large amount of output/tokens for a big catalog.
- **Best 5 / Best 15 / Best 30** — ask a SECOND question too when this is picked: ranked by what? There's no single correct default, so ask rather than assume:
  - **Revenue** (GA4 `top_products`) — which products make the most money. Never accept an "unmatched" item: resolve it with the ID lookup chain in Description Mode Step 0 (GA4 `itemId` first).
  - **Impressions or clicks** (Google Ads `shopping_performance_view`) — which products already get real traffic, worth polishing further. Maps to the Merchant Center offerId directly, no fuzzy matching.
  - **Conversions or conversion value** (same source) — which products already sell, worth reinforcing rather than fixing.
  - Revenue answers "biggest money-maker," clicks/impressions answers "already gets seen, worth tightening," conversions answers "already converts, worth doubling down on" — genuinely different goals, so let the user pick rather than silently defaulting.
- **Specific product IDs** the user provides directly (bare offerId like `1936` or the full Merchant Center id both work).

This selection scopes which product(s) actually get a restructuring suggestion in Step 5 below — it does NOT shrink the coverage-checking corpus in Step 2, which still needs to scan every title in the feed to correctly tell "genuinely missing" from "covered by some other product you didn't select."

## Step 1 — Run it
`.venv/bin/python3 scripts/feed_title_optimizer.py title fetch-candidates $1 --select all|best5|best15|best30|ids [--ids 1936,2304,...] [--rank-by revenue|impressions|clicks|conversions|conversions_value] [--days 90] [--min-impressions 10] [--top 20]`

**Always use the longest period the account has data for (added 2026-10-12)** - not the 90-day default - for `fetch-candidates` and for every other search-term pull in this command (Step 2.5, Step 2.6, the PDF's numbers). Find it first: `SELECT segments.month, metrics.impressions FROM customer WHERE segments.date BETWEEN '2015-01-01' AND '<today>'` and take the first month with impressions; set `--days` to cover from that month to today. Confirmed live that it changes recommendations: on one account a phrase ranked 3rd by conversions over 90 days ranked 2nd over the full history, with 4x the conversions.

Requires `merchant_center_id` for the client in `clients.json`. This is a general-purpose command — it works for any market/language (Polish, German, Ukrainian, or otherwise) the same way; nothing about the process below is specific to one country.

## Step 2 — What it does, and its real limits
1. Pulls real customer search terms from PMax + Shopping campaigns (`campaign_search_term_view`).
2. Tokenizes every current product title in Merchant Center into a word corpus (Unicode-aware — handles diacritics/accents in any European language, not just Latin/Cyrillic).
3. Flags search terms with real account activity (impressions ≥ threshold) whose meaningful words are mostly *not* found anywhere in that corpus — i.e. "customers are searching this, but no product title mentions it."
4. Validates each candidate against Keyword Planner (`KeywordPlanIdeaService`) for standalone search volume/competition, using the client's own country/language via `GEO_TARGET_CONSTANTS`/`LANGUAGE_CONSTANTS` in `keyword_research.py` (27 European countries configured — add a new one there if a client's country is missing, don't hardcode a new constant in this script).

**Two real limitations, not fixed by more engineering — human judgement is required every run, on every client:**
- **Catalog-wide, not per-SKU.** PMax doesn't expose which specific product a search term actually converted on via the Ads API — there's no way to say "add this word to *this* product's title" automatically. Treat results as "a concept worth adding to *some* product," and use the product's own theme/conversion history to pick the right SKU.
- **Not pre-filtered for relevance, on any client.** The candidate list can include off-catalog product categories the client doesn't actually sell, navigational/address-style queries, and terms that read like a competitor's brand name rather than a generic descriptor — none of those belong in a title regardless of search volume. `KNOWN_BAD_TERMS`/`NAVIGATIONAL_MARKERS` in the script hard-filters previously-caught examples, but **it only knows what's been found so far** — a new client in a new market will surface its own new false positives that this list has never seen. *Example of what this looked like in practice: on a home-fragrance catalog, the raw list included a different category the shop didn't sell, an address-lookup query, and several terms that turned out to be other shops' brand names.* Expect the same shape of noise (wrong category / navigational / competitor name) on any client, in whatever language — read every row before recommending it, and add newly-caught false positives to the script's constants so the next client benefits too.

**One category of finding that's reliably worth checking on every client, regardless of market:** cross-language or cross-script spelling variants of something the client already sells, where titles only use one variant. This shows up differently by market — a client selling in a bilingual or multi-script region may have titles in only one language while a meaningful share of customers search in another (*example: titles written in only one of a market's two common languages, while Keyword Planner showed real, high-volume demand for the other language's spelling of the same product terms*); a Polish or German client might instead have a gap between an English loanword and its local-language equivalent, or between a formal and colloquial spelling. The pattern to check for is the same everywhere: does Keyword Planner show real standalone volume for a spelling/language variant of a word already in the client's own titles? If so, that's a low-risk, high-confidence suggestion.

## Step 2.5 — Top converting GENERIC (non-branded) terms, full account (added 2026-09-16)
`fetch-candidates` also pulls search terms from **every campaign type in the account** (not just PMax/Shopping — `campaign_search_term_view` with no channel-type filter), strips out anything containing one of the client's own brand tokens (read from `clients/<slug>/client-brief.md`'s `## Brand Terms` section, same source `/55-pmax-audit` uses — falls back to just the client's registry name if that section doesn't exist), and ranks what's left by real conversions.

This is a stronger signal than Step 2's coverage-gap table: it's not "customers searched this and no title mentions it," it's "this exact generic term is actually converting, account-wide." If a term from this list plausibly describes a product in your Step 0 selection, that's the term to **lead** that product's title with — brand goes right after it, and anything that still distinguishes this SKU from a sibling (pack size, named flavor/style, volume) stays after the brand. Don't drop those distinguishing attributes just to make room:

`{top converting generic term} {brand} {remaining distinguishing attributes}`

If a second real, relevant term turns up too (from this table, Step 2, or Step 2.6's combined evidence), it doesn't have to sit unused — see Step 2.6's ordering rule for how to place more than one validated keyword in the same title.

*Illustrative example (home-fragrance catalog): "scented candle gift set" and "soy candle gift box" topped the account-wide generic list - both plausible leads for a candle gift-set product's title, but NOT for a reed-diffuser gift set in the same catalog (they are candle-specific terms) - this is exactly the catalog-wide-to-per-SKU judgement call from Step 2, applied to a different data source.*

## Step 2.6 — Extra evidence for a product with no qualifying converting term (added 2026-09-16, revised 2026-09-16)
Applies **only** to a product in your Step 0 selection that has no real converting term from Step 2.5 and no strong candidate from Step 2 either (e.g. a reed diffuser on a candle-dominated account, where every top-converting generic term is candle-specific and would misdescribe it). Don't run this for a product that already has a qualifying converting term — use that one as-is.

**These are sources to combine, not a fallback ladder where you stop at the first hit.** Pull from all of them for the product, build one pool of validated candidate keywords, then rank and place — see the ordering rule below. Don't treat finding one usable term as a reason to skip the others; a second or third genuinely relevant term is welcome, not redundant. **The account's own historical search-term check (the last bullet below) is OBLIGATORY, not optional** — always run it for every product in this fallback path before finalizing a title/description, even when a Keyword Planner candidate already looks good enough. Confirmed in practice that it changes real recommendations: a catalog-wide guess got replaced by a better-fitting, higher-activity real phrase from the account's own history only after actually running this check — don't skip it and assume the Keyword Planner/description-derived candidate is already the best one.

- **The product's own current title and description** — the cheapest source, always worth reading first for its category concept (e.g. "diffuser" for a reed diffuser).
- **Its landing page** (WebFetch) — richer context when title/description alone is too thin to name a clear category. Same bot-block caveat as Description Mode Step 1 — some sites return a JS challenge page instead of real content; fall back to Merchant Center data if so, don't fabricate.
- **Keyword Planner volume on a candidate:** `.venv/bin/python3 scripts/keyword_research.py $1 "candidate term"` — validates a specific guess.
- **Keyword Planner's own suggestions**, seeded by a candidate and/or the landing page URL: `.venv/bin/python3 scripts/keyword_research.py $1 "candidate term" --seed-url <landing page url>` (`generate_keyword_ideas()` — genuine suggestions from Google's engine, not just a volume check on one guess). **Known limitation, confirmed live on a real client account:** a URL-only seed can return ZERO suggestions (plausibly the same bot-check blocking WebFetch/curl also blocks Google's crawler, not fully confirmed) — drop `--seed-url` and retry keyword-only if so.
- **OBLIGATORY — the account's own raw historical search-term data.** Re-run `fetch-candidates` with a higher `--top` (or no cap) and the longest `--days` window, not just the default top-N cut (the full list comes from `fetch_pmax_shopping_search_terms` / `fetch_account_search_terms_ranked`). Grep it for anything containing the product's category concept, even at modest impressions/clicks and low or no conversions — real account behavior at lower volume is still worth having alongside a Keyword Planner number, and can outrank a catalog-wide guess once you actually see it.

**Every candidate from every source gets the same relevance screening — volume or presence in a list is never enough on its own.** Confirmed in practice: seeding a descriptive phrase ("white candle") into Keyword Planner surfaced a competitor brand name that literally contains the same words, ranked ABOVE the seed term itself — a real trap, not a hypothetical one. If a candidate turns out to be a competitor brand, an unrelated concept, or otherwise off, don't use it — try a **broader** version of the concept instead (e.g. "white candle" → "candle", which had far more volume and no noise) and re-run the relevant checks above on that broader term.

**Ordering rule — the same for title and description:** rank every validated, relevant candidate you've gathered by how important/strong it is (real volume, real conversions, and specificity to this exact product all count) and place them in that order — **the phrase you judge most important goes first**, a second (or third) genuinely relevant phrase can go in the **middle or at the end**, brand and remaining distinguishing attributes fill in around them. This is not a single-keyword-then-brand template anymore — a title or description can legitimately carry two or more validated keywords when you have more than one, as long as each one actually describes the product (same correctness rule as always: never force a phrase that doesn't fit just because it scored well somewhere).

## Step 3 — Apply, only after explicit approval
Title overrides have an apply step — `.venv/bin/python3 scripts/feed_title_optimizer.py title apply $1 --plan plan.json [--confirm]`, plan shape `[{"product_id": "...", "title": "new title"}, ...]` (dry run without `--confirm`, prints old vs. new per product). It writes through the same Merchant API path as Description Mode's apply (see Description Mode Step 4 for the durability rules). Titles and descriptions are applied with two separate plan files and two separate runs. **Show the full proposed title per product and get explicit approval before running `--confirm`** — same convention as every apply step in this toolkit.

## Step 4 — Answer with commentary
Separate genuinely actionable rows (real descriptive gap, plausible product match) from risky ones (possible competitor/brand name, off-catalog category, navigational query) explicitly in your answer — don't just paste the table. Name the specific product you'd attach a good suggestion to, if you can infer it from the term's meaning. `KNOWN_BAD_TERMS`/`NAVIGATIONAL_MARKERS` in the script filters previously-caught false positives, but it is **not comprehensive** — a new client's account will surface noise this list hasn't seen yet; if you catch a new one, add it to the script's constants so every future client benefits.

## Step 5 — Restructure titles, don't just append keywords
Once you have a short list of validated, safe candidates (Step 2-4), don't just tack them onto the end of the existing title — actually reorder the title using these rules, and only for the product(s) selected in Step 0 (the printed product table shows you their current titles). This step is judgement-driven; don't try to fully automate it in the script.

**Mechanics that apply to every client, in every market:**
- Google indexes up to 150 characters; the visible SERP snippet (especially mobile) can cut off around 30 characters. Put the highest-value term in the first ~30 characters, and keep the full title under 150.
- Word order matters more than word presence — a term buried at character 120 helps far less than the same term at character 10.
- Check the client's own brand-name search volume via Keyword Planner (query the brand/company name the same way as any other term) and compare it to the volume of the found keyword gaps. If brand volume is small relative to the gaps, **push the brand to the back of the title** and lead with the highest-value term instead — don't default to brand-first just because that's the "standard" pattern. (*Example: a small regional brand name got ~50/mo searches vs. ~18,000/mo for the best descriptive gap - an extreme case, but the same comparison is worth running for any client, since a well-known international brand and a small local one will land on opposite sides of this rule.*)

**Category structure as a starting template — identify the client's actual vertical first, then adapt, don't force-fit:**
| Category | Structure |
|---|---|
| Clothing/Apparel | Brand + Gender + Product Type + Color + Size + Material |
| Consumables (food, drink, cosmetics, etc.) | Brand + Product Type + Attribute (weight/count) — or, if brand search volume is low, Product Type + Attribute + Brand |
| Hard Goods | Brand + Product + Attributes (size, weight, quantity) |
| Electronics | Brand + Attributes + Product Type + Model # |
| Books | Title + Type + Format + Author |
| Seasonal | Occasion + Product Type + Attributes |

**Two correctness rules that matter more than the structure itself, on any client — get these wrong and the suggestion becomes actively misleading, not just suboptimal:**
1. **Audience/occasion framing** (e.g. "gift for a man/her/a birthday") is never a default suffix — adding it to a product needs a stated reason, the same evidence discipline as any other keyword here. A reason is either: (a) real search-term evidence for that specific occasion phrase in this product's category (e.g. "candle as a gift" found for candle products, "gift set for her" found for boxed gift sets) — not just the generic top-level occasion volume, which exists for almost any catalog and proves nothing product-specific; or (b) the product is genuinely gift-positioned as a fact — sold in a gift box, bundled with glassware, a themed multi-item set — not merely "it's alcohol, alcohol can be a gift." **A plain single product with no such evidence and no gift packaging gets no occasion phrase at all.** (*Real correction: occasion framing had been added to every product in a batch as a template ending - on review, plain single items had no such evidence and should not have carried it; boxed gift sets and products backed by real occasion searches did.*)
2. **Style/attribute-specific terms** must ONLY be added to a product whose title *already* states that exact attribute in some form — never introduce a new style/attribute claim a product doesn't actually have, just because it shares a broad category with products that do. (*Example: on a candle catalog, a candidate term for the specific scent "vanilla" was only valid to add to products already labeled vanilla - adding it to a plain unscented candle in the same broad category would have mislabeled the product.*) When in doubt, re-read the product's own title before assigning any attribute-specific term — this check matters regardless of the client's language or market.

Present the result as an explicit before/after pair per product, with character counts — lead with the highest-confidence patterns for that specific client (which will differ client to client: a cross-language spelling gap, an audience-framing gap, a word-order fix, etc.), not a fixed template of what one past client happened to need.

# Description Mode — check + apply

Description overrides persist once the account's data-source rule is set up correctly (see Step 4 below): a write through the Merchant API typically shows up in Merchant Center within ~30-90 seconds and is not overwritten by the next scheduled feed fetch. This mode has a real apply step, gated the same way as every other apply step in this toolkit: full proposed list shown, explicit approval, only then `--confirm`.

## Step 0 — Ask which products, before doing anything else
Don't default to "all" silently. Ask:
- **All products in the feed** — warn first: this can mean a large amount of output/tokens for a big catalog, so confirm that's really wanted before running it.
- **Best 5 / Best 15 / Best 30** — same second question as Title Mode Step 0: ranked by what? Revenue (GA4, subject to the matching caveat below), impressions/clicks (Ads `shopping_performance_view`, reliable direct offerId match, "already gets traffic worth polishing"), or conversions/conversion value (same source, "already sells, worth reinforcing"). Ask rather than default.
- **Specific product IDs** the user provides directly (bare offerId like `1936` or the full Merchant Center id both work).

Run: `.venv/bin/python3 scripts/feed_title_optimizer.py describe fetch-candidates $1 --select all|best5|best15|best30|ids [--ids 1936,2304,...] [--rank-by revenue|impressions|clicks|conversions|conversions_value] [--days 90]`

This prints the selected product set (id, title, price, current description) AND a table of real PMax search terms ranked by conversions (fetched the same way `/55-pmax-audit` does — enumerate live PMax campaigns, then `campaign_search_term_view` per campaign id — not a blanket channel-type filter).

**ID lookup chain, required whenever ranking by revenue (revised 2026-10-12):** never stop at "this GA4 name has no matching feed title". Matching `itemName` to titles by token overlap fails on renamed/repackaged/delisted SKUs (confirmed live: GA4's #1 revenue product had no title match, but had an ID in GA4 all along). Resolve every item through this chain, in order, and only call it unmatched after all of them fail:
1. **GA4 `itemId` dimension** - query GA4 Data API `runReport` with dimensions `itemId` + `itemName` (filter `itemName` CONTAINS a distinctive word, case-insensitive, date range from the property's start). On most shop plugins (e.g. WooCommerce) `itemId` IS the Merchant Center offerId. GA4 may also show several names over time for one `itemId` (and one name across several IDs) - group by ID, not name.
2. **The resolved ID in the live feed** (`products.list`, match `offerId`).
3. **Google Ads `shopping_performance_view`** filtered by `segments.product_item_id = '<id>'` (all available dates) - shows every title the product served under and its real Ads conversions, even after delisting.
4. **The shop itself** - site search (`/?s=<word>&post_type=product`) and `/?post_type=product&p=<id>` - to see whether the product page still exists.
If the ID resolves but the product is gone from both feed and site, report it as **delisted**, with its last sale date (GA4 `date` dimension) and its revenue - that is a business finding for the client (a top seller disappeared), not a matching failure. Then continue with the next item in the ranking.

## Step 1 — Fetch each selected product's landing page
Use WebFetch to pull the real page content (specs, ingredients/composition, what's included) for each selected product — this is the factual source for the new description, not just the existing Merchant Center text. **Known failure mode:** some sites sit behind a JS bot-check that returns a "Protected section" challenge page to both WebFetch and curl (confirmed on a real shop) — there's no headless browser available in this environment to get past that. If a fetch fails this way, say so explicitly and fall back to the product's existing Merchant Center `description` field plus its title/price as the factual source instead of fabricating specs. Never invent an attribute (ABV, ingredients, volume) that isn't confirmed by either the page or the existing feed data.

## Step 2 — Decide the keywords: ask the user, or offer the converting-search-term data
Two paths, ask the user which:
1. **They name their own primary keywords** — just use those.
2. **Use historical conversion data** — offer the ranked search-term table from Step 0's output (or re-pull it fresh) and let the user pick/approve which terms to use, rather than silently auto-selecting. This table is catalog-wide (PMax doesn't expose which SKU a term converted on), so match each keyword to the product(s) it actually describes by judgement — the same per-SKU-assignment caveat as Title Mode Step 2.

**No qualifying converting term for a given product?** Same Title Mode Step 2.6 approach — combine evidence from the product's own title/description, its landing page, Keyword Planner volume/suggestions, and the account's own raw historical search terms into one pool, screen every candidate for relevance (never on volume alone), then order by importance: the strongest phrase leads the description, a second genuinely relevant one can sit in the middle or at the end alongside it — this isn't limited to one keyword when more than one earns its place.

## Step 3 — Write the description: conversion-weighted frequency and placement
This is the core rule for this mode, apply it to every product:
- **Rank the keywords assigned to a given product by their real conversion count** (from the Step 0/2 data).
- **The highest-converting keyword goes first in the description**, and can be repeated (mentioned twice) if it fits naturally.
- **Each lower-converting keyword appears later in the text, and only once.**
- Never force a keyword that doesn't actually describe the product just because it converts well elsewhere in the account — same Title Mode Step 5 correctness rules apply here too: a style/attribute-specific keyword (a scent, a specific ingredient) only belongs on a product that actually has that attribute, and audience/occasion framing (gift for a man, etc.) is never a default addition — it needs a stated reason (real search-term evidence for that occasion in this product's category, or the product genuinely being gift-positioned as a fact) before it goes in a description, exactly as for a title. A plain single-bottle product with no such evidence gets no occasion phrase.
- Keep the description in the product's own `contentLanguage` — don't mix in a keyword's source language if it doesn't match (e.g. a search term in another language on a product whose content language differs should be translated to the product's language, not pasted in as-is).

Show the full before/after list, per product, for explicit approval **before** writing anything — same convention as every other apply step in this workspace. Approval of the general approach is not approval of the specific text.

## Step 4 — Apply, only after approval
`feed_title_optimizer.py describe apply` and `title apply` write via the **Merchant API** (`accounts.productInputs.patch`), with a dynamic `updateMask` covering whichever of `title`/`description` are present in each change entry. Plan file shape: `[{"product_id": "<Merchant Center product id>", "description": "new text"}, ...]` (`title` plans use `"title"`; run the two applies separately for a product that gets both). Dry run first, same convention as every apply step in this toolkit: `.venv/bin/python3 scripts/feed_title_optimizer.py describe apply $1 --plan plan.json` then add `--confirm`.

**Durability is not automatic — this is not the old Content API's behavior.** The Merchant API models an account's data as multiple named data sources merged by an explicit rule; there is no built-in "manual edit always wins" guarantee. A write only shows up in what Ads actually serves if the account's primary data source's rule is already configured to pull that field from an API-type data source. `apply` resolves the correct write target *from that rule itself* (not by guessing), and if the rule is still self-only (the common default, meaning no override path has ever been configured), it stops with a clear error naming exactly what to fix in Merchant Center (Settings > Data sources > the primary source > rules — add an API-type data source above self) rather than silently writing somewhere that can never surface. **If you hit that error, it's a one-time account setup gap, not something to work around per-run** — tell the user and point them at that fix; don't retry.

Once a write is accepted, `apply` polls for up to 2 minutes and only reports a field as done after re-reading it live and confirming it matches — a `200` response alone is not proof the value actually changed (confirmed to diverge in practice). Anything still unconfirmed after polling is reported explicitly, with a recommendation to check again shortly or edit directly in the Merchant Center UI, rather than assumed to have failed or succeeded.

**A separate anomaly, not a durability problem:** some individual products can get stuck on `title` specifically - `productInputs.patch` returns a clean 200 and the title never changes, while a `description` write on the same product succeeds (confirmed live on several products, identical on the old and the current API, so it is a product/field-specific hold inside Merchant Center). After 2-3 identical attempts, stop retrying: hand the user the exact title text to paste into the Merchant Center UI.

## Client PDF report - built in the client's own brand style (added 2026-10-07, ported 2026-10-12)

Once the obligatory landing-page fact check (top of this file) has passed and the user has approved the final title/description list (applied via `apply` or not - e.g. when there's no API access, the deliverable is a supplemental-feed CSV + this PDF), build the client-facing before/after PDF with `scripts/feed_report_pdf.py`. Never hand-roll a new HTML/PDF generator, and don't fall back to `scripts/text_report_pdf.py` for this report: `feed_report_pdf.py` already has the layout, the 3 languages (pl/uk/en, any label overridable via the spec's `labels` key) and the PDF-safe styling below baked in. It renders through headless Chromium (`playwright` in `.venv`, listed in `requirements.txt`).

**1. Take the brand style from the client's own website (not a generic palette).**
- **Colors:** fetch a product page with curl, find the theme stylesheet (WordPress themes often expose tokens such as `--color-content-primary`, `--color-footer-bg` in a theme CSS file), and take the brand primary, a dark background (their footer/dark-section bg), and the secondary/gray. Prefer the real tokens over colors guessed from screenshots.
- **Font:** the `fonts.googleapis.com` family the site loads. If the site only uses Adobe/self-hosted fonts, pick the closest Google Font.
- **Logo:** the header `<img>`; for the dark report background use the white/inverted version if the site has one.
- **Product images:** each product page's `og:image`, resized with `sips -Z 600` into the spec folder. The script puts them on a light tile so dark products don't disappear.

**2. Write the spec JSON** in `clients/<slug>/reports/feed_pdf/report_spec.json` (images and logo in an `img/` folder next to it - relative paths in the spec resolve against the spec's folder). Spec keys (see the script's docstring, and the fully fictional working example built by `feed-optimization/example/make_example.py`): `client`, `lang`, `currency`, `date_label`, `product_noun`, `period`, `brand` {primary, primary_light, bg, bg2, secondary, font, logo}, `kpis` {terms, conv_value, kp_terms}, `title_formula` {chips, example}, `rules`, `keyword_planner`, `kp_insights`, optional `kp_note`, `themes` ([theme, cost, conversions, conv value, decision, up|mid|down]), `ads_insights`, `top_terms` ([term, conversions, conv value]), optional `brand_share`/`changes`, `highlight` (phrases to mark), optional `labels`, `products` (id, name, sales, old_title, old_desc, new_title, new_desc, image). All numbers come from the same Keyword Planner run and search-term analysis used to pick the keywords - never retyped or estimated.

**3. Run it:** `.venv/bin/python scripts/feed_report_pdf.py clients/<slug>/reports/feed_pdf/report_spec.json --out "clients/<slug>/reports/feed_refresh_YYYY-MM-DD.pdf"`. It prints a warning for any page whose content runs into the footer or any broken image, then renders the **real PDF pages** (not the HTML) to `<out dir>/qa/pageN.png` via macOS PDFKit. Look at the cover, a table page and a before/after page (`sips -Z 800`) before calling it done, and extract the PDF text to check completeness before sending it anywhere.

**Content rules for the report (from real client-report corrections):**
- Client language, client's brand only: **no agency branding** anywhere in the PDF (the footer carries only the date).
- Show what was improved, not what loses money: **don't include a "this theme loses money, we removed it" section** and don't add caveat notes such as "Google doesn't show which model sold" - keep those for the chat answer to the user, not the client PDF.
- No closing "next steps" page unless asked.
- Only products the user confirmed: drop any product whose page is missing or that the user excluded.
- No em dashes (the script refuses to build if one slips in).

**PDF-safe styling - already in the script, never reintroduce (each one broke a real PDF while the HTML preview looked fine):**
- `filter: blur()` background blobs -> banded/clipped rectangles. Use radial-gradient layers on the page background.
- outer `box-shadow` on cards -> printed as opaque black blocks behind every card. Only a 1px inset highlight.
- gradient fill inside cards -> visible horizontal seam. One solid `rgba()` fill.
- `backdrop-filter` -> not supported in print.
Removing the blurs also cut the file size by roughly 3-4x.

Open the final PDF for the user with `open "<path>.pdf"`. The script also writes the HTML it rendered next to the PDF; if the user wants a shareable link instead of (or as well as) the file, publish that HTML as an Artifact.
