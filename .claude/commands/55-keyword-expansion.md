---
description: Ad-group-by-ad-group keyword expansion — propose thematically similar keywords per ad group, verify real search volume, and add only what the user approves
---

Expand keywords for client **$1** (optionally scoped to a campaign/theme named in the rest of the arguments — e.g. "only the Winter Tires campaign"). This is a two-step, read-then-write process — never skip the approval step, even if the user already approved the general approach.

## Step 1 — Understand the existing structure
Run: `.venv/bin/python3 scripts/keyword_expansion.py list-ad-groups $1 --status enabled`
This restricts to ad groups that are **fully active — campaign ENABLED and ad group ENABLED**. A PAUSED campaign isn't in scope for this command even if its ad group is technically ENABLED — don't propose candidates for it (if the user specifically wants to prep keywords for a paused campaign ahead of a relaunch, that's a separate, explicit ask — confirm with them rather than including it by default). Read the client's `clients/$1/client-brief.md` too, for services offered and negative-intent rules (e.g. don't propose purchase-intent terms for a service-only business).

Two things the output still flags that change what's eligible for Step 2 — learned from a real incident on a live account, where skipping this check produced a pointless recommendation for a dead ad group:
- **`*** AD GROUP <status> ***` flags** — `--status enabled` already excludes non-ENABLED ad groups, but if you ever run with `--status any` for diagnostic purposes, never propose candidates for anything flagged REMOVED or PAUSED here.
- **`[NEGATIVE]`-prefixed keywords** — these are exclusions, not existing positive targeting themes. Don't read a negative keyword as "this ad group already covers X, propose more like X" — it means the opposite. Don't propose the same negated term again either.
- **DSA and PMax ad groups can't take manually-added positive keywords at all** — DSA targets pages dynamically (any keywords you see there, if not negative, are inert leftovers from before the campaign was converted to DSA), and PMax has no ad-group/keyword concept in the first place (asset groups only). Skip these entirely rather than proposing candidates that can never be applied. Confirm campaign type from Step 1's campaign name/context if unsure — if the client has any DSA/PMax campaigns and the scope isn't already narrowed to Search-only, ask the user to confirm which campaigns are in scope before Step 2 (see also `/55-pmax-brand-generic-audit` for PMax-specific keyword work, which is a different mechanism — asset group signals, not ad group keywords).

## Step 2 — Propose candidates per ad group (your judgment, not the script's)
For each **fully active (campaign ENABLED, ad group ENABLED), Search (non-DSA/PMax)** ad group, generate 1–4+ thematically similar candidates that aren't already covered (more than 4 is fine when the ad group is thin or the theme supports it — don't stop at the low end just to stay tidy; a richer candidate pool finds more real winners in Step 3). What's actually worked well in practice (learned from a real client account, 2026-07-18):
- **Cross-language spelling variants** were the single highest-yield category — e.g. a bilingual or multi-script market whose keywords only cover one language/script is often missing the other spelling of the same query. Always check both if the market plausibly searches in either.
- **Price-intent variants** (translations of "price", "cost", "how much", "quote", etc. in the account's target language) often have small but real, high-value volume — worth trying even (especially) in ad groups that currently have zero price-intent terms.
- **Geo variants** (city name in the local language vs. transliterated) if not already present.
- Avoid inventing generic terms unrelated to the ad group's specific theme — stay tightly on-theme per ad group, don't propose account-wide generic terms here (that's a different, structural conversation).
- Respect the client brief's "Always Negate" rules — don't propose a candidate that the brief would flag as irrelevant/wrong-intent. If no client brief exists, say so plainly and ask the user whether to proceed on ad-group-structure judgment alone or pause until one exists.
- Don't propose more competitor-brand terms just because one already exists in the account (e.g. a rival brand name sitting in an ad group as a positive keyword) — that's a targeting-strategy call for the user, not a same-theme expansion.

Write candidates to a JSON file: `{"<ad_group_resource_name>": ["term one", "term two"], ...}` (resource names come from Step 1's output — when a theme has multiple fully-active duplicates, e.g. an A/B test running two enabled campaigns side by side, ask the user before deciding whether to add to all of them or just one).

## Step 3 — Check real volume (read-only)
Run: `.venv/bin/python3 scripts/keyword_expansion.py check $1 --candidates <file> --out winners.json`
This dedupes against every keyword already in the account (any ad group), checks real Google Ads historical search volume, and writes only the candidates with real volume (>0) to `winners.json`. **Makes zero account changes.**

## Step 4 — Present findings and get explicit approval
Show the user the full list from `winners.json`, grouped by ad group, with volume and competition. **Always stop here and wait for explicit approval before proceeding — do not add anything automatically, even if the user approved doing this "for all ad groups" or similar in principle.** Approval of the method is not approval of the specific resulting list. If the user wants to trim the list (drop low-volume or high-competition ones), edit `winners.json` accordingly before Step 5.

## Step 5 — Check the bidding strategy before applying
Before running `apply`, check the bidding strategy of the campaign(s) the winning ad groups belong to: `SELECT campaign.name, campaign.bidding_strategy_type FROM campaign WHERE campaign.id = <id>` (or read it off Step 1's output if already known).

**If it's `MANUAL_CPC`:** a newly-created keyword with no bid of its own silently inherits the ad group's default bid, which may not be what the user wants for these specific new terms. Ask the user (one AskUserQuestion call covers both):
- Do you want me to set an explicit CPC bid on these new keywords, or leave them on the ad group default?
- If yes — how much (in the account's currency), and which match type: PHRASE or EXACT? (Don't silently default to PHRASE or "whatever the ad group mostly uses" when the strategy is Manual CPC — ask, since the bid and match type are the two levers that matter most under manual bidding.)

**If it's Smart Bidding / Target CPA / Maximize Conversions / etc.:** bids aren't set per-keyword under these strategies, so skip the bid question — just confirm match type against the ad group's existing convention as before.

## Step 6 — Add the approved keywords
Only after explicit approval: `.venv/bin/python3 scripts/keyword_expansion.py apply $1 --approved winners.json --match-type <PHRASE|EXACT> [--cpc-bid <amount>] --confirm`
**Safe by default** — without `--confirm`, `apply` only prints what it would add and writes nothing; run it once without `--confirm` first if you want a final sanity check on the exact list (it also echoes back the bid, or notes "no explicit bid" if `--cpc-bid` was omitted — confirm that matches what the user asked for in Step 5 before re-running with `--confirm`). `--cpc-bid` takes a plain amount in the account's currency (e.g. `2.00`), not micros. Confirm what was added afterward (script prints a count; every added keyword is also recorded in the shared change log — `scripts/change_log.py show $1`).
