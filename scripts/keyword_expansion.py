#!/usr/bin/env python3
"""
55DigitalAI — Ad-Group-by-Ad-Group Keyword Expansion
=============================================================
Purpose  : Given a set of candidate keywords proposed per ad group (an LLM
           or human generates these — see /55-keyword-expansion), check their
           real search volume via the Google Ads KeywordPlanIdeaService,
           dedupe against every keyword already in the account (any status,
           any ad group — avoids adding the same phrase to two ad groups),
           and either report the winners (read-only) or write the approved
           subset as new ad group criteria.

           Two-step by design: `check` never writes to the account. `apply`
           only ever adds the exact keywords found in the approved file —
           it does not re-run volume checks or decide anything on its own.
           Always run `check`, show the user the winners, get explicit
           approval, THEN run `apply` on the (possibly trimmed) approved file.

Usage    : python3 scripts/keyword_expansion.py list-ad-groups <client_slug> [--status any|enabled|paused]
           python3 scripts/keyword_expansion.py suggest <client_slug> [--status enabled] [--idea-limit 15]
             (seeds Keyword Planner idea-generation from each ad group's own core phrase —
             writes RAW/unfiltered suggested_candidates.json; review for relevance before `check`)
           python3 scripts/keyword_expansion.py check <client_slug> --candidates candidates.json
             (writes winners.json — the candidates that had real volume)
           python3 scripts/keyword_expansion.py apply <client_slug> --approved winners.json [--match-type PHRASE] [--cpc-bid 2.00]

           candidates.json shape: {"<ad_group_resource_name>": ["term one", "term two"], ...}
           winners.json / approved.json shape: [{"ad_group": "...", "ad_group_name": "...",
             "text": "...", "avg_monthly_searches": N, "competition": "..."}, ...]
Changelog: 2026-07-18  Initial version — extracted from an ad-hoc client keyword
                       expansion session into a reusable two-step tool.
           2026-07-27  Added --cpc-bid to apply (account currency, not micros) —
                       Manual CPC campaigns otherwise leave new keywords with no
                       bid of their own, silently inheriting the ad group default.
           2026-07-30  Added `suggest` — manually brainstorming candidates per ad group
                       (the original Step 2 of /55-keyword-expansion) missed obvious gaps
                       that Keyword Planner's own idea-generation mode surfaces immediately
                       when seeded from the ad group's existing core phrase (confirmed on a
                       live client account: one seed term turned up ~17 relevant real-volume
                       gaps vs. 3 found by manual brainstorming for the same ad group).
                       `suggest` automates the seeding but NOT the relevance judgment — idea
                       mode routinely surfaces competitor brand names, marketplace/secondhand
                       intent, and other off-topic terms alongside genuine gaps, so its output
                       is an unfiltered candidates.json meant for review, not a skip-ahead to
                       `check`.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402
from keyword_research import GEO_TARGET_CONSTANTS, LANGUAGE_CONSTANTS, fetch_keyword_ideas  # noqa: E402 — single source of truth; this file used to duplicate these with a stale language constant, fixed 2026-07-26
from change_log import log_change, new_run_id  # noqa: E402


def normalize(t):
    return " ".join(t.lower().strip().split())


def cmd_list_ad_groups(client_meta, status):
    from google.ads.googleads.client import GoogleAdsClient

    ga_client = GoogleAdsClient.load_from_storage("google-ads.yaml")
    ga = ga_client.get_service("GoogleAdsService")

    status_filter = ""
    if status == "enabled":
        status_filter = "WHERE campaign.status = 'ENABLED' AND ad_group.status = 'ENABLED'"
    elif status == "paused":
        status_filter = "WHERE campaign.status = 'PAUSED' AND ad_group.status = 'ENABLED'"

    query = f"""
        SELECT campaign.name, campaign.status, ad_group.name, ad_group.resource_name, ad_group.status,
               ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.negative
        FROM keyword_view
        {status_filter}
        ORDER BY campaign.name, ad_group.name, ad_group_criterion.keyword.text
    """
    rows = list(ga.search(customer_id=client_meta["customer_id"], query=query))
    by_ag = {}
    for r in rows:
        key = r.ad_group.resource_name
        if key not in by_ag:
            by_ag[key] = {"campaign": r.campaign.name, "campaign_status": r.campaign.status.name,
                          "ad_group": r.ad_group.name, "ad_group_status": r.ad_group.status.name, "keywords": []}
        by_ag[key]["keywords"].append((r.ad_group_criterion.keyword.text, r.ad_group_criterion.negative))

    # keyword_view does NOT implicitly filter out REMOVED ad groups (only REMOVED
    # criteria) — a removed ad group with surviving keyword rows would otherwise
    # look identical to a live one here. Flag it loudly since expansion candidates
    # for a dead ad group go nowhere (seen live on a real account, where this
    # silently produced a pointless recommendation).
    #
    # Also flag NEGATIVE keywords distinctly — keyword_view returns both positive
    # and negative criteria with no visual difference otherwise, which caused
    # DSA ad groups' single negative keyword (an excluded term) to be misread as
    # an existing positive theme to expand around (same account, same incident).
    for resource, info in by_ag.items():
        ag_flag = "" if info["ad_group_status"] == "ENABLED" else f"  *** AD GROUP {info['ad_group_status']} — DO NOT propose keywords here ***"
        print(f"{resource}  [campaign:{info['campaign_status']}/ad_group:{info['ad_group_status']}] {info['campaign']} > {info['ad_group']}  ({len(info['keywords'])} kw){ag_flag}")
        for text, negative in info["keywords"]:
            print(f"    {'- [NEGATIVE] ' if negative else '- '}{text}")


def cmd_suggest(client_meta, status, idea_limit, out_path):
    """For each eligible Search ad group, seed Keyword Planner's idea-generation mode
    (GenerateKeywordIdeas) from that ad group's own core phrase — the shortest existing
    positive keyword, on the theory that it's the generic "hub" term rather than an
    already-elaborated long-tail variant (e.g. "ikea" for a pure-brand ad group,
    "ikea wardrobes" for a wardrobes ad group). Writes only the ideas that are both new
    (not already anywhere in the account) and have real search volume — same candidates.json
    shape `check` consumes. This is NOT a relevance filter: idea mode routinely surfaces
    competitor brand names, marketplace/secondhand intent, and other off-topic terms — the
    output here is meant to be reviewed and trimmed before it's passed to `check`."""
    from google.ads.googleads.client import GoogleAdsClient

    ga_client = GoogleAdsClient.load_from_storage("google-ads.yaml")
    ga = ga_client.get_service("GoogleAdsService")

    status_filter = ""
    if status == "enabled":
        status_filter = "WHERE campaign.status = 'ENABLED' AND ad_group.status = 'ENABLED'"
    elif status == "paused":
        status_filter = "WHERE campaign.status = 'PAUSED' AND ad_group.status = 'ENABLED'"

    query = f"""
        SELECT campaign.name, ad_group.name, ad_group.resource_name, ad_group.status, ad_group.type,
               ad_group_criterion.keyword.text, ad_group_criterion.negative
        FROM keyword_view
        {status_filter}
        ORDER BY campaign.name, ad_group.name, ad_group_criterion.keyword.text
    """
    rows = list(ga.search(customer_id=client_meta["customer_id"], query=query))
    by_ag = {}
    for r in rows:
        key = r.ad_group.resource_name
        if key not in by_ag:
            by_ag[key] = {"campaign": r.campaign.name, "ad_group": r.ad_group.name,
                          "ad_group_type": r.ad_group.type_.name, "positive_keywords": []}
        if not r.ad_group_criterion.negative:
            by_ag[key]["positive_keywords"].append(r.ad_group_criterion.keyword.text)

    # DSA ad groups (ad_group.type == SEARCH_DYNAMIC_ADS) can't take manually-added positive
    # keywords at all — any positive-looking keywords sitting there are inert leftovers from
    # before conversion to DSA. PMax has no ad_group/keyword concept, so it never appears in
    # keyword_view to begin with. Detect via ad_group.type (not the campaign-name convention)
    # so this doesn't silently break on an account that names campaigns differently.
    eligible = {ag: info for ag, info in by_ag.items()
                if info["ad_group_type"] == "SEARCH_STANDARD" and info["positive_keywords"]}
    skipped = [f"{info['ad_group']} ({info['ad_group_type']})" for info in by_ag.values()
               if info["ad_group_type"] != "SEARCH_STANDARD"]
    if skipped:
        print(f"Skipping {len(skipped)} non-Search-standard ad group(s): {', '.join(skipped)}\n")

    country = client_meta.get("country", "PL")
    geo = GEO_TARGET_CONSTANTS.get(country)
    language = LANGUAGE_CONSTANTS.get(country)
    if not geo or not language:
        sys.exit(f"No geo/language constant configured for country '{country}' — "
                  f"add it to GEO_TARGET_CONSTANTS / LANGUAGE_CONSTANTS in keyword_research.py.")

    existing_q = "SELECT ad_group_criterion.keyword.text FROM keyword_view"
    existing = {normalize(r.ad_group_criterion.keyword.text) for r in ga.search(customer_id=client_meta["customer_id"], query=existing_q)}

    network_enum = ga_client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

    candidates = {}
    proposed_this_run = set()
    print(f"Seeding Keyword Planner idea-generation from each ad group's own core phrase ({len(eligible)} eligible ad groups)...\n")
    failed = []
    seed_cache = {}  # seed text -> list(idea_response) — two ad groups can land on the identical
                      # seed (e.g. an A/B test running the same ad group under two campaigns), and
                      # querying Keyword Planner twice for the same seed wastes a call and was what
                      # tipped this into a 429 quota error live; share the result instead.
    for ag, info in eligible.items():
        seed = min(info["positive_keywords"], key=lambda t: (len(t.split()), len(t)))

        if seed in seed_cache:
            idea_response = seed_cache[seed]
        else:
            # One ad group's request failing (transient upstream 500s/429s happen — seen live) must
            # not lose the results already gathered for every other ad group in this run, so isolate
            # per-ad-group and keep going; write out whatever succeeded either way. A single retry
            # covers the transient 429 case (Google's own error message says "retry in N seconds").
            idea_response = None
            for attempt in range(2):
                try:
                    idea_response = list(fetch_keyword_ideas(ga_client, client_meta["customer_id"], [seed], geo, language, network_enum))
                    break
                except Exception as e:
                    is_quota = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
                    if is_quota and attempt == 0:
                        print(f"[{info['ad_group']}]  seed=\"{seed}\"  hit quota, retrying in 8s...")
                        time.sleep(8)
                        continue
                    print(f"[{info['ad_group']}]  seed=\"{seed}\"  FAILED: {e}\n")
                    failed.append(info["ad_group"])
                    break
            if idea_response is None:
                continue
            seed_cache[seed] = idea_response

        found = []
        for r in idea_response:
            n = normalize(r.text)
            if n in existing or n in proposed_this_run:
                continue
            vol = r.keyword_idea_metrics.avg_monthly_searches or 0
            if vol <= 0:
                continue
            comp = r.keyword_idea_metrics.competition.name if r.keyword_idea_metrics.competition is not None else "n/a"
            found.append((r.text, vol, comp))

        found.sort(key=lambda x: -x[1])
        found = found[:idea_limit]

        print(f"[{info['ad_group']}]  seed=\"{seed}\"  ({len(found)} new candidates with volume)")
        terms = []
        for text, vol, comp in found:
            print(f"    {vol:>6}  {comp:8s}  {text}")
            terms.append(text)
            proposed_this_run.add(normalize(text))
        if terms:
            candidates[ag] = terms
        print()

    Path(out_path).write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in candidates.values())
    print(f"Wrote {total} raw candidates across {len(candidates)} ad groups to {out_path}.")
    print("UNFILTERED Keyword Planner suggestions — review each for relevance (competitor names, "
          "wrong intent, off-topic) before running `check` on the trimmed file.")
    if failed:
        print(f"\n{len(failed)} ad group(s) failed and were skipped (rerun `suggest` to retry — likely transient): {', '.join(failed)}")


def cmd_check(client_meta, candidates_path, out_path):
    from google.ads.googleads.client import GoogleAdsClient

    candidates = json.loads(Path(candidates_path).read_text(encoding="utf-8"))

    ga_client = GoogleAdsClient.load_from_storage("google-ads.yaml")
    ga = ga_client.get_service("GoogleAdsService")

    existing_q = "SELECT ad_group_criterion.keyword.text FROM keyword_view"
    existing = {normalize(r.ad_group_criterion.keyword.text) for r in ga.search(customer_id=client_meta["customer_id"], query=existing_q)}

    ag_names_q = "SELECT ad_group.resource_name, ad_group.name FROM ad_group"
    ag_names = {r.ad_group.resource_name: r.ad_group.name for r in ga.search(customer_id=client_meta["customer_id"], query=ag_names_q)}

    term_to_ag = {}
    all_terms = []
    for ag, terms in candidates.items():
        for t in terms:
            n = normalize(t)
            if n in existing or n in term_to_ag:
                continue
            term_to_ag[n] = ag
            all_terms.append(t)

    if not all_terms:
        print("Nothing new to check — every candidate is already in the account.")
        Path(out_path).write_text("[]", encoding="utf-8")
        return

    country = client_meta.get("country", "PL")
    geo = GEO_TARGET_CONSTANTS.get(country)
    language = LANGUAGE_CONSTANTS.get(country)
    if not geo or not language:
        sys.exit(f"No geo/language constant configured for country '{country}' — "
                  f"add it to GEO_TARGET_CONSTANTS / LANGUAGE_CONSTANTS in keyword_research.py.")

    kwp = ga_client.get_service("KeywordPlanIdeaService")
    req = ga_client.get_type("GenerateKeywordHistoricalMetricsRequest")
    req.customer_id = client_meta["customer_id"]
    req.keywords = all_terms
    req.language = language
    req.geo_target_constants = [geo]
    req.keyword_plan_network = ga_client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

    response = kwp.generate_keyword_historical_metrics(request=req)

    winners = []
    for result in response.results:
        vol = result.keyword_metrics.avg_monthly_searches or 0
        if vol <= 0:
            continue
        n = normalize(result.text)
        ag = term_to_ag.get(n)
        if not ag:
            for cv in result.close_variants:
                ag = term_to_ag.get(normalize(cv))
                if ag:
                    break
        if ag:
            winners.append({
                "ad_group": ag,
                "ad_group_name": ag_names.get(ag, ag),
                "text": result.text,
                "avg_monthly_searches": vol,
                "competition": result.keyword_metrics.competition.name,
            })

    winners.sort(key=lambda w: -w["avg_monthly_searches"])
    print(f"Checked {len(all_terms)} new candidates across {len(candidates)} ad groups — {len(winners)} have real volume:\n")
    for w in winners:
        print(f"  {w['avg_monthly_searches']:>6}  {w['competition']:8s}  [{w['ad_group_name']}]  {w['text']}")

    Path(out_path).write_text(json.dumps(winners, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWinners written to {out_path} — review with the user before running `apply`.")


def cmd_apply(client_meta, approved_path, match_type_name, confirm, cpc_bid=None):
    approved = json.loads(Path(approved_path).read_text(encoding="utf-8"))
    if not approved:
        print("Approved file is empty — nothing to add.")
        return

    bid_micros = round(cpc_bid * 1_000_000) if cpc_bid is not None else None
    bid_note = f", cpc_bid={cpc_bid:.2f}" if cpc_bid is not None else " (no explicit bid — inherits ad group default)"

    if not confirm:
        print(f"DRY RUN — {len(approved)} keywords would be added ({match_type_name} match{bid_note}). "
              f"Nothing was changed. Pass --confirm to actually write these to the account.\n")
        for item in approved:
            print(f"  [would add] {item['text']}  -> {item.get('ad_group_name', item['ad_group'])}")
        return

    from google.ads.googleads.client import GoogleAdsClient

    ga_client = GoogleAdsClient.load_from_storage("google-ads.yaml")
    match_type = getattr(ga_client.enums.KeywordMatchTypeEnum, match_type_name)

    ops = []
    seen = set()
    sent_items = []
    for item in approved:
        dedup_key = (item["text"], item["ad_group"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        op = ga_client.get_type("AdGroupCriterionOperation")
        crit = op.create
        crit.ad_group = item["ad_group"]
        crit.status = ga_client.enums.AdGroupCriterionStatusEnum.ENABLED
        crit.keyword.text = item["text"]
        crit.keyword.match_type = match_type
        if bid_micros is not None:
            crit.cpc_bid_micros = bid_micros
        ops.append(op)
        sent_items.append(item)

    service = ga_client.get_service("AdGroupCriterionService")
    result = service.mutate_ad_group_criteria(customer_id=client_meta["customer_id"], operations=ops)
    print(f"Added {len(result.results)} keywords ({match_type_name} match{bid_note}).")

    run_id = new_run_id()
    for item in sent_items:
        log_change(client_slug=client_meta["slug"], script="keyword_expansion.py",
                   action="add_keyword", resource_type="ad_group_criterion",
                   resource_id=item["ad_group"], detail=f"{item['text']} ({match_type_name}{bid_note})",
                   reason=f"volume={item.get('avg_monthly_searches')}", run_id=run_id)


def main():
    parser = argparse.ArgumentParser(description="Ad-group-by-ad-group keyword expansion (two-step: check, then apply)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list-ad-groups", help="Dump ad groups + existing keywords (read-only)")
    p1.add_argument("client")
    p1.add_argument("--status", choices=["any", "enabled", "paused"], default="any")

    p1b = sub.add_parser("suggest", help="Seed Keyword Planner idea-generation from each ad group's own core phrase; "
                                          "writes RAW/unfiltered candidates.json for review before `check` (read-only)")
    p1b.add_argument("client")
    p1b.add_argument("--status", choices=["any", "enabled", "paused"], default="enabled")
    p1b.add_argument("--idea-limit", type=int, default=15,
                      help="Max new-candidate ideas to keep per ad group, sorted by volume (default: 15)")
    p1b.add_argument("--out", default="suggested_candidates.json")

    p2 = sub.add_parser("check", help="Check candidate volume, write winners.json (read-only, makes zero account changes)")
    p2.add_argument("client")
    p2.add_argument("--candidates", required=True)
    p2.add_argument("--out", default="winners.json")

    p3 = sub.add_parser("apply", help="Add the approved winners as new keywords (writes to the account)")
    p3.add_argument("client")
    p3.add_argument("--approved", required=True)
    p3.add_argument("--match-type", default="PHRASE", choices=["EXACT", "PHRASE", "BROAD"])
    p3.add_argument("--cpc-bid", type=float, default=None,
                     help="Explicit CPC bid in the account's currency (e.g. 2.00), not micros. "
                          "Relevant for Manual CPC campaigns — without it, new keywords inherit the "
                          "ad group's default bid. Omit for Smart Bidding / Target CPA / Maximize Conversions etc.")
    p3.add_argument("--confirm", action="store_true",
                     help="Actually write to the account. Without this, dry-run only.")

    args = parser.parse_args()

    try:
        client_meta = resolve(args.client)
    except KeyError as e:
        print(str(e).strip('"'))
        sys.exit(2)

    if args.cmd == "list-ad-groups":
        cmd_list_ad_groups(client_meta, args.status)
    elif args.cmd == "suggest":
        cmd_suggest(client_meta, args.status, args.idea_limit, args.out)
    elif args.cmd == "check":
        cmd_check(client_meta, args.candidates, args.out)
    elif args.cmd == "apply":
        cmd_apply(client_meta, args.approved, args.match_type, args.confirm, args.cpc_bid)


if __name__ == "__main__":
    main()
