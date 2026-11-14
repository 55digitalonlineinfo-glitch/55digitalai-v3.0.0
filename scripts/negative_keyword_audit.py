#!/usr/bin/env python3
"""
55DigitalAI — Negative Keyword Audit (interactive)
=============================================================
Purpose  : On-demand version of the scheduled negative-keyword audit
           (see CLAUDE.md's "Automated Routines") — pulls recent search
           terms and the client's brief for a human-in-the-loop run,
           instead of the unattended Tue/Fri automation.

           This script only FETCHES data — it does not apply any AI
           judgment and does not write anything. The classification
           (which terms are irrelevant, which recurring tokens deserve a
           broad-match negative) is done by Claude reading this output
           against the client's own client-brief.md, exactly as the
           scheduled automation's prompt does — then presented to the
           user for explicit confirmation before anything is written.
           Actually adding negatives is a separate step: see
           add_shared_negatives.py, called only after that confirmation.

           If a client has no negative_list_id configured yet, `fetch`
           won't guess — it looks up whatever shared negative-keyword
           lists already exist on the account and prints them so the
           user can pick one (`set-list`), or asks whether to create a
           new one (`create-list`). Both write choices are surfaced for
           explicit confirmation, same convention as the rest of this
           flow — this script never picks a list on its own.

           This is the backing script for /keyword-audit.

Usage    : python3 negative_keyword_audit.py fetch <client_slug> [--days 4]
           python3 negative_keyword_audit.py list-lists <client_slug>
           python3 negative_keyword_audit.py create-list <client_slug> --name "..." [--attach-all]
           python3 negative_keyword_audit.py set-list <client_slug> --id <shared_set_id>
Changelog: 2026-07-26  Initial version
           2026-07-26  Added list-lists/create-list/set-list so a missing
                       negative_list_id no longer just dead-ends the audit.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve, reload as reload_clients, save_clients  # noqa: E402
from change_log import log_change, new_run_id  # noqa: E402

from google.ads.googleads.client import GoogleAdsClient

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def fetch_search_terms(customer_id, days, sort_by="cost", top=None):
    client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = client.get_service("GoogleAdsService")
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)
    order_column = "metrics.impressions" if sort_by == "impressions" else "metrics.cost_micros"
    query = f"""
        SELECT search_term_view.search_term, metrics.impressions, metrics.clicks,
               metrics.cost_micros, metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}' AND metrics.impressions >= 1
        ORDER BY {order_column} DESC
        LIMIT 2000
    """
    rows = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        rows.append({
            "term": row.search_term_view.search_term,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": round(row.metrics.cost_micros / 1_000_000, 2),
            "conversions": row.metrics.conversions,
        })
    total_found = len(rows)
    if top:
        rows = rows[:top]
    return rows, date_from, date_to, total_found


def find_negative_lists(ads_client, customer_id):
    """All ENABLED shared negative-keyword lists on this account, with how many
    keywords and campaigns are already attached — so a human can tell them apart
    without opening the UI."""
    ga_service = ads_client.get_service("GoogleAdsService")
    query = """
        SELECT shared_set.id, shared_set.name, shared_set.member_count,
               shared_set.reference_count
        FROM shared_set
        WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND shared_set.status = 'ENABLED'
        ORDER BY shared_set.name
    """
    lists = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        lists.append({
            "id": str(row.shared_set.id),
            "name": row.shared_set.name,
            "member_count": row.shared_set.member_count,
            "reference_count": row.shared_set.reference_count,
        })
    return lists


def get_enabled_campaigns(ga_service, customer_id):
    query = """
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.status = 'ENABLED'
    """
    return [
        {"id": str(row.campaign.id), "name": row.campaign.name}
        for row in ga_service.search(customer_id=customer_id, query=query, timeout=60)
    ]


def persist_negative_list_id(slug, list_id):
    """Read-modify-write clients.json so the chosen/created list sticks around
    for future runs, instead of re-asking every time."""
    data = reload_clients()
    data[slug]["negative_list_id"] = list_id
    save_clients(data)


def print_available_lists(lists):
    print(f"\n=== EXISTING SHARED NEGATIVE-KEYWORD LISTS ({len(lists)}) ===")
    for lst in lists:
        print(f"  ID {lst['id']:<12} \"{lst['name']}\"  "
              f"({lst['member_count']} keywords, attached to {lst['reference_count']} campaigns)")


def cmd_fetch(args):
    client_meta = resolve(args.client)
    negative_list_id = client_meta.get("negative_list_id")

    if not negative_list_id:
        print(f"No negative_list_id configured for '{args.client}' in client_registry.py.")
        ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
        lists = find_negative_lists(ads_client, client_meta["customer_id"])
        if lists:
            print_available_lists(lists)
            print(f"\nPick one and run:")
            print(f"  python3 scripts/negative_keyword_audit.py set-list {args.client} --id <ID>")
            print(f"...or create a new one:")
            print(f"  python3 scripts/negative_keyword_audit.py create-list {args.client} --name \"...\"")
        else:
            print("\nNo existing shared negative-keyword lists found on this account.")
            print(f"Create one with:")
            print(f"  python3 scripts/negative_keyword_audit.py create-list {args.client} --name \"...\" --attach-all")
        sys.exit(3)

    brief_path = WORKSPACE_ROOT / "clients" / args.client / "client-brief.md"
    if not brief_path.exists():
        print(f"No client-brief.md found at {brief_path}")
        sys.exit(2)

    rows, date_from, date_to, total_found = fetch_search_terms(
        client_meta["customer_id"], args.days, sort_by=args.sort_by, top=args.top
    )

    print(f"Client            : {client_meta['name']} ({args.client})")
    print(f"Shared list       : {negative_list_id}")
    print(f"Period            : {date_from} -> {date_to} ({args.days} days)")
    if args.top and total_found > args.top:
        print(f"Search terms found: {total_found} (showing top {args.top} by {args.sort_by})")
    else:
        print(f"Search terms found: {total_found}")
    print()
    print("=== CLIENT BRIEF ===")
    print(brief_path.read_text())
    print()
    print("=== SEARCH TERMS (cost | impressions | conversions | term) ===")
    for r in rows:
        print(f"{r['cost']:.2f}|{r['impressions']}i|{r['conversions']:.0f}cv|{r['term']}")


def cmd_list_lists(args):
    client_meta = resolve(args.client)
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    lists = find_negative_lists(ads_client, client_meta["customer_id"])
    print(f"Client: {client_meta['name']} ({args.client})")
    if not lists:
        print("No existing shared negative-keyword lists found on this account.")
        sys.exit(1)
    print_available_lists(lists)
    current = client_meta.get("negative_list_id")
    if current:
        print(f"\nCurrently configured for this client: ID {current}")


def cmd_set_list(args):
    client_meta = resolve(args.client)
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    lists = find_negative_lists(ads_client, client_meta["customer_id"])
    match = next((l for l in lists if l["id"] == args.id), None)
    if not match:
        print(f"ERROR: no ENABLED shared negative-keyword list with ID {args.id} found on this account.")
        print_available_lists(lists)
        sys.exit(2)

    persist_negative_list_id(client_meta["slug"], args.id)
    print(f"Set negative_list_id = {args.id} (\"{match['name']}\") for '{args.client}' in clients.json.")


def cmd_create_list(args):
    client_meta = resolve(args.client)
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = ads_client.get_service("GoogleAdsService")
    customer_id = client_meta["customer_id"]
    run_id = new_run_id()

    name = args.name or f"{client_meta['name']} - Negative Keywords"

    shared_set_service = ads_client.get_service("SharedSetService")
    op = ads_client.get_type("SharedSetOperation")
    ss = op.create
    ss.name = name
    ss.type_ = ads_client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS

    resp = shared_set_service.mutate_shared_sets(customer_id=customer_id, operations=[op], timeout=60)
    new_resource = resp.results[0].resource_name
    new_id = new_resource.split("/")[-1]
    print(f"Created shared negative-keyword list: ID={new_id}, name=\"{name}\"")
    log_change(client_slug=args.client, script="negative_keyword_audit.py", action="create_shared_set",
               resource_type="shared_set", resource_id=new_id, detail=name, run_id=run_id)

    if args.attach_all:
        campaigns = get_enabled_campaigns(ga_service, customer_id)
        if not campaigns:
            print("WARNING: no ENABLED campaigns found — nothing to attach to.")
        else:
            css_service = ads_client.get_service("CampaignSharedSetService")
            attached = 0
            for camp in campaigns:
                css_op = ads_client.get_type("CampaignSharedSetOperation")
                css = css_op.create
                css.campaign = f"customers/{customer_id}/campaigns/{camp['id']}"
                css.shared_set = new_resource
                try:
                    css_service.mutate_campaign_shared_sets(customer_id=customer_id, operations=[css_op], timeout=60)
                    attached += 1
                    print(f"  Attached to: {camp['name']} (ID: {camp['id']})")
                    log_change(client_slug=args.client, script="negative_keyword_audit.py",
                               action="attach_shared_set", resource_type="campaign", resource_id=camp["id"],
                               detail=f"shared_set {new_id}", run_id=run_id)
                except Exception as e:
                    print(f"  FAILED to attach to {camp['name']} (ID: {camp['id']}) — {e}")
            print(f"Attached to {attached}/{len(campaigns)} enabled campaign(s).")
    else:
        print("Not attached to any campaign (pass --attach-all to attach to every ENABLED campaign).")

    persist_negative_list_id(client_meta["slug"], new_id)
    print(f"Set negative_list_id = {new_id} for '{args.client}' in clients.json.")


def main():
    parser = argparse.ArgumentParser(description="Fetch data for an interactive negative-keyword audit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Pull search terms + client brief for this client")
    p_fetch.add_argument("client")
    p_fetch.add_argument("--days", type=int, default=4)
    p_fetch.add_argument("--top", type=int, default=None,
                          help="Only fetch the top N search terms (by --sort-by) instead of all of them")
    p_fetch.add_argument("--sort-by", choices=["cost", "impressions"], default="cost",
                          help="Ranking used with --top (default: cost)")
    p_fetch.set_defaults(func=cmd_fetch)

    p_list = sub.add_parser("list-lists", help="Show existing shared negative-keyword lists on this client's account")
    p_list.add_argument("client")
    p_list.set_defaults(func=cmd_list_lists)

    p_set = sub.add_parser("set-list", help="Point this client at an existing shared negative-keyword list")
    p_set.add_argument("client")
    p_set.add_argument("--id", required=True, help="Shared set ID, as shown by list-lists")
    p_set.set_defaults(func=cmd_set_list)

    p_create = sub.add_parser("create-list", help="Create a new shared negative-keyword list for this client")
    p_create.add_argument("client")
    p_create.add_argument("--name", help="Defaults to '<client name> - Negative Keywords'")
    p_create.add_argument("--attach-all", action="store_true",
                           help="Attach the new list to every ENABLED campaign on the account")
    p_create.set_defaults(func=cmd_create_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
