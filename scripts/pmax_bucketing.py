#!/usr/bin/env python3
"""
PMax Product Segmentation (Bucketing) — any client
=============================================================
Purpose  : Segments a client's active Merchant Center feed into 4 performance
           tiers (Platinum/Gold/Silver/Bronze) using a Pareto/ABC-style cut on
           trailing conversion-value share, proposes a per-tier budget +
           target ROAS, and (only after explicit approval) creates one new
           "feed only" PMax campaign per qualifying tier — so top performers
           aren't diluted by weak products sharing one campaign's Smart
           Bidding signal.

           Generalised (2026-07-25) from a single-client-only script into a shared,
           per-client tool driven by client_registry.py instead of hardcoded
           constants — same fetch/analyse/apply logic. Requires "customer_id"
           (always present) in client_registry.py; merchant_id and feed_label
           are read directly from the client's own enabled PMax campaigns, not
           from the registry, so no extra per-client setup is needed beyond
           having at least one enabled PMax campaign with a Merchant Center
           feed attached.

           Tiering rule (products sorted revenue-descending, by cumulative
           share of trailing revenue):
             Platinum : cumulative share <= 50%
             Gold     : cumulative share 50-80%
             Silver   : cumulative share 80-100% (must have revenue > 0)
             Bronze   : zero revenue in the window — no campaign proposed;
                        these products are recommended for EXCLUSION from
                        spend, not a new campaign (see `check` output)

           Two-step by design, same pattern as keyword_expansion.py:
             `check` is read-only — pulls performance, buckets products,
                      prints the proposal, and writes a plan JSON.
             `apply` only ever acts on an already-written plan JSON, and
                      only runs with --confirm. It creates campaigns in
                      PAUSED status (never auto-enables live spend) —
                      review and enable manually in the Ads UI after
                      checking the built campaign.

           New campaigns are created "feed only" style — no manual text/image
           creative is generated or cloned; the asset group is just a
           final_url and relies entirely on the Merchant Center feed for
           creative, matching how this toolkit expects PMax campaigns to
           already be structured.

           RE-RUNNING: by default, `apply` always creates brand-new campaigns and
           fails with DUPLICATE_CAMPAIGN_NAME if a tier's campaign already exists
           from a prior run (use --suffix for a genuinely separate parallel
           structure instead). Pass --sync to move products in place instead: for
           any tier whose campaign already exists (matched by the same
           deterministic name create_campaign() uses), --sync reads its current
           listing-group-filter product assignment, diffs it against the latest
           plan, and adds/moves/removes only the product filters that changed —
           it never touches that campaign's budget or target ROAS, and never
           creates a duplicate. Tiers with no existing campaign still go through
           the normal create path. --sync cannot be combined with --only, since a
           move touches both the source and destination tier's asset group in one
           pass. Both the dry run (no --confirm) and the live run compute the same
           diff, so the preview is exact.

Usage    : python3 pmax_bucketing.py <client_slug> check [--days 90] [--out plan.json]
           python3 pmax_bucketing.py <client_slug> apply --plan plan.json --confirm [--include-bronze]
           python3 pmax_bucketing.py <client_slug> apply --plan plan.json --confirm --sync   # re-bucket in place
Changelog: 2026-07-23  Initial version (single-client-only, check step)
           2026-07-23  Add apply step (creates PAUSED campaigns, requires --confirm)
           2026-07-25  Generalised to any client via client_registry.py;
                       wired into the shared change_log
           2026-07-27  Add --sync: move products between existing tier campaigns'
                       listing-group-filters on a re-run instead of always creating
                       new (duplicate) campaigns
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
GOOGLE_ADS_YAML = WORKSPACE_ROOT / "google-ads.yaml"
SHOPPING_SRC = 2  # ListingGroupFilterListingSource.SHOPPING
TIER_ORDER = ["Platinum", "Gold", "Silver", "Bronze"]

sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))
from client_registry import resolve  # noqa: E402
from change_log import log_change, new_run_id  # noqa: E402


def load_client(slug: str) -> dict:
    try:
        client = resolve(slug)
    except KeyError as e:
        sys.exit(str(e))
    if not client.get("customer_id"):
        sys.exit(f"ERROR: client_registry.py entry for '{slug}' has no 'customer_id'.")
    if "final_url" not in client:
        domain = client["domain"].strip()
        if not re.match(r"^https?://", domain):
            domain = f"https://{domain}"
        if not domain.endswith("/"):
            domain += "/"
        client["final_url"] = domain
    client.setdefault("currency", "")
    return client


# ─── shared data pulls ────────────────────────────────────────────────────────

def get_pmax_campaigns(ga_service, customer_id):
    campaigns = []
    for r in ga_service.search(customer_id=customer_id, query="""
        SELECT campaign.id, campaign.name, campaign_budget.amount_micros,
               campaign.shopping_setting.merchant_id, campaign.shopping_setting.feed_label
        FROM campaign
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX' AND campaign.status = 'ENABLED'
    """, timeout=60):
        campaigns.append({
            "id": str(r.campaign.id),
            "name": r.campaign.name,
            "budget_per_day": r.campaign_budget.amount_micros / 1_000_000,
            "merchant_id": r.campaign.shopping_setting.merchant_id,
            "feed_label": r.campaign.shopping_setting.feed_label,
        })
    return campaigns


def get_active_products(ga_service, customer_id):
    active = {}
    for r in ga_service.search(customer_id=customer_id, query="""
        SELECT shopping_product.item_id, shopping_product.title, shopping_product.status
        FROM shopping_product
    """, timeout=120):
        if r.shopping_product.status.name == "ELIGIBLE":
            active[r.shopping_product.item_id] = r.shopping_product.title
    return active


def get_product_performance(ga_service, customer_id, campaign_ids, date_from, date_to):
    ids_str = ", ".join(campaign_ids)
    agg = defaultdict(lambda: {"item_id": "", "title": "", "cost": 0.0,
                                "conversions": 0.0, "revenue": 0.0,
                                "impressions": 0, "clicks": 0})
    for r in ga_service.search(customer_id=customer_id, query=f"""
        SELECT campaign.id, segments.product_item_id, segments.product_title,
               metrics.cost_micros, metrics.conversions, metrics.conversions_value,
               metrics.impressions, metrics.clicks
        FROM shopping_performance_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
          AND campaign.id IN ({ids_str})
        LIMIT 5000
    """, timeout=120):
        iid = r.segments.product_item_id
        if not iid:
            continue
        p = agg[iid]
        p["item_id"] = iid
        p["title"] = p["title"] or r.segments.product_title
        p["cost"] += r.metrics.cost_micros / 1_000_000
        p["conversions"] += r.metrics.conversions
        p["revenue"] += r.metrics.conversions_value
        p["impressions"] += r.metrics.impressions
        p["clicks"] += r.metrics.clicks
    return agg


def bucket_products(products):
    for p in products:
        p["roas"] = (p["revenue"] / p["cost"] * 100) if p["cost"] > 0 else 0.0
    products.sort(key=lambda p: p["revenue"], reverse=True)
    total_rev = sum(p["revenue"] for p in products) or 1.0

    cum = 0.0
    for p in products:
        cum += p["revenue"]
        p["cum_share"] = cum / total_rev
        if p["revenue"] <= 0:
            p["tier"] = "Bronze"
        elif p["cum_share"] <= 0.5:
            p["tier"] = "Platinum"
        elif p["cum_share"] <= 0.8:
            p["tier"] = "Gold"
        else:
            p["tier"] = "Silver"
    return products


def propose_budgets(buckets, days):
    proposals = {}
    for tier in ("Platinum", "Gold", "Silver"):
        b = buckets[tier]
        cost = sum(p["cost"] for p in b)
        rev = sum(p["revenue"] for p in b)
        roas = (rev / cost * 100) if cost else 0
        realized_daily = cost / days
        if tier in ("Platinum", "Gold"):
            budget = realized_daily * 1.25
        else:  # Silver
            budget = realized_daily * 1.1
        troas = max(round(roas * 0.9 / 10) * 10, 100)
        proposals[tier] = {
            "products": len(b), "cost": cost, "revenue": rev, "roas": roas,
            "realized_daily": realized_daily, "proposed_daily_budget": round(budget, 2),
            "proposed_troas": troas,
            "item_ids": [p["item_id"] for p in b],
        }

    # Bronze: split genuinely untested (zero-spend) SKUs from proven-wasteful ones
    # (spent money, zero return). Only the untested subset is ever eligible for a
    # campaign (--include-bronze) — the wasteful subset is a spend-exclusion
    # recommendation, never a campaign proposal.
    bronze = buckets["Bronze"]
    untested = [p for p in bronze if p["cost"] == 0]
    wasteful = [p for p in bronze if p["cost"] > 0]
    wasteful_cost = sum(p["cost"] for p in wasteful)
    bronze_realized_daily = wasteful_cost / days

    blended_cost = sum(proposals[t]["cost"] for t in ("Platinum", "Gold", "Silver"))
    blended_rev = sum(proposals[t]["revenue"] for t in ("Platinum", "Gold", "Silver"))
    blended_troas = round(blended_rev / blended_cost * 100) if blended_cost else None

    proposals["Bronze"] = {
        "products": len(bronze), "cost": wasteful_cost, "revenue": 0.0, "roas": 0.0,
        "realized_daily": bronze_realized_daily,
        "proposed_daily_budget": round(min(30.0, bronze_realized_daily * 0.3), 2) if untested else 0.0,
        # Blended Platinum/Gold/Silver ROAS used as a placeholder target — these SKUs
        # have zero history of their own, so there's no real ROAS to base a target on.
        "proposed_troas": blended_troas if untested else None,
        "item_ids": [p["item_id"] for p in untested],
        "untested_count": len(untested),
        "wasteful_count": len(wasteful),
        "wasteful_cost": wasteful_cost,
    }
    return proposals


# ─── check ────────────────────────────────────────────────────────────────────

def cmd_check(client, args):
    from google.ads.googleads.client import GoogleAdsClient
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = ads_client.get_service("GoogleAdsService")
    customer_id = client["customer_id"]
    currency = f" {client['currency']}" if client["currency"] else ""

    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    print(f"{client['name']} — PMax Product Bucketing — CHECK (read-only, no account changes)")
    print(f"Period: {date_from} -> {date_to} ({args.days} days)")
    print("=" * 70)

    campaigns = get_pmax_campaigns(ga_service, customer_id)
    if not campaigns:
        sys.exit(f"No ENABLED PMax campaigns found for '{client['slug']}' — nothing to bucket.")
    campaign_ids = [c["id"] for c in campaigns]
    merchant_id = campaigns[0]["merchant_id"]
    feed_label = campaigns[0]["feed_label"]

    print(f"\nEnabled PMax campaigns ({len(campaigns)}), current nominal budgets:")
    total_nominal = 0.0
    for c in campaigns:
        print(f"  {c['name']:<55} {c['budget_per_day']:>8,.0f}{currency}/day")
        total_nominal += c["budget_per_day"]
    print(f"  {'TOTAL (nominal caps)':<55} {total_nominal:>8,.0f}{currency}/day")

    active_products = get_active_products(ga_service, customer_id)
    if not active_products:
        sys.exit(f"No ELIGIBLE Merchant Center products found for '{client['slug']}' — nothing to bucket.")
    perf = get_product_performance(ga_service, customer_id, campaign_ids, date_from, date_to)
    for iid, title in active_products.items():
        if iid not in perf:
            perf[iid] = {"item_id": iid, "title": title, "cost": 0.0,
                         "conversions": 0.0, "revenue": 0.0, "impressions": 0, "clicks": 0}
    products = [p for p in perf.values() if p["item_id"] in active_products]
    products = bucket_products(products)

    total_rev = sum(p["revenue"] for p in products)
    total_cost = sum(p["cost"] for p in products)
    print(f"\nActive feed products bucketed: {len(products)}")
    print(f"Realized {args.days}d revenue: {total_rev:,.0f}{currency} | cost: {total_cost:,.0f}{currency} | "
          f"blended ROAS: {(total_rev/total_cost*100) if total_cost else 0:.0f}%")
    print(f"Realized avg daily spend: {total_cost/args.days:,.0f}{currency}/day "
          f"(vs {total_nominal:,.0f}{currency}/day nominal budget caps — Target ROAS strategies "
          f"commonly underspend the cap, this gap is expected, not an error)")

    buckets = defaultdict(list)
    for p in products:
        buckets[p["tier"]].append(p)

    print(f"\n{'Tier':<10} {'#SKUs':<7} {'Revenue':>10} {'Cost':>10} {'ROAS':>7} {'Conv':>7}")
    print("-" * 55)
    for tier in TIER_ORDER:
        b = buckets[tier]
        rev = sum(p["revenue"] for p in b)
        cost = sum(p["cost"] for p in b)
        conv = sum(p["conversions"] for p in b)
        roas = (rev / cost * 100) if cost else 0
        print(f"{tier:<10} {len(b):<7} {rev:>10,.0f} {cost:>10,.0f} {roas:>6.0f}% {conv:>7.1f}")

    zero_spend = [p for p in buckets["Bronze"] if p["cost"] == 0]
    spend_no_rev = [p for p in buckets["Bronze"] if p["cost"] > 0]
    print(f"\nBronze breakdown: {len(zero_spend)} untested (zero spend), "
          f"{len(spend_no_rev)} spent with zero return "
          f"(wasted {sum(p['cost'] for p in spend_no_rev):,.0f}{currency} over {args.days}d)")

    print(f"\n{'=' * 70}\nPROPOSED CAMPAIGN STRUCTURE\n{'=' * 70}")
    proposals = propose_budgets(buckets, args.days)
    for tier in TIER_ORDER:
        pr = proposals[tier]
        if tier == "Bronze":
            troas_str = (f"{pr['proposed_troas']:.0f}% (blended P/G/S ROAS — placeholder, "
                         f"these {pr['untested_count']} SKUs have no history of their own)"
                         if pr["proposed_troas"] else "n/a (no untested SKUs to test)")
            print(f"\n{tier} ({pr['untested_count']} untested SKUs eligible for a test campaign, "
                  f"{pr['wasteful_count']} proven-wasteful SKUs excluded from spend, "
                  f"{pr['wasteful_cost']:,.0f}{currency} wasted over {args.days}d)")
        else:
            troas_str = f"{pr['proposed_troas']:.0f}%"
            print(f"\n{tier} ({pr['products']} SKUs) — realized {pr['roas']:.0f}% ROAS, "
                  f"{pr['realized_daily']:.0f}{currency}/day actual spend")
        print(f"  Proposed budget : {pr['proposed_daily_budget']:.0f}{currency}/day")
        print(f"  Proposed tROAS  : {troas_str}")

    print("\n--- Sample SKUs per tier ---")
    for tier in ["Platinum", "Gold"]:
        print(f"\n{tier}:")
        for p in buckets[tier]:
            print(f"  [{p['item_id']}] rev={p['revenue']:,.0f} cost={p['cost']:,.0f} "
                  f"roas={p['roas']:.0f}% conv={p['conversions']:.1f}  {p['title'][:55]}")

    plan = {
        "client_slug": client["slug"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": args.days,
        "merchant_id": merchant_id,
        "feed_label": feed_label,
        "final_url": client["final_url"],
        "tiers": proposals,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== Check complete — READ ONLY, no campaigns/budgets/filters were created or modified ===")
    print(f"Plan written to: {out_path}")
    print(f"Review it, then run: python3 {Path(__file__).name} {client['slug']} apply --plan {out_path} --confirm")


# ─── apply ────────────────────────────────────────────────────────────────────

def create_campaign(ads_client, customer_id, budget_svc, campaign_svc, tier, pr, merchant_id, feed_label, suffix=""):
    budget_op = ads_client.get_type("CampaignBudgetOperation")
    budget = budget_op.create
    budget.name = f"Budget — pm max - bucketing - {tier.lower()}{suffix} — {datetime.now().strftime('%Y%m%d%H%M%S')}"
    budget.amount_micros = int(pr["proposed_daily_budget"] * 1_000_000)
    budget.delivery_method = ads_client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False
    budget_resp = budget_svc.mutate_campaign_budgets(customer_id=customer_id, operations=[budget_op])
    budget_rn = budget_resp.results[0].resource_name

    campaign_op = ads_client.get_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = f"pm max - feed only - {tier.lower()} - bucketing{suffix}"
    campaign.advertising_channel_type = ads_client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    campaign.status = ads_client.enums.CampaignStatusEnum.PAUSED  # always paused — review before enabling
    campaign.contains_eu_political_advertising = ads_client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    campaign.campaign_budget = budget_rn
    campaign.maximize_conversion_value.target_roas = pr["proposed_troas"] / 100.0
    campaign.shopping_setting.merchant_id = merchant_id
    campaign.shopping_setting.feed_label = feed_label
    campaign_resp = campaign_svc.mutate_campaigns(customer_id=customer_id, operations=[campaign_op])
    return campaign_resp.results[0].resource_name


def create_asset_group(ads_client, customer_id, ag_svc, campaign_rn, tier, final_url):
    op = ads_client.get_type("AssetGroupOperation")
    ag = op.create
    ag.name = f"{tier.lower()} feed only"
    ag.campaign = campaign_rn
    ag.final_urls.append(final_url)
    ag.status = ads_client.enums.AssetGroupStatusEnum.PAUSED
    resp = ag_svc.mutate_asset_groups(customer_id=customer_id, operations=[op])
    return resp.results[0].resource_name


def create_listing_group_filters(ads_client, customer_id, lf_svc, asset_group_rn, item_ids):
    """Root SUBDIVISION + one UNIT_INCLUDED per item_id + one catch-all UNIT_EXCLUDED —
    the standard structure Google's own PMax "feed only" campaigns use."""
    ops = []

    asset_group_id = asset_group_rn.rsplit("/", 1)[-1]

    root_op = ads_client.get_type("AssetGroupListingGroupFilterOperation")
    root = root_op.create
    root.asset_group = asset_group_rn
    root.type_ = ads_client.enums.ListingGroupFilterTypeEnum.SUBDIVISION
    root.listing_source = SHOPPING_SRC
    root_temp_rn = f"customers/{customer_id}/assetGroupListingGroupFilters/{asset_group_id}~-1"
    root.resource_name = root_temp_rn
    ops.append(root_op)

    for i, item_id in enumerate(item_ids, start=2):
        op = ads_client.get_type("AssetGroupListingGroupFilterOperation")
        f = op.create
        f.asset_group = asset_group_rn
        f.parent_listing_group_filter = root_temp_rn
        f.type_ = ads_client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED
        f.listing_source = SHOPPING_SRC
        f.case_value.product_item_id.value = item_id
        ops.append(op)

    catchall_op = ads_client.get_type("AssetGroupListingGroupFilterOperation")
    catchall = catchall_op.create
    catchall.asset_group = asset_group_rn
    catchall.parent_listing_group_filter = root_temp_rn
    catchall.type_ = ads_client.enums.ListingGroupFilterTypeEnum.UNIT_EXCLUDED
    catchall.listing_source = SHOPPING_SRC
    catchall.case_value.product_item_id.value = ""  # touch case_value so it's present on the wire — required even for the "everything else" node
    ops.append(catchall_op)

    lf_svc.mutate_asset_group_listing_group_filters(customer_id=customer_id, operations=ops, timeout=90)
    return len(item_ids)


# ─── sync (move products within an already-existing tier structure) ──────────

def find_existing_tier_campaigns(ga_service, customer_id, tiers, suffix):
    """Looks up, by the exact deterministic name create_campaign() uses, which of these tiers
    already has a PMax campaign (any non-removed status — it may or may not have been enabled
    since a prior run). Returns {tier: campaign_resource_name} for tiers that already exist."""
    if not tiers:
        return {}
    names = {f"pm max - feed only - {t.lower()} - bucketing{suffix}": t for t in tiers}
    quoted = ", ".join(f"'{n}'" for n in names)
    result = {}
    for r in ga_service.search(customer_id=customer_id, query=f"""
        SELECT campaign.resource_name, campaign.name
        FROM campaign
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
          AND campaign.status != 'REMOVED'
          AND campaign.name IN ({quoted})
    """, timeout=60):
        tier = names.get(r.campaign.name)
        if tier:
            result[tier] = r.campaign.resource_name
    return result


def find_tier_asset_groups(ga_service, customer_id, tier_campaign_rns):
    """{tier: campaign_resource_name} -> {tier: asset_group_resource_name}, preferring the
    '{tier} feed only' asset group create_asset_group() names (falls back to the first one found,
    in case it was renamed by hand in the UI)."""
    if not tier_campaign_rns:
        return {}
    rn_to_tier = {rn: t for t, rn in tier_campaign_rns.items()}
    quoted = ", ".join(f"'{rn}'" for rn in tier_campaign_rns.values())
    by_campaign = defaultdict(list)
    for r in ga_service.search(customer_id=customer_id, query=f"""
        SELECT asset_group.resource_name, asset_group.name, asset_group.campaign
        FROM asset_group
        WHERE asset_group.campaign IN ({quoted})
    """, timeout=60):
        by_campaign[r.asset_group.campaign].append((r.asset_group.resource_name, r.asset_group.name))

    result = {}
    for campaign_rn, groups in by_campaign.items():
        tier = rn_to_tier[campaign_rn]
        preferred = next((rn for rn, name in groups if name == f"{tier.lower()} feed only"), None)
        result[tier] = preferred or groups[0][0]
    return result


def fetch_existing_filters(ga_service, customer_id, tier_asset_groups):
    """{tier: asset_group_resource_name} -> (roots, current_assignment):
      roots[asset_group_rn]           = resource_name of that asset group's root SUBDIVISION node
      current_assignment[item_id]     = {"tier", "filter_rn", "asset_group_rn"} for every
                                         UNIT_INCLUDED leaf found across these asset groups
    """
    ag_to_tier = {ag: t for t, ag in tier_asset_groups.items()}
    if not ag_to_tier:
        return {}, {}
    quoted = ", ".join(f"'{ag}'" for ag in ag_to_tier)
    roots = {}
    current_assignment = {}
    for r in ga_service.search(customer_id=customer_id, query=f"""
        SELECT asset_group_listing_group_filter.resource_name,
               asset_group_listing_group_filter.type,
               asset_group_listing_group_filter.case_value.product_item_id.value,
               asset_group_listing_group_filter.asset_group
        FROM asset_group_listing_group_filter
        WHERE asset_group_listing_group_filter.asset_group IN ({quoted})
    """, timeout=90):
        f = r.asset_group_listing_group_filter
        ag_rn = f.asset_group
        tier = ag_to_tier.get(ag_rn)
        if f.type_.name == "SUBDIVISION":
            roots[ag_rn] = f.resource_name
        elif f.type_.name == "UNIT_INCLUDED":
            item_id = f.case_value.product_item_id.value
            if item_id:
                current_assignment[item_id] = {"tier": tier, "filter_rn": f.resource_name, "asset_group_rn": ag_rn}
    return roots, current_assignment


def compute_sync_diff(current_assignment, tier_asset_groups, desired_all):
    """Pure diff, no API calls — safe to run in a dry run for an accurate preview.
    tier_asset_groups here must only contain tiers that ALREADY existed before this apply run;
    tiers being freshly created in this same run are seeded directly by create_listing_group_filters
    and must not appear here, or their items would get double-added.
    Returns (remove_ops_data: [filter_rn, ...], create_ops_data: [(asset_group_rn, item_id), ...], counts)."""
    remove_ops_data = []
    create_ops_data = []
    counts = defaultdict(lambda: {"added": 0, "moved_in": 0, "moved_out": 0, "removed": 0})

    for item_id, info in current_assignment.items():
        cur_tier = info["tier"]
        target_tier = desired_all.get(item_id)
        if target_tier == cur_tier:
            continue  # already in the right place
        remove_ops_data.append(info["filter_rn"])
        if target_tier:
            counts[cur_tier]["moved_out"] += 1
        else:
            counts[cur_tier]["removed"] += 1  # no longer qualifies for any in-scope tier
        if target_tier and target_tier in tier_asset_groups:
            create_ops_data.append((tier_asset_groups[target_tier], item_id))
            counts[target_tier]["moved_in"] += 1
        # else: target tier is being freshly created this run — create_listing_group_filters
        # already seeds it with the full desired set, nothing more to do here for that side.

    for item_id, target_tier in desired_all.items():
        if item_id in current_assignment:
            continue  # handled above
        if target_tier in tier_asset_groups:
            create_ops_data.append((tier_asset_groups[target_tier], item_id))
            counts[target_tier]["added"] += 1

    return remove_ops_data, create_ops_data, dict(counts)


def execute_sync_diff(ads_client, customer_id, lf_svc, remove_ops_data, create_ops_data, roots):
    """Batches every remove+create from one compute_sync_diff() pass into a single mutate call —
    succeeds or fails atomically together, same preference as create_listing_group_filters."""
    ops = []
    for filter_rn in remove_ops_data:
        op = ads_client.get_type("AssetGroupListingGroupFilterOperation")
        op.remove = filter_rn
        ops.append(op)
    for ag_rn, item_id in create_ops_data:
        op = ads_client.get_type("AssetGroupListingGroupFilterOperation")
        f = op.create
        f.asset_group = ag_rn
        f.parent_listing_group_filter = roots[ag_rn]
        f.type_ = ads_client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED
        f.listing_source = SHOPPING_SRC
        f.case_value.product_item_id.value = item_id
        ops.append(op)
    if ops:
        lf_svc.mutate_asset_group_listing_group_filters(customer_id=customer_id, operations=ops, timeout=90)
    return len(ops)


def cmd_apply(client, args):
    if args.sync and args.only:
        sys.exit("ERROR: --sync and --only cannot be combined — a move touches both the source and "
                  "destination tier's asset group in one pass, so restricting to a single tier could "
                  "remove a product without re-adding it anywhere. Run --sync without --only.")

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))

    tiers_in_scope = [t for t in TIER_ORDER if t != "Bronze" or args.include_bronze]
    if args.only:
        tiers_in_scope = [t for t in tiers_in_scope if t == args.only]

    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = ads_client.get_service("GoogleAdsService")
    customer_id = client["customer_id"]
    lf_svc = ads_client.get_service("AssetGroupListingGroupFilterService")

    # --sync: figure out, read-only, which in-scope tiers already have a campaign, and what moving
    # every product to its latest plan tier would require. Safe to compute even without --confirm —
    # it's the accurate preview for the dry run below. Tiers with no existing campaign fall through
    # to today's create path unchanged (tiers_needing_create).
    existing_asset_groups, roots, sync_counts = {}, {}, {}
    remove_ops_data, create_ops_data = [], []
    tiers_needing_create = tiers_in_scope
    existing_campaigns = {}
    if args.sync:
        existing_campaigns = find_existing_tier_campaigns(ga_service, customer_id, tiers_in_scope, args.suffix)
        existing_asset_groups = find_tier_asset_groups(ga_service, customer_id, existing_campaigns)
        roots, current_assignment = fetch_existing_filters(ga_service, customer_id, existing_asset_groups)

        desired_all = {}
        for tier in tiers_in_scope:
            for item_id in plan["tiers"][tier]["item_ids"]:
                desired_all[item_id] = tier

        remove_ops_data, create_ops_data, sync_counts = compute_sync_diff(
            current_assignment, existing_asset_groups, desired_all)
        tiers_needing_create = [t for t in tiers_in_scope if t not in existing_asset_groups]

    if not args.confirm:
        print("DRY RUN — refusing to create/change anything without --confirm. Review the plan file first:")
        print(f"  {args.plan}")
        for tier in tiers_in_scope:
            pr = plan["tiers"][tier]
            if tier in existing_asset_groups:
                c = sync_counts.get(tier, {"added": 0, "moved_in": 0, "moved_out": 0, "removed": 0})
                print(f"  [would sync] {tier} -> existing campaign ({existing_campaigns[tier]}): "
                      f"+{c['added']} added, {c['moved_in']} moved in, {c['moved_out']} moved out, "
                      f"{c['removed']} removed")
            elif pr["item_ids"] and pr["proposed_troas"] is not None:
                print(f"  [would create] pm max - feed only - {tier.lower()} - bucketing{args.suffix} "
                      f"({pr['products']} SKUs, {pr['proposed_daily_budget']:.0f}/day, tROAS {pr['proposed_troas']:.0f}%)")
        print("\nRe-run with --confirm once you've reviewed it.")
        return

    budget_svc = ads_client.get_service("CampaignBudgetService")
    campaign_svc = ads_client.get_service("CampaignService")
    ag_svc = ads_client.get_service("AssetGroupService")
    run_id = new_run_id()

    print(f"{client['name']} — PMax Bucketing — APPLY")
    print(f"Plan: {args.plan} (generated {plan['generated_at']})")
    print("New campaigns are created PAUSED — review and enable manually in the Ads UI.")
    print("=" * 70)

    created = []
    skipped_tiers = []
    for tier in tiers_needing_create:
        pr = plan["tiers"][tier]
        if not pr["item_ids"] or pr["proposed_troas"] is None:
            print(f"\n{tier}: skipped — no tROAS proposed / no items (see plan file)")
            continue

        print(f"\n── {tier} ({pr['products']} SKUs, {pr['proposed_daily_budget']:.0f}/day, "
              f"tROAS {pr['proposed_troas']:.0f}%) ──")

        campaign_rn = None
        try:
            campaign_rn = create_campaign(ads_client, customer_id, budget_svc, campaign_svc, tier, pr,
                                           plan["merchant_id"], plan["feed_label"], suffix=args.suffix)
            print(f"  Created campaign (PAUSED): {campaign_rn}")

            asset_group_rn = create_asset_group(ads_client, customer_id, ag_svc, campaign_rn, tier, plan["final_url"])
            print(f"  Created asset group: {asset_group_rn}")

            n = create_listing_group_filters(ads_client, customer_id, lf_svc, asset_group_rn, pr["item_ids"])
            print(f"  Added {n} product filters + 1 catch-all exclusion")

            log_change(client_slug=client["slug"], script="pmax_bucketing.py", action="create_campaign",
                       resource_type="campaign", resource_id=campaign_rn,
                       detail=f"{tier}: {n} SKUs, {pr['proposed_daily_budget']:.0f}/day, tROAS {pr['proposed_troas']:.0f}%",
                       run_id=run_id)

            created.append({"tier": tier, "campaign": campaign_rn, "asset_group": asset_group_rn,
                            "products": n})
        except GoogleAdsException as e:
            gerror = e.failure.errors[0] if e.failure.errors else None
            code_field = gerror.error_code._pb.WhichOneof("error_code") if gerror else None
            code_name = getattr(gerror.error_code, code_field).name if code_field else None
            message = gerror.message if gerror else str(e)

            print(f"  FAILED: {message}")
            if code_field == "campaign_error" and code_name == "DUPLICATE_CAMPAIGN_NAME":
                print(f"  Hint: a campaign named 'pm max - feed only - {tier.lower()} - bucketing{args.suffix}' "
                      f"already exists (active or paused). Re-run with --sync to move products into it "
                      f"instead, or a distinct --suffix (e.g. ' - v2', ' - v3') to avoid the collision.")
            elif code_field in ("url_field_error", "asset_group_error"):
                print(f"  Hint: check clients.json's 'domain' field for '{client['slug']}' against the "
                      f"actual Merchant Center home page URL — final_url and the feed's domain must match.")

            if campaign_rn:
                print(f"  Rolling back partially-created campaign {campaign_rn} (no asset group/filters were attached)...")
                try:
                    remove_op = ads_client.get_type("CampaignOperation")
                    remove_op.remove = campaign_rn
                    campaign_svc.mutate_campaigns(customer_id=customer_id, operations=[remove_op])
                    print(f"  Removed {campaign_rn} — no orphan left behind.")
                except GoogleAdsException as cleanup_err:
                    print(f"  WARNING: automatic rollback failed too — remove {campaign_rn} manually. ({cleanup_err})")

            # Same root cause (bad final_url / naming collision) applies identically to
            # every remaining tier — stop here instead of repeating the same failure.
            remaining = tiers_needing_create[tiers_needing_create.index(tier) + 1:]
            skipped_tiers.append(tier)
            skipped_tiers.extend(remaining)
            break

    if args.sync:
        print(f"\n{'─' * 70}\nSYNC — moving products within existing tier campaigns\n{'─' * 70}")
        if remove_ops_data or create_ops_data:
            execute_sync_diff(ads_client, customer_id, lf_svc, remove_ops_data, create_ops_data, roots)
            for tier, c in sync_counts.items():
                if not any(c.values()):
                    continue
                print(f"  {tier}: +{c['added']} added, {c['moved_in']} moved in, "
                      f"{c['moved_out']} moved out, {c['removed']} removed")
                log_change(client_slug=client["slug"], script="pmax_bucketing.py", action="sync_products",
                           resource_type="asset_group", resource_id=existing_asset_groups.get(tier, ""),
                           detail=f"{tier}: +{c['added']} added, {c['moved_in']} moved in, "
                                  f"{c['moved_out']} moved out, {c['removed']} removed",
                           run_id=run_id)
        else:
            print("  No product movement needed — existing tier campaigns already match the latest plan.")

    if tiers_needing_create:
        print(f"\n{'=' * 70}")
        print(f"Created {len(created)} campaign(s), all PAUSED. Review in the Ads UI before enabling.")
        for c in created:
            print(f"  {c['tier']}: {c['campaign']}")
        if skipped_tiers:
            print(f"\nNot attempted due to the failure above: {', '.join(skipped_tiers)}")
            print(f"Fix the issue, then re-run with --only <tier> for each, or --suffix to change the name.")

    if not args.include_bronze:
        bronze = plan["tiers"]["Bronze"]
        print(f"\nBronze ({bronze['products']} SKUs) was NOT created as a campaign. "
              f"Recommend excluding the proven-wasteful ones from the feed/existing campaigns "
              f"instead of running a new campaign for them — see the check output for the full list.")


def main():
    parser = argparse.ArgumentParser(description="PMax product bucketing — any client")
    parser.add_argument("client", help="Client slug from client_registry.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Read-only analysis, writes a plan JSON")
    p_check.add_argument("--days", type=int, default=90)
    p_check.add_argument("--out", default="pmax_bucketing_plan.json")
    p_check.set_defaults(func=cmd_check)

    p_apply = sub.add_parser("apply", help="Create PAUSED campaigns from an approved plan JSON")
    p_apply.add_argument("--plan", required=True)
    p_apply.add_argument("--confirm", action="store_true",
                          help="Actually create campaigns. Without this, dry-run only.")
    p_apply.add_argument("--include-bronze", action="store_true",
                          help="Also create a minimal test campaign for Bronze's untested SKUs")
    p_apply.add_argument("--sync", action="store_true",
                          help="For any tier whose campaign already exists (matched by name), move "
                               "products into/out of its listing-group-filters to match the latest "
                               "plan instead of creating a duplicate campaign. Filters only — never "
                               "touches an existing campaign's budget or target ROAS. Cannot be "
                               "combined with --only.")
    p_apply.add_argument("--suffix", default="",
                          help="Appended to each campaign/budget name (e.g. ' - v2') to avoid "
                               "DUPLICATE_CAMPAIGN_NAME collisions with an existing bucketing run")
    p_apply.add_argument("--only", choices=TIER_ORDER,
                          help="Create only this tier — useful when resuming a run where some "
                               "tiers were already created successfully")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    client = load_client(args.client)
    args.func(client, args)


if __name__ == "__main__":
    main()
