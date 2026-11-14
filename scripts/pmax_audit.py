#!/usr/bin/env python3
"""
55DigitalAI — Plain PMax Search Term Audit (interactive)
=============================================================
Purpose  : On-demand irrelevant-keyword scan for Performance Max campaigns,
           the PMax analog of negative_keyword_audit.py. Source is
           campaign_search_term_view across every ENABLED PMax campaign on
           the account, merged into one list — no branded-vs-generic split.
           (For that heavier, campaign-type-aware audit — branded PMax
           excluding non-brand terms, separate exclusion list per type —
           see pmax_brand_generic_audit.py / /pmax-brand-generic-audit
           instead. This script is the simple version: same judgment as
           /keyword-audit, just against PMax traffic.)

           This script only FETCHES — it applies no AI judgment and writes
           nothing. Classification (which terms are irrelevant per the
           client's brief) is done by Claude reading this output, exactly
           like negative_keyword_audit.py's flow, then presented to the
           user for explicit confirmation before anything is written.
           Writing is a separate step, reusing add_shared_negatives.py
           unchanged — same shared negative-keyword list, same
           SharedCriterionService pattern, called only after confirmation.

           Writes to the same client_registry.py "negative_list_id" that
           /keyword-audit already uses. If it isn't configured yet for this
           client, this script won't guess — use negative_keyword_audit.py's
           list-lists/create-list/set-list subcommands (same list, so no
           need to duplicate that logic here), then re-run fetch.

           This is the backing script for /pmax-audit.

Usage    : python3 pmax_audit.py fetch <client_slug> [--days 4] [--top 100 --sort-by <cost|impressions>]
Changelog: 2026-07-27  Initial version
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

from google.ads.googleads.client import GoogleAdsClient

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def get_enabled_pmax_campaigns(ga_service, customer_id):
    query = """
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
          AND campaign.status = 'ENABLED'
    """
    return [
        {"id": str(row.campaign.id), "name": row.campaign.name}
        for row in ga_service.search(customer_id=customer_id, query=query, timeout=60)
    ]


def fetch_pmax_search_terms(ga_service, customer_id, campaign_ids, days, sort_by="cost", top=None):
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)

    # Merged across campaigns: the same term can recur in more than one PMax
    # campaign, and a human reviewing this list cares about total spend/signal
    # on that term, not which campaign happened to trigger it first.
    merged = {}
    for cid in campaign_ids:
        query = f"""
            SELECT campaign_search_term_view.search_term,
                   metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
            FROM campaign_search_term_view
            WHERE campaign.id = {cid}
              AND segments.date BETWEEN '{date_from}' AND '{date_to}'
              AND metrics.impressions >= 1
            ORDER BY metrics.cost_micros DESC
            LIMIT 2000
        """
        for row in ga_service.search(customer_id=customer_id, query=query, timeout=120):
            term = row.campaign_search_term_view.search_term
            if term not in merged:
                merged[term] = {"term": term, "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0}
            merged[term]["impressions"] += row.metrics.impressions
            merged[term]["clicks"] += row.metrics.clicks
            merged[term]["cost"] += round(row.metrics.cost_micros / 1_000_000, 2)
            merged[term]["conversions"] += row.metrics.conversions

    sort_key = (lambda r: r["cost"]) if sort_by == "cost" else (lambda r: r["impressions"])
    rows = sorted(merged.values(), key=sort_key, reverse=True)
    total_found = len(rows)
    if top:
        rows = rows[:top]
    return rows, date_from, date_to, total_found


def cmd_fetch(args):
    client_meta = resolve(args.client)
    negative_list_id = client_meta.get("negative_list_id")

    if not negative_list_id:
        print(f"No negative_list_id configured for '{args.client}' in client_registry.py.")
        print("This is the same shared negative-keyword list /keyword-audit uses. Configure it with:")
        print(f"  python3 scripts/negative_keyword_audit.py list-lists {args.client}")
        print(f"  python3 scripts/negative_keyword_audit.py set-list {args.client} --id <ID>")
        print(f"...or create a new one:")
        print(f"  python3 scripts/negative_keyword_audit.py create-list {args.client} --name \"...\"")
        sys.exit(3)

    brief_path = WORKSPACE_ROOT / "clients" / args.client / "client-brief.md"
    if not brief_path.exists():
        print(f"No client-brief.md found at {brief_path}")
        sys.exit(2)

    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = ads_client.get_service("GoogleAdsService")
    customer_id = client_meta["customer_id"]

    campaigns = get_enabled_pmax_campaigns(ga_service, customer_id)
    if not campaigns:
        print("No ENABLED Performance Max campaigns found on this account.")
        sys.exit(4)

    rows, date_from, date_to, total_found = fetch_pmax_search_terms(
        ga_service, customer_id, [c["id"] for c in campaigns],
        args.days, sort_by=args.sort_by, top=args.top,
    )

    print(f"Client            : {client_meta['name']} ({args.client})")
    print(f"Shared list       : {negative_list_id}")
    print(f"PMax campaigns    : {len(campaigns)} — " + ", ".join(c["name"] for c in campaigns))
    print(f"Period            : {date_from} -> {date_to} ({args.days} days)")
    if args.top and total_found > args.top:
        print(f"Search terms found: {total_found} (showing top {args.top} by {args.sort_by}, merged across campaigns)")
    else:
        print(f"Search terms found: {total_found} (merged across campaigns)")
    print()
    print("=== CLIENT BRIEF ===")
    print(brief_path.read_text())
    print()
    print("=== SEARCH TERMS (cost | impressions | conversions | term) ===")
    for r in rows:
        print(f"{r['cost']:.2f}|{r['impressions']}i|{r['conversions']:.0f}cv|{r['term']}")


def main():
    parser = argparse.ArgumentParser(description="Fetch data for an interactive plain PMax search-term audit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Pull PMax search terms + client brief for this client")
    p_fetch.add_argument("client")
    p_fetch.add_argument("--days", type=int, default=4)
    p_fetch.add_argument("--top", type=int, default=None,
                          help="Only fetch the top N search terms (by --sort-by), merged across campaigns")
    p_fetch.add_argument("--sort-by", choices=["cost", "impressions"], default="cost",
                          help="Ranking used with --top (default: cost)")
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
