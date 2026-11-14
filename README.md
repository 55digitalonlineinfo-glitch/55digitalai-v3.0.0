# 55DigitalAI

Google Ads account management via Claude Code slash commands — audits, keyword research/expansion, GA4 reporting, and PMax search-term analysis, driven by a per-client config instead of hardcoded accounts.

**New here?** See [`GETTING_STARTED.md`](GETTING_STARTED.md) for a plain-language walkthrough. This README is the technical reference.

This is a sanitized, generalized fork of an internal agency workspace — every script here reads client identity from `clients.json` (via `scripts/client_registry.py`) and per-client judgment rules from `clients/<slug>/client-brief.md`. Both are gitignored (same protection as `google-ads.yaml`) — real client data never accidentally ends up in this repo's git history, yours or a future buyer's.

## Setup

**Guided (recommended):** `bash setup.sh` (Mac/Linux) or `setup.bat` (Windows) — creates a `.venv`, installs dependencies into it, and runs the wizard in one step. Walks you through the developer token / OAuth setup (customer IDs can be pasted with dashes, they're cleaned up automatically), runs the browser consent flow, writes `google-ads.yaml`, makes a live test call listing the real accounts under your MCC, lets you pick one to configure as your first client, then pulls a real spend/campaign number for that specific account as final proof it's connected. It also looks up your shared negative-keyword list by name (as shown in Google Ads > Tools & Settings > Shared Library) and resolves the ID for you, instead of requiring you to hunt down a numeric ID by hand. Re-run it any time to add another client — it detects existing credentials and skips straight to that part. See `GETTING_STARTED.md` for the full walkthrough including the Google Cloud/Ads API setup this depends on.

Every slash command in `.claude/commands/` invokes `.venv/bin/python3` directly (not a bare `python3`), so the `.venv` created by `setup.sh`/`setup.bat` has to exist at that exact path — commands won't find their interpreter otherwise.

**On Mac, don't put this project in Desktop, Documents, Downloads, or an iCloud/Dropbox/Google Drive sync folder.** Those are gated by macOS privacy controls (TCC), and the scheduled automation this wizard sets up (daily checks, keyword audits) runs via `launchd` in the background — those background runs get silently blocked from reading/writing files in a protected folder unless you manually grant `/bin/bash` Full Disk Access in System Settings. A plain location like `~/55digitalai-main` needs no such grant. `setup.sh` checks for this and refuses to continue if it detects a protected folder (override with `ALLOW_PROTECTED_FOLDER=1 bash setup.sh` if you're sure, e.g. no scheduled automation planned). If the project already lives in a protected folder, move it first: `mv ~/Downloads/55digitalai-main ~/55digitalai-main`, then re-run setup — this also regenerates `.venv`, since a venv's `pip`/`activate` hardcode the absolute path they were created at and break if the folder is moved afterward.

**Manual, if you'd rather:**
1. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Copy `google-ads.yaml.example` → `google-ads.yaml`, fill in your own Google Ads API credentials (see comments in that file for how to get a developer token + OAuth credentials, or run `.venv/bin/python3 scripts/get_google_refresh_token.py` for just the refresh-token step). This file is gitignored — never commit it.
3. Copy `clients/_template/` → `clients/<your-client-slug>/`, fill in `client-brief.md` — or auto-draft a starting point from their website: `.venv/bin/python3 scripts/generate_brief.py <slug> <url>` (the setup wizard offers this automatically). Review it either way; a generated draft is explicitly marked as unreviewed.
4. Copy `clients.json.example` to `clients.json` if it doesn't exist yet (or just run any script once — it bootstraps itself), then replace the `acme` example with your real client, and delete the example entry. Look up your shared negative-keyword list's ID under Google Ads > Tools & Settings > Shared Library (click into the list — the ID is in the URL) and set `negative_list_id`, so audit scripts don't fail with "No negative_list_id configured."
5. Run any slash command, e.g. `/55-daily-check <your-client-slug>`.

## What's here

- `clients.json` — client slug -> account metadata (customer ID, currency, budget, list IDs). Plain data, not code, specifically so `setup_wizard.py` (or you) can edit it safely without risking Python syntax. Gitignored — ships as `clients.json.example`, and `scripts/client_registry.py` auto-copies that to `clients.json` on first run if it's missing. Every other script imports from `client_registry.py`, not from this file directly.
- `setup.sh` / `setup.bat` — one-command entry point (installs dependencies, then runs the wizard).
- `scripts/build_release.sh [output-dir]` — for maintainers only, not buyers: builds a clean copy of this project for distribution, stripping real credentials (`google-ads.yaml`), real client data (`clients.json`, every `clients/<slug>/` folder except `_template`), and local build/runtime artifacts (`.venv`, `dashboard/`, `change_log.db`, `.claude/settings.local.json`). Aborts loudly instead of producing output if anything real slips through. Also zips the result. Defaults to writing next to this project (`../55digitalai-release`), never inside it.
- `scripts/setup_wizard.py` — guided first-run setup + "add another client," described above.
- `scripts/` — the engine: read-only reporting (`daily_check.py`, `ga4_reports.py`, `campaign_analyst.py`, `merchant_review.py`, `seasonality.py`, `keyword_research.py`), and write-capable workflows gated behind an explicit `--confirm` flag (`add_shared_negatives.py`, `keyword_expansion.py`, `pmax_brand_generic_audit.py`, `pmax_bucketing.py`).
- `scripts/change_log.py` — shared SQLite audit trail. Every write path logs to it; query with `.venv/bin/python3 scripts/change_log.py show <client_slug>` or `--all`, or check the **Negatives** tab ("Other logged changes") in the local dashboard (`.venv/bin/python3 scripts/build_dashboard.py`, then `open dashboard/index.html`). Local-only, gitignored, never sent anywhere.
- `scripts/term_cache.py` — caches `pmax_brand_generic_audit.py`'s AI classification decisions per (client, campaign, term, client-brief version), so a term already classified under the current brief isn't re-sent to Claude on the next run. Editing `client-brief.md` automatically invalidates the affected cache entries — no manual cache-clearing needed.
- `scripts/generate_brief.py <slug> <url> [<url2> ...]` — fetches a client's website and asks Claude to draft `client-brief.md` from it. The setup wizard offers this automatically after adding a client. **The output is a draft, clearly marked as one** — the brief is the single most safety-critical file in the toolkit (every negative-keyword/PMax audit reasons against it), so an AI's read of a homepage is a starting point for someone who knows the business to correct, never a substitute for that review.
- `scripts/gaql_helper.py` — `safe_search()` wrapper for GAQL queries: catches the known DURING-literal gotcha before it hits the API, and translates common `GoogleAdsException` failures (auth, permission, quota, bad field) into a plain-English hint alongside the raw error.
- `brand_config.json` + `scripts/pdf_common.py` / `scripts/brand.py` — your agency's name/colors/logo for PDF exports, loaded from this one file (not hardcoded) so every buyer's PDFs are branded as their own agency.
- `scripts/generate_audit_pdf.py` — renders the structured "full account audit" JSON (see the file's docstring for the schema) into a branded PDF.
- `scripts/text_report_pdf.py` — generic renderer for everything else: pass it the plain-text output of any report script and it produces a branded PDF, no bespoke schema needed. `daily_check.py`, `campaign_analyst.py run`, `merchant_review.py`, and `seasonality.py` all support a `--pdf` flag built on this.
- `.claude/commands/` — the slash commands that orchestrate the scripts above with human-in-the-loop approval before any write.
- `system-prompts/` — the PPC reasoning frameworks and specialist agent prompts the AI judgment steps use.
- `clients/_template/` — copy this per client (or let `setup_wizard.py` do it).

## Website & Merchant Center audits

Two read-only commands that check a client's *website* (not just the ad account). Both write their output under `clients/<slug>/reports/` and finish with an optional client-branded PDF (the client's own colors/logo, no agency branding).

- `/55-merchant-policy-check <slug>` - Merchant Center misrepresentation pre-flight. `scripts/merchant_policy_check.py` compares Merchant Center settings, the feed and ~20 key website pages against Google's Shopping policies (contact details, shipping/returns/terms/privacy content, price and availability match, fake urgency, feed quality...), then Claude reads the saved page texts for what keywords can't catch. Needs `domain` in `clients.json`; adding `merchant_center_id` unlocks the Merchant Center side (otherwise only the website checks run). Optional `about_url` in the client's `clients.json` entry points the check at an About page whose URL doesn't say "about". Reference: `system-prompts/frameworks/merchant-policy-checklist.md`. PDF: `scripts/policy_report_pdf.py`.
- `/55-cro-audit <slug>` - 342-check conversion audit (general, home, category, landing, product, cart, checkout, thank-you). `scripts/cro_audit.py` owns the check IDs and a completeness gate: the report and PDF refuse to build while any selected check is still TODO or has no evidence. For `"business_type": "ecommerce"` clients it also pulls the GA4 sales funnel (`scripts/ga4_funnel_export.py`) and benchmarks each step. Reference: `system-prompts/frameworks/cro-audit-checklist.txt`. PDF: `scripts/cro_report_pdf.py` (labels for English, Ukrainian and Polish; any other language falls back to English until a label set is added).
- `/55-seo-audit <url|slug>` - 218-check SEO + GEO (AI answer engine) audit: 15 GEO items, classic technical / on-page / E-E-A-T sections A-P, Mobile and Sitemap health. `scripts/seo_audit.py` captures robots.txt, sitemap, sampled pages (raw HTML + rendered + JS-off + iPhone width), AI-crawler access and link status, pre-fills what it can measure, marks tool gaps (Search Console, SEMrush...) as `needs`, and refuses to report until every check has a verdict. Reference: `system-prompts/frameworks/geo-audit-framework.md`. PDF: `seo_audit.py pdf --show failed|failed+passed|all` (English).
- `/55-web-guidelines-audit <url|path|slug>` - 61-point design / mobile / accessibility / "AI-look" audit measured on the rendered page (desktop 1440px + iPhone 390px): spacing, tap targets, contrast, focus, reduced motion, glow, glass, card grids, copy cliches and more. `scripts/guidelines_audit.py` draws an annotated screenshot per point, writes `audit.json` + `report.md` and a PDF; with `--before` it shows before/after screenshots of the same section. Reference: `system-prompts/frameworks/web-design-rules.md`. Report in English.
- `/55-web-animation <url|path>` - proposes (and after approval builds) purposeful motion from 20 UX & animation principles, within the guidelines audit's motion rules.

**One-time browser install** for `/55-cro-audit`, `/55-seo-audit` and `/55-web-guidelines-audit` page capture (Playwright is already in `requirements.txt`): `.venv/bin/python3 -m playwright install chromium`. The merchant check needs no browser. `scripts/video_frames.swift` (macOS only) extracts frames from a screen recording when a site blocks automated capture.

## Safety convention

Every workflow that writes to a live Google Ads account follows the same pattern: a read-only `check`/`fetch` step, an AI-judgment `analyze` step, a **step that shows the full proposed change list to a human**, and only then an `apply`/`--confirm` step. Never skip the approval step, even if the user already approved the general approach — approving "do a keyword audit" is not approval of the resulting list.

**Every write-capable script defaults to dry-run.** `add_shared_negatives.py`, `keyword_expansion.py apply`, `pmax_brand_generic_audit.py`, and `pmax_bucketing.py apply` all print what they *would* do and change nothing unless you pass `--confirm` explicitly — there is no flag that silently writes by default. Every actual write also gets a row in `change_log.py`, so "what has this ever changed on my account" is always a query away, not an archaeology exercise through text logs.

## Known gaps (not yet ported from the internal workspace)

- **No Sheets export** — PDF export exists (see above); a Google Sheets export for feeding an existing reporting workflow does not yet.
- **`--pdf` not wired into every read-only script** — `daily_check.py`, `campaign_analyst.py run`, `merchant_review.py`, and `seasonality.py` have it; `ga4_reports.py` and `keyword_research.py` don't yet, though `text_report_pdf.py` would need no changes to support them, just the same few lines added to each `main()`.
- **`term_cache.py` only covers `pmax_brand_generic_audit.py`** — the other AI-judgment steps (`55-keyword-audit`, `keyword-expansion`, `55-feed-title-optimizer`) don't have caching yet; `pmax_brand_generic_audit.py` was the one with a documented real cost problem (see its changelog), so it came first.
- **`gaql_helper.safe_search()` isn't wired into every script yet** — built and proven, but only referenced as the pattern to follow; most scripts still call `ga_service.search()` directly. Worth migrating over time, not blocking.
- **Scheduling** — no cron/launchd setup is included. Pick whatever your OS supports, or use GitHub Actions on a schedule if you want something portable. If you do wire any write-capable script into an unattended schedule, keep `--confirm` behind a deliberate decision, not the default — an unattended AI misclassification on a stranger's live ad account is a real failure mode.

## Requirements

- [Claude Code](https://claude.com/claude-code) with an Anthropic API key (used by the AI-judgment steps — `55-keyword-audit`, `55-pmax-brand-generic-audit`, `keyword-expansion`, `55-feed-title-optimizer`)
- A Google Ads API developer token (Basic access is enough for one agency/MCC managing its own accounts)
- Python 3.10+
