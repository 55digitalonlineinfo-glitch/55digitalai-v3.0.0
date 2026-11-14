#!/usr/bin/env python3
"""
55DigitalAI — Keyword Research (Keyword Planner in the terminal)
=============================================================
Purpose  : Pull search volume, competition level, CPC bid range, and a
           12-month search volume trend for a list of keyword terms, via
           the Google Ads KeywordPlanIdeaService (the API behind Keyword
           Planner's "Get search volume and forecasts" tool). Cross-checks
           each term against keywords already active in the client's
           account to flag what's already covered vs. genuinely new.

           Also runs Keyword Planner's "Get keyword ideas" mode
           (GenerateKeywordIdeas, seeded from the requested terms) by
           default, surfacing related terms the user didn't explicitly ask
           about — same cross-check against the account applies. Pass
           --no-ideas to skip this and only check the exact terms given.

           Read-only. Makes zero changes to the account.

Usage    : python3 scripts/keyword_research.py <client_slug> "term one, term two"
           python3 scripts/keyword_research.py <client_slug> --file terms.txt
           python3 scripts/keyword_research.py <client_slug> "term" --network search_and_partners
           python3 scripts/keyword_research.py <client_slug> "term" --no-ideas
           python3 scripts/keyword_research.py <client_slug> "term" --idea-limit 50
Changelog: 2026-07-18  Initial version
           2026-07-27  Added "similar keyword ideas" section (GenerateKeywordIdeas,
                       on by default) — previously only reported data for the exact
                       terms requested, with no way to discover related terms.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

# Google Ads geo target / language constant resource names, covering Europe generally so new
# European clients don't need new IDs guessed — all values below were verified live against
# GeoTargetConstantService.suggest and the language_constant resource on 2026-07-26, not recalled
# from training data.
#
# BUG FIX (2026-07-26): the "UA" language constant was languageConstants/1023, which is actually
# Hindi, not Ukrainian (1036) — a copy-paste/transposition error present since this file's creation
# and duplicated into keyword_expansion.py. This means every /55-keyword-research, /55-keyword-expansion,
# and /55-feed-title-optimizer run for an account configured with language=UA queried Keyword Planner
# with Hindi as the language parameter instead of Ukrainian. Geo targeting (correct) likely dominated
# enough that results still looked plausible in practice, but this was a real error, not just
# imprecision — now fixed. If historical numbers from before this date look off on a UA-language
# client, this is the first thing to suspect.
GEO_TARGET_CONSTANTS = {
    "PL": "geoTargetConstants/2616",  # Poland
    "UA": "geoTargetConstants/2804",  # Ukraine
    "DE": "geoTargetConstants/2276",  # Germany
    "FR": "geoTargetConstants/2250",  # France
    "ES": "geoTargetConstants/2724",  # Spain
    "IT": "geoTargetConstants/2380",  # Italy
    "NL": "geoTargetConstants/2528",  # Netherlands
    "CZ": "geoTargetConstants/2203",  # Czechia
    "RO": "geoTargetConstants/2642",  # Romania
    "PT": "geoTargetConstants/2620",  # Portugal
    "SE": "geoTargetConstants/2752",  # Sweden
    "AT": "geoTargetConstants/2040",  # Austria
    "BE": "geoTargetConstants/2056",  # Belgium — bilingual NL/FR, language below defaults to Dutch; override per client
    "DK": "geoTargetConstants/2208",  # Denmark
    "FI": "geoTargetConstants/2246",  # Finland
    "IE": "geoTargetConstants/2372",  # Ireland
    "HU": "geoTargetConstants/2348",  # Hungary
    "SK": "geoTargetConstants/2703",  # Slovakia
    "BG": "geoTargetConstants/2100",  # Bulgaria
    "GR": "geoTargetConstants/2300",  # Greece
    "LT": "geoTargetConstants/2440",  # Lithuania
    "LV": "geoTargetConstants/2428",  # Latvia
    "EE": "geoTargetConstants/2233",  # Estonia
    "HR": "geoTargetConstants/2191",  # Croatia
    "SI": "geoTargetConstants/2705",  # Slovenia
    "NO": "geoTargetConstants/2578",  # Norway (not EU, but European)
    "CH": "geoTargetConstants/2756",  # Switzerland — multi-language DE/FR/IT, language below defaults to German; override per client
}
LANGUAGE_CONSTANTS = {
    "PL": "languageConstants/1030",  # Polish
    "UA": "languageConstants/1036",  # Ukrainian (fixed 2026-07-26, was wrongly 1023/Hindi)
    "DE": "languageConstants/1001",  # German
    "FR": "languageConstants/1002",  # French
    "ES": "languageConstants/1003",  # Spanish
    "IT": "languageConstants/1004",  # Italian
    "NL": "languageConstants/1010",  # Dutch
    "CZ": "languageConstants/1021",  # Czech
    "RO": "languageConstants/1032",  # Romanian
    "PT": "languageConstants/1014",  # Portuguese
    "SE": "languageConstants/1015",  # Swedish
    "AT": "languageConstants/1001",  # German
    "BE": "languageConstants/1010",  # Dutch default — Belgium is genuinely bilingual, check the client's actual market before trusting this
    "DK": "languageConstants/1009",  # Danish
    "FI": "languageConstants/1011",  # Finnish
    "IE": "languageConstants/1000",  # English
    "HU": "languageConstants/1024",  # Hungarian
    "SK": "languageConstants/1033",  # Slovak
    "BG": "languageConstants/1020",  # Bulgarian
    "GR": "languageConstants/1022",  # Greek
    "LT": "languageConstants/1029",  # Lithuanian
    "LV": "languageConstants/1028",  # Latvian
    "EE": "languageConstants/1043",  # Estonian
    "HR": "languageConstants/1039",  # Croatian
    "SI": "languageConstants/1034",  # Slovenian
    "NO": "languageConstants/1013",  # Norwegian
    "CH": "languageConstants/1001",  # German default — Switzerland is genuinely multi-language, check the client's actual market before trusting this
}

MONTH_ABBR = {
    "JANUARY": "Jan", "FEBRUARY": "Feb", "MARCH": "Mar", "APRIL": "Apr",
    "MAY": "May", "JUNE": "Jun", "JULY": "Jul", "AUGUST": "Aug",
    "SEPTEMBER": "Sep", "OCTOBER": "Oct", "NOVEMBER": "Nov", "DECEMBER": "Dec",
}


def micros(v):
    return v / 1_000_000


def normalize(term):
    return " ".join(term.lower().strip().split())


def fetch_existing_keywords(ga, customer_id):
    """All active keyword texts already on the account, normalized, for the duplicate cross-check."""
    query = """
        SELECT ad_group_criterion.keyword.text
        FROM keyword_view
        WHERE ad_group_criterion.status = 'ENABLED'
    """
    existing = set()
    for row in ga.search(customer_id=customer_id, query=query):
        existing.add(normalize(row.ad_group_criterion.keyword.text))
    return existing


def fetch_historical_metrics(client, ga_client, customer_id, terms, geo, language, network_enum):
    kwp_idea_service = ga_client.get_service("KeywordPlanIdeaService")
    request = ga_client.get_type("GenerateKeywordHistoricalMetricsRequest")
    request.customer_id = customer_id
    request.keywords = terms
    request.language = language
    request.geo_target_constants = [geo]
    request.keyword_plan_network = network_enum
    return kwp_idea_service.generate_keyword_historical_metrics(request=request)


def fetch_keyword_ideas(ga_client, customer_id, seed_terms, geo, language, network_enum, page_size=200):
    """Keyword Planner's 'Get keyword ideas' mode (GenerateKeywordIdeas, seeded from seed_terms) —
    distinct from fetch_historical_metrics above, which only returns data for the exact terms given.
    This surfaces related/similar terms Google itself suggests, same as the Keyword Planner UI's
    'keyword ideas' tab. Returns the raw iterator; caller filters/sorts/limits."""
    kwp_idea_service = ga_client.get_service("KeywordPlanIdeaService")
    request = ga_client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.keyword_seed.keywords.extend(seed_terms)
    request.language = language
    request.geo_target_constants.append(geo)
    request.keyword_plan_network = network_enum
    request.page_size = page_size
    return kwp_idea_service.generate_keyword_ideas(request=request)


def build_ideas_section(idea_response, already_shown, existing_keywords, idea_limit):
    """already_shown: normalized texts already covered in the ## RESULTS section (the terms the
    user explicitly asked about, plus their close variants) — ideas mode re-suggests these
    constantly since they're the seed, so skip re-listing them here."""
    lines = ["\n## SIMILAR KEYWORD IDEAS (Keyword Planner suggestions, not explicitly requested)"]
    lines.append("Read every row with judgment before recommending it — idea mode routinely surfaces")
    lines.append("competitor/other-business names and off-topic suggestions alongside genuine gaps.")

    seen = set()
    ideas = []
    for r in idea_response:
        n = normalize(r.text)
        if n in already_shown or n in seen:
            continue
        seen.add(n)
        vol = r.keyword_idea_metrics.avg_monthly_searches or 0
        if vol <= 0:
            continue
        ideas.append({
            "text": r.text,
            "vol": vol,
            "competition": r.keyword_idea_metrics.competition.name if r.keyword_idea_metrics.competition is not None else "n/a",
            "low_bid": micros(r.keyword_idea_metrics.low_top_of_page_bid_micros) if r.keyword_idea_metrics.low_top_of_page_bid_micros else None,
            "high_bid": micros(r.keyword_idea_metrics.high_top_of_page_bid_micros) if r.keyword_idea_metrics.high_top_of_page_bid_micros else None,
            "in_account": n in existing_keywords,
        })

    ideas.sort(key=lambda i: -i["vol"])
    shown = ideas[:idea_limit]

    if not shown:
        lines.append("\n  (no additional ideas with real volume beyond what's already shown above)")
        return "\n".join(lines)

    for i in shown:
        status = "[IN ACCOUNT]" if i["in_account"] else "[NEW]"
        bid = f"{i['low_bid']:.2f}–{i['high_bid']:.2f}" if i["low_bid"] and i["high_bid"] else "n/a"
        lines.append(f"\n  {status} \"{i['text']}\"")
        lines.append(f"    avg monthly vol. : {i['vol']}")
        lines.append(f"    competition      : {i['competition']}")
        lines.append(f"    top-of-page CPC  : {bid}")

    if len(ideas) > idea_limit:
        lines.append(f"\n  ...and {len(ideas) - idea_limit} more with lower volume (use --idea-limit to see more).")

    return "\n".join(lines)


def build_report(client_meta, terms, response, existing_keywords, network_label):
    lines = []
    lines.append("=" * 70)
    lines.append(f"  Keyword Research: {client_meta['name']}")
    lines.append(f"  Terms requested : {len(terms)}")
    lines.append(f"  Network         : {network_label}")
    lines.append("=" * 70)

    matched_texts = set()
    lines.append("\n## RESULTS")
    for result in response.results:
        text = result.text
        matched_texts.add(normalize(text))
        for cv in result.close_variants:
            matched_texts.add(normalize(cv))

        m = result.keyword_metrics
        avg_searches = m.avg_monthly_searches if m.avg_monthly_searches is not None else "n/a"
        competition = m.competition.name if m.competition is not None else "n/a"
        comp_idx = m.competition_index if m.competition_index is not None else "n/a"
        low_bid = f"{micros(m.low_top_of_page_bid_micros):.2f}" if m.low_top_of_page_bid_micros else "n/a"
        high_bid = f"{micros(m.high_top_of_page_bid_micros):.2f}" if m.high_top_of_page_bid_micros else "n/a"

        in_account = normalize(text) in existing_keywords
        status = "[IN ACCOUNT]" if in_account else "[NEW]"

        lines.append(f"\n  {status} \"{text}\"")
        if result.close_variants:
            lines.append(f"    close variants   : {', '.join(result.close_variants)}")
        lines.append(f"    avg monthly vol. : {avg_searches}")
        lines.append(f"    competition      : {competition} (index {comp_idx}/100)")
        lines.append(f"    top-of-page CPC  : {low_bid} – {high_bid}")

        volumes = sorted(
            [v for v in m.monthly_search_volumes if v.monthly_searches is not None],
            key=lambda v: (v.year, v.month),
        )
        if volumes:
            trend = " ".join(f"{MONTH_ABBR.get(v.month.name, v.month.name[:3])}{str(v.year)[2:]}:{v.monthly_searches}" for v in volumes)
            lines.append(f"    12mo trend       : {trend}")

    not_found = [t for t in terms if normalize(t) not in matched_texts]
    if not_found:
        lines.append(f"\n  No historical data returned for: {', '.join(not_found)} (too low volume, or deduped into a close variant above)")

    new_terms = [normalize(r.text) for r in response.results if normalize(r.text) not in existing_keywords]
    dup_terms = [normalize(r.text) for r in response.results if normalize(r.text) in existing_keywords]
    lines.append("\n## ACCOUNT CROSS-CHECK")
    lines.append(f"  Already in account : {len(dup_terms)}")
    lines.append(f"  New — consider adding: {len(new_terms)}")

    return "\n".join(lines), matched_texts


def main():
    parser = argparse.ArgumentParser(description="Keyword Planner data for a list of terms (read-only)")
    parser.add_argument("client", help="Client slug (e.g. acme) or raw customer_id")
    parser.add_argument("terms", nargs="?", help="Comma-separated list of terms")
    parser.add_argument("--file", help="Path to a file with one term per line (alternative to positional terms)")
    parser.add_argument("--network", choices=["search", "search_and_partners"], default="search",
                         help="Keyword Plan network (default: search)")
    parser.add_argument("--no-ideas", action="store_true",
                         help="Skip the 'similar keyword ideas' section (Keyword Planner's idea-generation "
                              "mode, seeded from the requested terms) — on by default.")
    parser.add_argument("--idea-limit", type=int, default=20,
                         help="Max number of similar-keyword ideas to show, sorted by volume (default: 20)")
    args = parser.parse_args()

    try:
        client_meta = resolve(args.client)
    except KeyError as e:
        print(str(e).strip('"'))
        sys.exit(2)

    if args.file:
        terms = [t.strip() for t in Path(args.file).read_text(encoding="utf-8").splitlines() if t.strip()]
    elif args.terms:
        terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    else:
        print("Provide terms as a comma-separated argument or via --file")
        sys.exit(2)

    if len(terms) > 10000:
        print(f"Note: {len(terms)} terms given — GenerateKeywordHistoricalMetrics accepts at most 10,000 per request; trimming to the first 10,000.")
        terms = terms[:10000]

    country = client_meta.get("country", "PL")
    geo = GEO_TARGET_CONSTANTS.get(country)
    language = LANGUAGE_CONSTANTS.get(country)
    if not geo or not language:
        print(f"No geo/language constant configured for country '{country}' — add it to GEO_TARGET_CONSTANTS / LANGUAGE_CONSTANTS in this script.")
        sys.exit(2)

    from google.ads.googleads.client import GoogleAdsClient

    ga_client = GoogleAdsClient.load_from_storage("google-ads.yaml")
    ga = ga_client.get_service("GoogleAdsService")

    network_enum = (
        ga_client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH_AND_PARTNERS
        if args.network == "search_and_partners"
        else ga_client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    )
    network_label = "Google Search + Partners" if args.network == "search_and_partners" else "Google Search"

    existing_keywords = fetch_existing_keywords(ga, client_meta["customer_id"])
    response = fetch_historical_metrics(client_meta, ga_client, client_meta["customer_id"], terms, geo, language, network_enum)

    report, matched_texts = build_report(client_meta, terms, response, existing_keywords, network_label)
    print(report)

    if not args.no_ideas:
        idea_response = fetch_keyword_ideas(ga_client, client_meta["customer_id"], terms, geo, language, network_enum)
        print(build_ideas_section(idea_response, matched_texts, existing_keywords, args.idea_limit))

    print("=" * 70)


if __name__ == "__main__":
    main()
