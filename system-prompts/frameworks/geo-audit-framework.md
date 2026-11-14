# GEO (Generative Engine Optimization) Audit Framework

Ranked by evidence strength/impact, based on controlled testing and current research (not opinion — see sourcing notes per section). Use this to audit any website for visibility in AI answer engines (ChatGPT, Gemini, Perplexity, Google AI Overviews).

GEO layers on top of SEO, not instead of it — item 13 (SEO fundamentals) is a prerequisite, not optional.

## Audit Checklist (in priority order)

### 1. Crawlability / access — BLOCKING, check first
Nothing else on this list matters if the site is invisible to AI crawlers.
- [ ] `robots.txt` does not block AI crawler user-agents (`GPTBot`, `ChatGPT-User`, `PerplexityBot`, `Google-Extended`, `Applebot-Extended`, `ClaudeBot`, `anthropic-ai`)
- [ ] Server/CDN (esp. Cloudflare) is not silently rejecting AI bot requests at the edge — Cloudflare's default settings began auto-blocking AI bots; check the dashboard's "AI Bots" / "Bot Fight Mode" settings explicitly, don't assume robots.txt is the whole story
- [ ] Spot-check with a fetch tool or the crawler's own IP ranges to confirm a 200, not a 403/429

### 2. Server-side rendering
- [ ] Core content (not just nav/footer) is present in the raw HTML response, not injected client-side via JS after load
- [ ] View-source (not DevTools-rendered DOM) on 2-3 key pages and confirm the actual answer-bearing text is there
- [ ] If the site is a JS framework (React/Vue/etc.), confirm SSR or static export is actually enabled for these pages, not just configured

### 3. Direct source citations
- [ ] Claims/stats on the page cite an identifiable source (a named study, report, or original data) rather than floating unsourced
- [ ] Sourced content measurably increased visibility (~24.9%) in controlled testing — treat unsourced claims as a real gap, not cosmetic

### 4. Expert quotes
- [ ] At least one direct, attributed quote from a named expert/practitioner appears in high-value pages (strongest single factor tested: ~27.8% lift)
- [ ] Quote is attributed to a real, checkable person/title — not a generic "our team says"

### 5. Statistics with clear sourcing
- [ ] Concrete numbers (not vague "many clients see growth") backed by a named source (~25.9% lift)
- [ ] Numbers are current — see freshness (item 10) before trusting an old stat still helps

### 6. Fluent, readable language
- [ ] Content reads as natural, well-edited prose — not keyword-stuffed or robotically "optimized"
- [ ] Run a plain read-through: would a human editor publish this as-is?

### 7. Answer-first structure
- [ ] Each major section opens with a direct 2-3 sentence answer before elaborating
- [ ] A concise 40-60 word answer block sits near the top of the page (the part most likely to get lifted verbatim into an AI answer)

### 8. Content matched to real questions
- [ ] Headings/sections are phrased the way people actually ask (natural-language questions), not keyword fragments
- [ ] AI engines answer prompts, not match keywords — audit against actual question phrasing, e.g. via "People also ask," AnswerThePublic, or real client questions, not a keyword list

### 9. Structured data / schema
- [ ] `FAQPage` schema present on pages with Q&A content
- [ ] `Article` schema present on blog/editorial content
- [ ] Validate with Google's Rich Results Test — present-but-broken schema doesn't count
- [ ] **Check static-exported and CMS-dynamic pages SEPARATELY** — a site can have completely different schema coverage between the two rendering paths (found live: a WordPress plugin added Organization/WebSite/BreadcrumbList/Person schema to dynamically-rendered pages while every static-exported marketing page, including the homepage, had zero schema at all). Don't assume coverage is uniform just because one page has it.
- [ ] **Where schema exists, cross-check the actual field VALUES against the site's own independently-verified facts** — not just whether it validates. Schema can be syntactically perfect and still wrong: a live audit found a Corporation block with a postal code that didn't match the site's own Privacy Policy text, a `url` pointing at `/contact/` instead of the homepage, a `sameAs` linking to an unrelated personal YouTube channel instead of the brand's real one, and a `Person` block with a blank `name` field. None of these would fail a validator, but all of them are real, citable-fact errors.
- [ ] **Identify WHERE each piece of schema is generated before planning remediation** — a static HTML file (fixable directly) vs. a CMS plugin/theme setting (needs admin access to that system, not a file edit). A broken field in WordPress-plugin-generated schema can't be patched over FTP; don't burn time trying.
- [ ] **Scope the schema audit to pages that are actually crawlable** — cross-reference against item 1's `robots.txt` check first. A page blocked from crawling is out of scope for schema fixes until it's unblocked (or is itself a candidate for being retired rather than fixed).

**General principle for generating ANY missing schema type (not just FAQPage): build it from the page's own visible content, never hand-type it separately.** This applies identically to Organization (real address/socials from the site's own footer/contact/privacy text), Person (real name/title as displayed on an About page — not a fuller name pulled from a CMS username or email slug that isn't actually shown to visitors), Review (real testimonial text and author names as displayed), BreadcrumbList (the page's real on-site navigational position), and Service (the page's own title/description) — in every case, hand-typing schema separately from visible copy lets the two drift out of sync the moment someone edits the page, and Google's guidelines require schema to match what's actually rendered. The FAQPage-specific steps below are one instance of this general pattern.

**Recommended schema types, ranked by importance (1-3 apply to every site regardless of type; 4-7 apply to almost every business site; 8-12 apply the moment that content type exists):**
1. `Organization` (or a subtype like `LocalBusiness`/`Corporation`) — name, logo, url, contact info, `sameAs` links to social/LinkedIn. Foundational entity identity every AI engine's "who is this" understanding starts from.
2. `WebSite` (with `SearchAction`) — declares the site as an entity, enables the sitelinks search box. Near-zero effort.
3. `BreadcrumbList` — page hierarchy/context on every non-homepage page, cheap to generate from the site's own nav structure.
4. `FAQPage` — see above; one of the highest direct-citation-lift items available.
5. `Article` / `BlogPosting` — carries `headline`, `author`, `datePublished`/`dateModified`, directly feeding the freshness signal (item 10) and authorship trust.
6. `Person` — for named authors, founders, or quoted experts, with `jobTitle` + `sameAs`. Turns item #4 ("expert quotes") into machine-verifiable identity, not just prose.
7. `Review` / `AggregateRating` — wherever testimonials exist, converts social proof into structured, citable data instead of paragraph text.
8. `LocalBusiness` fields specifically (`address`, `geo`, `openingHours`, `priceRange`) — often skipped even when Organization schema exists; these are what actually drive local/map-pack visibility.
9. `Service` (or `Product` for e-commerce) — structured description of what's offered, with pricing/availability where applicable.
10. `VideoObject` — wherever video is embedded, gives structured context (title, description, duration) without the engine needing to process the video itself.
11. `HowTo` — wherever content walks through a step-by-step procedure, matches how AI engines extract "how do I..." answers.
12. `ItemList` — wherever content is a ranked/ordered list, same extraction-pattern logic as HowTo.

**If `FAQPage` schema doesn't exist on a page that has visible FAQ content:**
Never hand-type the schema separately from the visible copy — they will drift out of sync the first time someone edits an answer, and Google's guidelines require schema to match what's actually rendered. Instead, generate it directly from the existing FAQ markup, for any site regardless of its specific HTML structure:
1. Identify the site's actual question/answer DOM pattern first (inspect the real markup — class names, tag structure — rather than assuming one).
2. Write or reuse a small parser matching that pattern, extracting each visible question and answer pair per page.
3. Strip answer HTML down to plain text — decode entities, remove tags, and collapse any stray whitespace left before punctuation where an inline tag (e.g. a link) was removed — since schema `text` fields must be plain text, not markup.
4. Inject one `FAQPage` JSON-LD block per page inside `<head>`, built only from that page's own visible text — never copy one page's/language's schema onto another.
5. Make the process idempotent (mark the injected block so a re-run replaces it instead of duplicating it), so schema can be regenerated any time the visible FAQ copy changes without manual JSON editing.
6. Before deploying, validate the JSON parses (e.g. `json.loads`) and that tag balance (div/section/anchor counts) in the modified file is unchanged — a bad regex match can silently mangle surrounding HTML.

### 10. Content freshness
- [ ] Page has a visible last-updated indication (or is provably updated) within the last 3-6 months
- [ ] Pricing, stats, and screenshots specifically reviewed/updated on that 3-6 month cycle — these decay fastest and get flagged first
- [ ] Flag any page with stats/pricing older than 6 months as a priority fix, not a nice-to-have
- [ ] **Don't trust a server's `Last-Modified` header as a freshness signal on its own.** A live audit found every page showing "today" purely because unrelated technical edits (adding a script tag, hreflang links) had touched the file that day — the actual pricing/stats/copy hadn't been reviewed in months. A file timestamp proves the file changed, not that anyone reviewed whether the content is still accurate.

### 11. Entity consistency
- [ ] Brand name, author names, and service names are IDENTICAL (exact string match) across: the website, Google Business Profile, LinkedIn, and any other cited profile
- [ ] Check for drift: e.g. the brand written with/without a space, with/without a legal suffix, or as the bare domain name, used inconsistently across pages — this is a real finding, not nitpicking
- [ ] This overlaps directly with item 9's schema data-accuracy check — a wrong address, phone number, or social link embedded in schema IS an entity-consistency bug, just one a validator won't catch. Check both together.

### 12. One-idea-per-paragraph structure
- [ ] Paragraphs are short and carry one discrete, quotable idea each — not multi-idea blocks that are hard to extract cleanly
- [ ] Spot-check: could a single paragraph be lifted out and stand alone as a correct, complete answer?

### 13. SEO fundamentals underneath (prerequisite, not optional)
(Fast load / Core Web Vitals → see section M below for the full technical breakdown and specific thresholds, not repeated here)
(Clean, descriptive URLs → see section L below for the full URL-structure treatment, not repeated here)
- [ ] Logical heading hierarchy (single H1, ordered H2/H3, no skipped levels)

### 14. Domain / brand authority
- [ ] Site has basic trust signals: real contact info, privacy policy, about page with real people — GEO weighs factual density/freshness over raw domain age, but authority still feeds trust scoring
- [ ] Not something to chase for its own sake — a byproduct of doing everything else on this list well over time

### 15. Multi-platform presence
- [ ] Site/brand has been checked for actual citation behavior across ChatGPT, Gemini, Perplexity, and Google AI Overviews separately — each has distinct citation patterns, a single platform check isn't representative
- [ ] Track which platform(s) cite the site and which don't, to prioritize fixes

## What to explicitly SKIP (tested, doesn't help)
- Keyword stuffing
- Text padding / artificially lengthening content
- Superficial "simplification" that removes substance without adding clarity

Don't spend audit time flagging the absence of these tactics as a gap — their absence is correct, not a finding.

## Suggested audit output format
For each site audited, produce a full table covering every checklist item run (not a prose summary of only new/notable findings), with these columns:

| Item | Result | Impact | Measured value | Why it matters | What happens if it's not fixed |
|---|---|---|---|---|---|

- **Item** — the exact checklist bullet being checked.
- **Result** — PASS or FAIL only. If a check genuinely can't be verified with the tools/access available (e.g. no Search Console, no analytics, no real device), still mark it FAIL, but add a short parenthetical naming what's missing (e.g. "FAIL (needs GSC access)") — this keeps the result binary while making clear a tooling gap isn't the same as a confirmed problem.
- **Impact** — a 1-10 rating (shown as filled/empty stars out of 10, e.g. ★★★★★★★★☆☆ = 8/10) of how much this specific item influences ranking — organic SEO and GEO/AI-answer-engine visibility combined, since they overlap heavily (item 13 is explicitly a prerequisite for GEO, not a separate concern). This is a fixed property of the ITEM itself, not of whether the site passes or fails it — score it once per checklist item, the same regardless of which site is being audited. Anchor points, so scores stay consistent across audits rather than reinvented each time:
  - **10** — the item is a hard gate: failing it removes the site from consideration entirely regardless of everything else (item 1, crawlability; basic HTTPS).
  - **8-9** — evidence-backed, high-leverage items: anything in the core 15 with a cited double-digit-percent lift in the framework's own sourcing (expert quotes, direct citations, sourced stats, schema, answer-first structure), plus Core Web Vitals and mobile-friendliness (both are direct, confirmed ranking factors at real scale).
  - **6-7** — established, broadly-agreed technical/on-page factors without a precise cited lift number here: title/meta optimization, internal linking, content depth vs. competitors, freshness, canonical/indexing hygiene.
  - **4-5** — real but secondary factors: image optimization, entity consistency, E-E-A-T polish items (author pages, Grammarly-level grammar), local-SEO tactics for a non-local-service business.
  - **2-3** — minor/contextual factors: domain age, legacy meta keywords, mega menus, print-page noindexing.
  - **1** — essentially cosmetic or a compliance/legal item with no real ranking mechanism (ToS existing, award schema) — worth doing, but not for ranking's sake.
  Where the same underlying fix affects multiple listed sub-bullets under one item, they can share one score rather than being re-derived line by line.
- **Measured value** — for any check that's actually a measurable number or threshold (character/word count, byte size, pixel dimensions, response time, click depth, etc.), this column carries the real, specific data behind the PASS/FAIL, not just the verdict. A bare "FAIL" on "title tag is roughly 30-65 characters" is not enough — the reader needs to know it failed because of exactly which page(s), and what the real number was. Required format:
  - **If checked on a single page/element**: the actual measured number, e.g. "78 characters" or "342KB".
  - **If checked across multiple pages** (e.g. title length, meta description length, image size — anything from sections B/F/M that applies sitewide): a per-page breakdown listing every page that fails, each with its own actual value — e.g. `/services/ — 78 chars`, `/contact/ — 24 chars`, not a single aggregate "3 pages fail" with no detail on which ones or by how much. A page that passes doesn't need its own line here (only the failing/borderline ones need surfacing) unless the reader asks for full sitewide data.
  - If a check has no natural numeric measurement (e.g. "expert quotes present"), leave this column empty rather than forcing a number where none applies.
- **Why it matters** — one plain-language sentence on the actual mechanism (what a crawler/user/algorithm does differently because of this), not a restatement of the item itself.
- **What happens if it's not fixed** — the concrete downstream consequence in plain language (lost visibility, a specific broken user flow, a wrong signal sent to Google/AI crawlers, etc.) — write it so someone non-technical understands the real stakes, not just "it's best practice."

Beyond the full table, also include:
1. A short list of BLOCKING issues (anything failing items 1-2 of the core 15) flagged separately and first
2. Top 3-5 highest-impact fixes, ordered by the evidence-strength ranking above (fix item 4 before item 12, all else equal)
3. A freshness re-check date (3-6 months out) logged so this doesn't become a one-time audit

---

## Supplementary: Classic Technical/On-Page SEO & Content Quality Checklist

The 15-item ranking above is GEO-specific (AI answer engines), evidence-ranked, and deliberately narrow. This section is broader, unranked, traditional-SEO-plus-E-E-A-T ground — use it alongside the ranking above, not instead of it. Items already covered above are cross-referenced rather than repeated.

### A. Technical / site architecture
- [ ] Every page has exactly one `<title>` tag and one `<h1>` (not zero, not several)
- [ ] No significant broken-link count (internal or outbound)
- [ ] No duplicate content against other pages on the same site or against content that exists elsewhere on the web
- (Click depth → see section L below, not repeated here)
- (Keyword cannibalization → see section P below, which also covers what to do once it's found, not repeated here)
- (Heading tag structure itself → see item 13 above, not repeated here)

### B. On-page keyword placement
- [ ] Primary keyword present in: the URL, the title tag, the meta description, the H1, the first sentence of body copy, and the first H2 (a close variation is fine for the H2)
- [ ] Meta description for a local-business page includes brand name, primary service, address/phone (NAP), and a call to action
- [ ] Title tag is roughly 30-65 characters (~570px) — flag both missing titles and ones so short they're clearly not descriptive, and ones long enough to get truncated in the SERP
- [ ] Meta description is roughly 70-155/160 characters — flag missing descriptions, ones too short to be useful, and ones long enough to get truncated
- [ ] No page title or meta description duplicated across pages without a canonical tag or legitimate pagination reason
- [ ] Primary keyword sits close to the start of the title tag, not buried at the end
- [ ] H1 matches the title tag's intent (if Google has visibly rewritten the displayed SERP title, that's often a signal to update the actual title tag and H1 to match, not fight it)
- [ ] If pursuing a "near me" or local-intent variant with real search volume, that variant belongs in the first H2, not forced into the H1
- [ ] Where several keyword variants exist, order by real search impressions: the highest-impression term goes in the H1, the next tier in H2s, the next in H3s
- [ ] Meta description includes a real call-to-action, not just a description, on any commercial page (not just local-business pages)
- [ ] If the site is multilingual, every translated page carries the correct `hreflang` tags pointing to its counterparts (including `x-default`)
- [ ] Legacy `meta keywords` tag: harmless if present, but carries no ranking value — don't spend time optimizing it

### C. Internal linking
- [ ] Page has 5+ unique internal links, excluding the global nav
- [ ] Internal links are placed thoughtfully (not link-dumped) and use a mix of branded and exact-match anchor text, with real variation across different keyword phrasings rather than the same anchor repeated everywhere
- [ ] The site's most authoritative/powerful pages are actively used to pass internal link equity to newer or weaker pages
- [ ] Page's internal link count is at least on par with the top-ranking competitor for that query
- [ ] Page has 5+ supporting/topically-related assets, and those supporting pages are effectively interlinked with each other and with the main page (topic cluster structure)

### D. Competitor benchmarking (run against the top 3-10 ranking competitors for the target query)
- [ ] Word count: take the competitor average (source material for this framework gave both 1.3x and 1.5x as the multiplier across two passes — treat it as a **1.3-1.5x range**, not a single precise number) and target that as a floor for comprehensiveness, not length for its own sake
- [ ] Heading count: match or exceed the competitor average
- [ ] At least half of your own headings incorporate a relevant keyword/variation (benchmark against how many of the competitors' headings do)
- [ ] Keyword density: take the competitor average, add ~0.3%, and sanity-check against an actual NLP/entity-density tool (or TF-IDF-style term-weighting, which is closer to how Google actually models term relevance) rather than a raw keyword-count ratio
- [ ] Image count: aim for roughly 1 image per 1,000 words, benchmarked against what competitors actually use
- [ ] What page TYPE is Google actually rewarding in the SERP for this query (listicle, comparison, tool, long-form guide, product page)? Match that shape, don't fight it
- [ ] Check competitor Domain Authority (or equivalent) honestly before committing budget — realistically assess whether there's a genuine chance to rank against them, not just what content gaps exist
- [ ] Competitor's real internal link count to their ranking page is a useful reference point for your own page's internal link count (see section C)

### E. Content quality & E-E-A-T
- [ ] Content reads at a high grammar-quality bar (e.g., 95+ Grammarly score) — a stricter, quantified version of item 6 above
- [ ] Content is well-structured for NLP/entity extraction, not just keyword-optimized
- [ ] Content actually satisfies the underlying search intent, not just the keyword
- [ ] Content's angle/strategy adds something a competitor doesn't already say — check this against real analytics/engagement data, not assumption
- [ ] Page is readable and scannable, and is NOT thin (shallow/low-substance) content
- [ ] Page has a table of contents where length/structure warrants one
- [ ] Google's own Helpful Content self-assessment, applied literally: is the content helpful, original, accurate, safe, and does it demonstrate real effort?
- [ ] Content is written and/or fact-checked by a genuine subject-matter expert (SME), and that SME is prominently displayed on the page (not buried)
- [ ] Each author has a real, detailed dedicated author page — not just a name
- [ ] Content demonstrates genuine first-hand / in-the-field experience: real personal perspective, first-person voice where appropriate, and evidence the writer actually did the thing (used the product, visited the place, ran the campaign) rather than synthesizing secondhand
- [ ] Entities (people, brands, products) mentioned in blog articles are real and clearly identifiable, feeding the same entity-recognition signal as item 11's consistency check above
- [ ] Body text is at least ~16px, hyperlinks are visually distinguishable from surrounding text, and font color has real contrast against its background (not "technically legible" gray-on-white) — basic accessibility, not cosmetic polish
- [ ] Content has a clear distinction between primary content (the actual answer/product) and supplementary content (related links, sidebars) — a reader shouldn't have to guess which is which
- [ ] A documented content-gap analysis exists against real competitors, not just an ad hoc sense of what's missing
- [ ] HTML validates (W3C), with no significant accessibility violations, and no deprecated HTML tags in use

### F. Images & video
- [ ] Images are unique to the site (not stock/reused elsewhere) and genuinely high-quality
- [ ] Every image is under ~100KB (performance)
- [ ] Each image's actual pixel dimensions are proportionate to its displayed CSS size, not just under a flat byte-size cap — PageSpeed Insights' "Improve image delivery" audit catches this directly (e.g. a 1024px-wide file rendered at 60px on screen), and it's a common miss precisely because the file can still pass a generic "under 100KB" rule while still being 5-10x larger than it needs to be. Resize the source file itself to roughly 2x the largest CSS size it's displayed at anywhere on the site (2x, not 1x, so it still looks sharp on high-DPI/retina screens) — don't rely on CSS `width`/`height` alone to shrink an oversized original, since the browser still downloads the full file either way
- [ ] Every image has a real, descriptive `alt` tag
- [ ] Video and image content is actually reviewed for structured-data opportunity — `VideoObject`/`ImageObject` schema applied wherever present (ties to item 9's ranked schema list above)
- [ ] Content is broken up with unique images/video rather than being a wall of unbroken text
- [ ] Images are named descriptively (the actual filename, not `IMG_4821.jpg`), and there are no dead/broken image links sitewide
- [ ] Not overly reliant on stock photography — compare stock-vs-real-photo ratio against competitors
- [ ] Brand images actually surface in Google Image search for relevant brand/product queries — check whether images are self-hosted or served from a separate asset subdomain, since either can affect this

### G. UX & conversion
- [ ] No pop-up or ad blocks the content a user actually came for
- [ ] Clear, visible calls-to-action throughout the page
- [ ] Page is actually built toward a real goal completion, not just informational for its own sake
- [ ] User-tracking/analytics software is installed and actually being reviewed, not just present
- [ ] If the site runs ads: how many appear above the fold, and are they actually relevant to the page's content (irrelevant/excessive above-the-fold ads are a real user-trust and Google quality-guideline issue)
- [ ] No video or audio that auto-plays, auto-moves, or auto-blinks without user interaction — a real accessibility violation (WCAG), not just an annoyance
- [ ] All ad and affiliate links carry `rel="nofollow"` or `rel="sponsored"` — required by Google's guidelines for paid/affiliate links
- [ ] Bounce rate isn't alarmingly high (rule of thumb: above ~80% deserves investigation) and session duration is trending in a healthy direction — read alongside real analytics, not in isolation

### H. Local SEO tactics
- [ ] Homepage doubles as a de facto "About Us" that surfaces every service offered, not just a generic hero
- [ ] Descriptive anchor text built from real customer reviews links directly to the Google Business Profile, incorporating relevant keywords naturally
- [ ] If the brand has YouTube videos ranking in search, their descriptions include timestamped keyword sections and the business's NAP (name/address/phone) below the fold of the description
- [ ] Google Business Profile itself is optimized: category selection actually matches the primary service, the product/service list on the profile mirrors the site, the description leads with location + primary services, and reviews mention location + service terms naturally
- [ ] Sidebar or footer on location pages embeds a real Google Maps widget for that location, not just a text address
- [ ] Location pages within the same state/region cross-link to each other, not just up to a single pillar page
- [ ] A location page built from one verified GBP listing can still be supported by multiple location-specific landing pages, as long as each has genuinely distinct, real content — the constraint is content depth, not the number of pages

### I. Ongoing workflow (recurring, not one-time)
- [ ] Pull Google Search Console for high-impression/low-ranking keywords on a regular cadence, cross-reference against competitor terms (e.g., via SEMrush), and work those into the page
- [ ] After adding new target keywords to a page, re-check GSC ~21 days later for what queries Google is now testing the page against, and incorporate those terms too — this is an iterative loop, not a one-off
- [ ] Refresh roughly 40% of site content monthly with meaningful edits (rule of thumb: 70-150 words of real change, not cosmetic) — content that never changes reads as stale to both users and freshness-sensitive ranking/citation systems
- [ ] New content should target a real, existing search demand (validated via GSC/SEMrush "people also ask"-style research), and ultimately tie back to revenue — publishing posts speculatively "to see what sticks" without a distribution/intent plan wastes the effort

### J. Search Console / indexing health
- [ ] Google Search Console AND Bing Webmaster Tools are both set up
- [ ] No unresolved Search Console errors; no manual actions; crawl errors reviewed and resolved
- [ ] `sitemap.xml` exists, contains no invalid URLs, and its page count roughly matches the number of pages actually indexed — a large gap between the two is itself a finding
- [ ] Utility pages that shouldn't rank on their own (internal search results, tag pages, thin category/filter combinations) carry `noindex`, not a blanket crawl block
- [ ] If a specific page isn't indexed, work through causes in order: canonical tag pointing elsewhere, missing from sitemap, `robots.txt` block, thin/duplicate content, too few internal links pointing to it, a chain of 301s obscuring the final URL, or a recent URL change that hasn't propagated
- [ ] For a non-indexed page specifically, check it has: internal links from higher-authority pages, presence in the main navigation, and — if relevant — any external signals (backlinks, social mentions) pointing to it
- [ ] Confirm whether a "not indexed" page is genuinely new (just needs time) vs. actually being ignored — check if other keyword variants for the same topic are already ranking elsewhere on the site
- [ ] No manual actions in Search Console; site is not on a blacklist
- [ ] Google Analytics is installed exactly once per page (a duplicated GA tag double-counts sessions/events and silently corrupts every report built on it)
- [ ] Brand's real social profiles are actually set up and linked (feeds `sameAs`/entity signals, not just a nice-to-have)
- [ ] Check Google's cached version of key pages to confirm what Google is actually seeing/storing, separate from what the live page shows
- [ ] If the site publishes news-style content on a regular cadence, a Google News sitemap is worth having in addition to the standard sitemap
- [ ] Search `site:brand-name` and confirm the expected sitelinks actually appear — a missing or wrong sitelink set is a real brand-visibility signal
- [ ] Check for negative search results ranking for the brand name, and for negative Google Autosuggest completions on brand searches — both are reputation issues to know about even if the fix isn't purely technical
- [ ] After a significant page change, monitor engagement signals Google itself is known to weigh: does the page hold unique visitors, how long do they stay, do they return — these take time to show up, don't judge a change on day one

### K. Benchmarks & competitive metrics (track over time, not just once)
- [ ] Total pages indexed in Google
- [ ] Total backlinks and total linking root domains (distinct domains matter more than raw link count)
- [ ] Total organic keywords ranking, and how many sit in positions 20-50 (the "next page" opportunity band, cheapest to push into the top 10)
- [ ] Domain age (context only — a data point, not something actionable on its own)
- [ ] Top 3-5 real competitors identified and benchmarked against the metrics above, plus their top-ranking keywords and average search position

### L. Site architecture — URLs, silos, and multi-location/multi-service structure
- [ ] URL structure matches intent: `service/service+location` for location-service combinations, not deep nested category chains (`/collections/category/productname` is a real anti-pattern) — favor a descriptive, readable slug over a short one (`how-to-create-a-website` beats brevity for its own sake)
- [ ] Each service+location page has real supporting content — don't create the page unless you can genuinely support it with unique content and, over time, its own links
- [ ] For a single-location business, keep the structure flat and centered on that one location's service pages rather than manufacturing state-level pages nobody searches for
- [ ] For a multi-location business, decide deliberately between a flat structure (roughly under 100-300 total pages, where every page carries strong internal links so Google reads each as important) vs. a siloed structure (larger sites) — and build a location-pillar page that lists every location and links out to each, weighted toward whichever locations/services actually drive revenue
- [ ] Don't split closely-related services into separate top-level structures if you can't realistically support both with unique content and links (e.g., two very similar legal-service niches under one firm)
- [ ] A true secondary/distinct service should get its own top-level category, not be nested under an unrelated primary one
- [ ] Homepage is optimized for the BRAND term and overall service breadth, not a single primary keyword — most homepage traffic is branded search, and secondary services belong in the footer/body copy, not competing with the H1
- [ ] Primary "money" services and locations get placed in the header and footer navigation — the highest-authority real estate on the site
- [ ] Internal link depth: important content should be reachable within 3-4 clicks of the homepage; don't bury a page you want to rank
- [ ] An HTML sitemap exists, links to every real page, uses the actual target keyword as anchor text per page, and — if pursuing external links — is itself a reasonable link target
- [ ] Primary navigation is easy to use; a breadcrumb trail is present; footer navigation includes the pages (and locations) worth ranking, plus a link back to the Google Business Profile with NAP details
- [ ] One page = one idea/intent — don't stack an informational and a transactional intent onto the same page when they'd each rank better separately (e.g., "car accident attorney [city]" as transactional vs. "car accident lawyer qualifications in [city]" as informational)
- [ ] `robots.txt` and the page-level meta robots tag are two DIFFERENT mechanisms — check both separately. `robots.txt` stops crawling; a meta `noindex` tag stops indexing of a page that's still crawled. Confirm each page's actual combination is the intended one, not an accident of theme/plugin defaults
- [ ] Paginated content uses correct pagination signals so Google understands the series rather than treating each page as thin/duplicate content
- [ ] Print-friendly page versions are `noindex`ed — they're near-duplicates of the real page and add nothing in search
- [ ] Tag pages and other auto-generated taxonomy pages are reviewed individually — either `noindex` them or make sure each one has enough unique value to justify being indexed; don't leave them on defaults
- [ ] No orphaned/"dead" category pages left over from a past structure change (e.g., an old `/category/service/` pattern nobody links to anymore)
- [ ] Consider a mega menu for service navigation on larger sites — done well, it increases the number of location/service entity combinations present in the actual HTML, not just in a dropdown JS renders after the fact
- [ ] Within a mega menu, prefer expanding a single "Service" entry into its real sub-pages (cost page, "best of" page, city variants) rather than listing every individual service name flat in the header
- [ ] Don't cross-link two unrelated supporting/blog articles directly across different content silos — route through the shared category/pillar page instead, or use a `nofollow` link between them if a direct link is genuinely necessary; the exception is the blog itself, which should always function as supporting content for services, never as its own flat, disconnected silo
- [ ] Consider naming the blog section around actual high-traffic keyword patterns (e.g., a "near me" or "tips" style URL) rather than defaulting to a generic `/blog/` slug with no keyword value of its own

### M. Technical infrastructure
- [ ] Site is fully on HTTPS with a valid SSL certificate; all HTTP requests 301-redirect to HTTPS; HSTS is in place
- [ ] No redirect chains or redirect loops; internal links point directly to final URLs, not through a redirect
- [ ] Core Web Vitals / PageSpeed Insights score is healthy (rule of thumb: 90+), benchmarked against competitor LCP, not just an absolute number
- [ ] Server response time under ~0.5s; no individual page over ~3MB; script load time under ~8.5s
- [ ] No render-blocking requests delaying first paint/LCP — check PageSpeed Insights' "Render-blocking requests" audit specifically. The most common real culprit is a plain `<link rel="stylesheet">` to an external font CSS (e.g. Google Fonts) — fix by converting it to the standard async preload+swap pattern (`<link rel="preload" as="style" href="...">` immediately followed by `<link ... rel="stylesheet" media="print" onload="this.media='all'">`, with a `<noscript>` fallback for the no-JS case) so the font loads in the background instead of blocking render. A `preconnect` to the font host alone does NOT fix this — it only speeds up the connection, the stylesheet link itself still blocks until fetched
- [ ] The page's actual LCP element (usually its largest above-the-fold image, sometimes a heading) is treated correctly — check PageSpeed Insights' "Optimize LCP" audit by name. Three things it checks specifically: the element must NOT carry `loading="lazy"` (lazy-loading the one image the page needs to paint first directly delays the metric it's supposed to help), it should carry `fetchpriority="high"` so the browser fetches it ahead of competing requests, and it must be discoverable directly in the raw server-rendered HTML (a plain `<img src="...">`, not injected by JS or hidden behind a lazy-load library) so the browser's preload scanner finds it on first parse without waiting for JS to run. An image above the fold is not itself a problem — Lighthouse expects the LCP element to often be exactly that; the fix is about how it's delivered, not whether it's there
- [ ] No forced reflow / layout-thrashing in the site's own JS — check PageSpeed Insights' "Forced reflow" audit. The pattern to look for: any place JS writes a DOM/style change (e.g. `classList.add`, `.style.X =`) and then, in the same synchronous block, reads a geometric property (`offsetWidth`/`offsetHeight`/`scrollHeight`/`clientWidth`/`getBoundingClientRect()`/`getComputedStyle()`) — that read-after-write forces the browser to compute layout immediately instead of at its normal time, which is exactly what the audit flags. This shows up most often in animated expand/collapse UI (accordions, FAQs, mobile menus) that measure `scrollHeight` to animate a `max-height` transition. Fix by deferring the read (and whatever write depends on it) into a `requestAnimationFrame` callback — the DOM/class change still happens immediately, only the measurement is pushed to the browser's next natural render pass, with no visible change in behavior
- [ ] Site is crawlable and usable with JavaScript disabled
- [ ] `.htaccess` (or platform equivalent) is configured correctly; a CDN is in use where it makes sense; favicon is present; server uptime is monitored
- [ ] No malware or blacklist flags; no unresolved Chrome DevTools console errors
- [ ] CSS is minified; inline CSS is minimized
- [ ] No pages returning 5xx errors; canonical tags are correct with no conflicting signals
- [ ] Identify what platform/CMS the site actually runs on, and note any known limitations that platform imposes (some page builders make clean URLs, schema, or crawlability genuinely harder to fix)
- [ ] Note whether the site uses subdomains vs. subfolders for major sections — this affects how link equity and crawl budget are treated across the site
- [ ] Open Graph (and, where relevant, Dublin Core) meta tags are present so social shares render a real preview instead of a blank/wrong one
- [ ] Dynamically-generated URLs (parameter-based filter/sort combinations, etc.) that create near-duplicate pages are identified and either canonicalized or blocked — don't leave them open to be crawled as if they were distinct pages
- [ ] No single page carries an excessive number of outbound external links (100+ is a reasonable line to start questioning) — dilutes both link equity and user trust
- [ ] Check what else is hosted on the same server/IP — on cheap shared hosting, a spammy neighbor can affect the site's own reputation; a dedicated IP or reputable host avoids this
- [ ] Check the domain's history (e.g., via the Wayback Machine or a domain-history tool) before assuming its age is a clean asset — a domain that previously hosted spam or was penalized carries that baggage forward

### N. Schema — additional tactical notes (extends item 9 above, same topic)
- [ ] On the homepage specifically: `Organization`/`Corporation` schema plus `Person` schema for the team/founder/authors, so that when an author byline appears on a blog post, that `Person` is already an established, linkable entity
- [ ] Use `disambiguatingDescription` inside `Organization`/`LocalBusiness` schema to reinforce what the entity actually is/does
- [ ] Don't apply the exact same schema blanket-wide — general entity schema (Organization/WebSite) belongs sitewide in the head; specific schema (`Article`, `FAQPage`) belongs on the body content it actually describes
- [ ] `Review`/`AggregateRating` schema belongs on a dedicated reviews page, not stacked on the homepage — schema.org and Google both flag review-schema stuffing on pages that aren't primarily about reviews
- [ ] FAQ content can be marked up with `FAQPage` even when it's written as ordinary paragraphs rather than a separate accordion "FAQ" section — the schema doesn't require a visually separate section, just genuine question/answer pairs in the copy
- [ ] Where a `sameAs` array is used, link to the entity's real Google Knowledge Graph ID (`/g/...`) where one exists, not just social profiles
- [ ] Schema is a comprehension aid, not a ranking signal by itself — real content and real links still have to come first; don't expect schema alone to move rankings
- [ ] If multiple schema types are used across a page, make sure they're internally consistent (the same entity referenced the same way) rather than contradicting each other
- [ ] Embedded iframes (maps, videos, forms) are considered for their own schema opportunity, not skipped just because they're iframed content
- [ ] `WebPage` schema is a real, distinct type worth using on standard pages (separate from the sitewide `WebSite` entity) when it adds genuine entity clarity
- [ ] `Award` schema is legitimate and worth adding if the business has a real, verifiable award — don't fabricate one to use it
- [ ] In `Article`/`BlogPosting` schema, put keyword emphasis in the image alt text and `articleBody`, not by keyword-stuffing the `headline` itself
- [ ] Prioritize schema effort on the homepage first — it's the page most likely to be eligible for a visible SERP enhancement (breadcrumbs, star ratings, FAQ dropdown, knowledge panel `sameAs` links)

### O. Legal & trust pages
- [ ] Privacy Policy and Terms of Service exist and are current
- [ ] Cookie/consent policy exists where required (GDPR-relevant markets)
- [ ] Contact page is easy to find, and — if it makes sense for the site — lists/links to all services

### P. Content audit additions
- [ ] Flag pages under ~200 words as thin content generally, and treat a page under ~600 words that ALSO has zero images as an even stronger thin-content signal — text volume and visual support are two separate axes of "thin," check both
- [ ] Classify content as evergreen vs. time-sensitive so freshness expectations (item 10) are set correctly per page
- [ ] A page translated into another language is a distinct, legitimate page — it is NOT duplicate content just because the underlying facts match the original language version
- [ ] Text pulled verbatim from third-party review platforms (e.g., embedding raw Google review text) can register as duplicate/thin content — converting reviews to on-page images (with a text link back to the real review) is a common legitimate workaround
- [ ] No content scraped from external sources without rewriting/adding real value
- [ ] Check whether multiple pages on the site target the same primary keyword (cannibalization) — when two pages target near-identical keywords and are splitting traffic, either merge them or deliberately differentiate their intent (informational vs. transactional vs. navigational) rather than letting both compete unfixed
- [ ] Rough content-similarity folklore worth knowing (not a verified Google policy, treat as a loose heuristic): content under roughly 60% unique vs. a source risks being read as duplicate; this is informational context for judging rewrite depth, not a target to game
- [ ] A real "Meet the Team" page exists (distinct from a single author bio) where the business has more than one person worth introducing; for a small business, Contact Us and About Us can reasonably be combined into one page rather than forced apart
- [ ] Removing content: if the page still gets traffic, 301-redirect it to the closest relevant page; if it gets none, a genuine removal (410) is fine — update the sitemap and resubmit in GSC either way, and don't treat removal itself as inherently risky
- [ ] If a specific page or page-type is under a Google manual action/penalty, removing or fixing THAT page is usually sufficient — most penalties are scoped to the specific page(s) involved, not the entire site
- [ ] For long-form blog posts, a rough heading-ratio guide worth checking against: roughly one H1, up to ~15 H2s, and H3s used sparingly (~1) — a page wildly outside this shape for its length is worth a second look, not a hard rule to force

## Explicitly excluded — deceptive, against platform guidelines, or illegal
These appeared in source material reviewed while building this framework and are deliberately NOT included as recommended practices:
- Filing a takedown (DMCA or similar) against a competitor based on a fabricated or backdated ownership claim — this is fraud, not an SEO tactic.
- Private blog networks (PBNs), buying backlinks, or any other paid/manipulative link scheme — explicitly prohibited under Google's Webmaster Guidelines and risks the site being penalized.
- Spinning/rewriting one location page into another (or scraping and lightly rewriting any content) specifically to defeat duplicate-content detection while adding no real local value.
- Creating a Google Business Profile for a location the business doesn't actually operate from.
- Asking someone to falsely claim authorship/ownership of an image or asset in exchange for a link.
- Copying a competitor's page content verbatim into your own video description/comments to try to outrank their exact title — the verbatim-copying part is a real copyright problem, not just an aggressive SEO tactic.
If an audit surfaces one of these already in use on a site, flag it as a genuine risk to remediate — don't treat it as a growth tactic to replicate elsewhere.

## Mobile Audit
Run this as its own pass — mobile and desktop can genuinely differ, and a page passing every check above can still fail here.
- [ ] Site is fully responsive across common breakpoints, not just "doesn't visually break"
- [ ] No intrusive pop-ups/interstitials on mobile specifically (Google penalizes these on mobile even when the desktop equivalent is fine)
- [ ] Mobile page weight/size is reasonable on a real mobile connection, not just tested on desktop wifi
- [ ] Images are appropriately sized/resized for mobile viewports, not just the same desktop asset scaled down in CSS
- [ ] Search Console's mobile-specific errors/usability report is clean
- [ ] If AMP is in use anywhere, confirm it's actually still serving correctly (and reconsider whether AMP is still the right call for the site at all)
- [ ] Mobile navigation is genuinely usable one-handed — menu, search, and primary CTAs are reachable with a thumb
- [ ] Buttons and links have real touch-target size (not so small/close together that mis-taps are likely)
- [ ] Video content on mobile is actually usable (doesn't break layout, doesn't auto-play data-heavy content)
- [ ] Favicon actually displays correctly in mobile SERPs
- [ ] Parity check: content, meta tags, and directives (noindex/canonical/etc.) match between the mobile and desktop rendering of the same URL — a mismatch here is a real, easy-to-miss bug
- [ ] Test on a real device (or real device emulation), not just a resized browser window

## Sitemap Health Check
Run this as its own pass — a sitemap can look fine from `robots.txt` alone (URL present, 200 status) while still being broken, stale, or actively contradicting the rest of the site. Added 2026-08-27 after finding and fixing a real case of this on a WordPress site: the CMS's SEO-plugin-generated sitemap was silently missing every page that existed only as a static file (a new blog post plus a full set of translated pages) simply because none of them had an underlying database post/page object for the plugin to enumerate.
- [ ] The URL(s) listed in `robots.txt`'s `Sitemap:` line actually resolve, return HTTP 200, and are valid, well-formed XML (a single malformed tag can cause a crawler to abandon the whole file)
- [ ] Every URL inside the sitemap is one the site actually wants indexed — cross-check the full sitemap URL list against `robots.txt`'s `Disallow` rules; a URL appearing in both is a direct contradiction (a real example: a set of sub-sitemaps listed pages under paths that were simultaneously blocked in `robots.txt` — the sitemap plugin and the block list had drifted out of sync with each other)
- [ ] No sitemap entry is a redirect (301/302) or an error (4xx/5xx) target — a sitemap should only ever list final, canonical, 200-status URLs (found live: `/checkout/` was listed despite being a 302 redirect stub, not real content)
- [ ] Every sitemap URL's own `<link rel="canonical">` tag points back to that exact same URL — a sitemap listing a non-canonical version of a page sends a mixed signal
- [ ] Check whether the sitemap is dynamically generated (by an SEO plugin/CMS) or a static file — this determines both how it's fixed and its single biggest blind spot: a dynamically-generated sitemap only knows about content that exists as a real object in that system (e.g. a WordPress post/page row) — any page added by another route (direct file upload, a different CMS, a manually-built static page) will silently never appear, with no error or warning
- [ ] If any pages are confirmed static-only per the check above, either get them into the CMS as real objects, or maintain a supplementary/consolidated sitemap that includes them explicitly — don't assume "it's in the sitemap system" covers pages added outside that system
- [ ] Sitemap page count is sanity-checked against the number of pages the site actually intends to have indexed (not just "some number greater than zero") — both a suspiciously low count (missing content) and a suspiciously high one (junk/parameter/utility URLs leaking in) are findings
- [ ] If translated/localized versions of pages exist (e.g. `uk/`, `pl/` prefixes), confirm they're actually present in the sitemap — don't assume hreflang tags on the page itself are a substitute; they serve a different purpose (language/region signaling) and don't help discovery the way a sitemap listing does
- [ ] If a sitemap was rebuilt or hand-edited (rather than left to auto-generate), a note now exists somewhere obvious that it will NOT auto-update going forward — confirm there's a known trigger/process for regenerating it when pages are added, removed, or blocked, rather than assuming it'll silently stay in sync
