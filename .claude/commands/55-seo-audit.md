---
description: Full SEO + GEO (AI answer engine) audit - 218 checks (15 GEO items, sections A-P, Mobile, Sitemap), table with Impact, measured values per page, completeness gate, optional client PDF
---

Run the SEO / GEO audit for **$1** (a URL, or a client slug from `clients.json`). Read-only - never changes the site.

Source of truth: `system-prompts/frameworks/geo-audit-framework.md` (218 checks). Backing script: `scripts/seo_audit.py` - it parses that file, gives every check an ID (C01-1 ... MAP-09), pins the count per section and refuses to run if the file drifted. **Never type the checklist from memory and never audit from a shortened list.**

Needs Playwright's Chromium once: `.venv/bin/python3 -m playwright install chromium`.

## Step 1 - Scope (always ALL, never ask)
Always audit **all 218 checks** (15 GEO items + sections A-P + Mobile + Sitemap). Do not offer a "just the GEO items" shortcut. Run `.venv/bin/python3 scripts/seo_audit.py list` once and show the section counts. Only ask for what cannot be discovered: the target keyword/page for on-page checks (B-01...), a sample blog page (`--page URL`), and whether the business is local (H section) or multilingual.

## Step 2 - Capture
`.venv/bin/python3 scripts/seo_audit.py capture <url> [--slug SLUG] [--pages 8] [--page URL ...]`
Fetches robots.txt, sitemap, the homepage + sampled sitemap pages (raw HTML, so it sees what crawlers see), tests AI-bot user-agent fetches (diagnostic only, never to bypass a block), http->https, PageSpeed Insights (may be rate limited), a Playwright render + JS-off + iPhone-390 pass, link/image/sitemap-entry status checks. Writes `capture.json` to `clients/<slug>/reports/seo_audit_YYYY-MM-DD/` (with `--slug`) or `seo-audits/<host>/seo_audit_YYYY-MM-DD/` (your own site or a prospect).
If the site blocks the fetch (403/bot check), say so and ask the user for screenshots / the HTML; never get around the block.

## Step 3 - Scaffold + judge
`.venv/bin/python3 scripts/seo_audit.py scaffold <slug-or-host>` writes `results.json` with EVERY check:
- **auto** - measured from the capture (status, `measured` with per-page values, evidence, fix);
- **needs** - cannot be verified with the available tools (Search Console, SEMrush, Grammarly, real device, AI-platform citation tests): pre-set to **FAIL (needs <tool>)**. Binary on purpose; a tooling gap is not a confirmed problem. If the user supplies the data, replace it with a real verdict;
- **TODO** - judgement: read the page text (WebFetch/curl the pages, signals in `capture.json`) and decide PASS / FAIL / N/A with real evidence (quote the visible text, name the page), a concrete `fix` for FAIL, and for threshold checks the real number in `measured` (one line per failing page). N/A only with a reason (e.g. H local-SEO items on a non-local business).
Work section by section, write results after each section, run `.venv/bin/python3 scripts/seo_audit.py validate <results.json>` often. **Do not report until it prints COMPLETE.** Also re-read auto verdicts that look odd (e.g. a 429 from an AI bot may be rate limiting from the capture itself - re-test before calling it a block) and fix the script if a heuristic misfires.
Rules from the framework: schema must be cross-checked against the site's own facts (C09-5), check static vs CMS pages separately (C09-4), never trust `Last-Modified` as freshness (C10-4), keyword stuffing/padding absence is not a finding, and the "explicitly excluded" tactics are flagged as a risk if found.

## Step 4 - Show the results in the chat (always, before anything else)
`.venv/bin/python3 scripts/seo_audit.py report <results.json>` prints and saves `report.md`. **Always list the results in the chat right after the audit, before offering anything**, in this order:
1. Totals (PASS / FAIL with how many are tooling gaps / N/A) and the link to `report.md`.
2. **High / Medium / Low fix summary** (grouped by theme, each with the concrete fix, not one line per check) and blocking issues first (GEO items 1-2, noindex, JS-only content).
3. **All 218 checks in one table** with columns `# | Result | Imp | Check | Finding | Why we need it (+ if fixed / - if not) | Proposed fix` (every row has Finding, Why and Proposed fix). Section by section, every check present as its own row, no merged rows (tooling-gap rows too: name the tool in Finding and give the fix as "get <tool> data"). The Why column states the positive and the negative. The version with measured values is in `report.md`.
4. Caveats: which verdicts are judgement, sample size, script fixes made during the run.
Link every page with its full URL; no em dashes; plain wording.

## Step 5 - Offer the PDF, then ask what to fix first (always, in this order, after Step 4)
**5a. PDF:** ask "PDF for the client?" (AskUserQuestion). If yes, ask **what the PDF lists**, offering **Failed and passed** first as the default:
1. **Failed and passed** (`--show failed+passed`) - confirmed FAIL plus PASS; checks that need a tool or manual review (and N/A) are left out;
2. **Only failed** (`--show failed`) - confirmed FAIL checks only;
3. **All of them** (`--show all`) - every check, including the ones that need manual review and N/A.

The PDF uses the same dark A4 glass style as `/55-web-guidelines-audit` (`scripts/feed_report_pdf.py` base CSS, agency name and logo from `brand_config.json`): cover with KPI tiles + section list, then High/Medium/Low fix pages, then one glass card per check. Page 1 shows an SEO health score (0-100 circle gauge, impact-weighted share of passed checks among verifiable ones; N/A and tool-gap checks excluded), the strongest and weakest section (sections with 3+ verifiable checks) and a bar chart of the score per section. The summary counts on page 1 always cover all checks. Every card carries three blocks: **Finding** (what was seen/measured), **Why we need it** (if done right / if not) and **Proposed fix** (concrete steps, with a High/Medium/Low priority tag), and page 1 has a "Fix first" summary. For every confirmed FAIL write specific `why`, `consequence` and a step-by-step `fix` into results.json before building the PDF; do not rely on the generic section text. Checks that only lack data (Search Console, GA4, PageSpeed) must carry `needs`, not a plain FAIL. Then `.venv/bin/python3 scripts/seo_audit.py pdf <results.json> --show <choice>` (refuses while results are incomplete), open the PDF, and look at a rendered page (downscaled) before calling it done. The PDF is English only; if the client's language (`client_language(slug)` in `scripts/client_registry.py`) is different, say so and ask whether English is fine.

**5b. What to fix first:** ask the user (AskUserQuestion, header "Fix first") which area to start with, offering the top 3-4 concrete priorities from this audit as options (e.g. the blocking issue, schema, titles/meta/H1, trust content) plus "Other". Do not start any fix until they choose; then propose the exact change list and apply it only after they approve that exact list.

## Rules
- Read-only. Fixes only after the user approves the exact list.
- Evidence or it didn't happen: no verdict without something you saw or measured.
- Fixes and the PDF are separate decisions: never build the PDF without asking Step 5.
