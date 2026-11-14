#!/usr/bin/env python3
"""
55DigitalAI — GA4 Campaign Analyst (Per-Campaign Deep Dive)
=============================================================
Purpose  : Eight ready-made analyses for a single Google Ads campaign,
           cross-referencing Ads cost/conversion data with GA4 behavioral
           data — so you see not just whether a campaign converts, but
           whether the traffic it brings makes business sense.

           Matching works because these accounts use Google Ads autotagging
           (gclid) with Google Ads <-> GA4 linked: GA4's sessionCampaignName
           is the literal Google Ads campaign name, confirmed live against a
           real client account (2026-07-25) — the campaign name string
           appears identically in both systems. Matching is done by exact
           campaign name string.

           Sections: (1) Business Overview & cross-system check, (2)
           Engagement Quality vs account baseline, (3) Landing Pages, (4)
           Device Breakdown, (5) New vs Returning, (6) Geo Breakdown
           (city), (7) First-Touch vs Last-Touch Attribution Role, (8)
           Customer Value Trend.

           Note on (7): the GA4 Data API does not expose full multi-touch
           conversion path sequences (that needs GA4's UI-only Attribution
           reports or a BigQuery export) — this compares first-touch vs
           last-touch (session-based) attribution as a proxy for whether a
           campaign tends to open or close the journey.

           This is the backing script for /ga4-campaign-analyst.

Usage    : python3 campaign_analyst.py list <client_slug> [--days 30]
           python3 campaign_analyst.py run <client_slug> "<campaign name or id>" [--days 30]
Changelog: 2026-07-25  Initial version — 8 sections, tested live against a real client account
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402
from ga4_reports import get_credentials, GA4_DATA_API  # noqa: E402

from google.ads.googleads.client import GoogleAdsClient

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"


# ─── Google Ads side ───────────────────────────────────────────────────────

def get_ads_client():
    return GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))


def fetch_campaigns(ads_client, customer_id, date_from, date_to):
    ga_service = ads_client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               metrics.cost_micros, metrics.clicks, metrics.impressions,
               metrics.conversions, metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
        ORDER BY metrics.cost_micros DESC
    """
    rows = []
    for row in ga_service.search(customer_id=customer_id, query=query):
        rows.append({
            "id": str(row.campaign.id),
            "name": row.campaign.name,
            "status": row.campaign.status.name,
            "cost": row.metrics.cost_micros / 1e6,
            "clicks": row.metrics.clicks,
            "impressions": row.metrics.impressions,
            "conversions": row.metrics.conversions,
            "conversions_value": row.metrics.conversions_value,
        })
    return rows


def resolve_campaign(ads_client, customer_id, needle, date_from, date_to):
    campaigns = fetch_campaigns(ads_client, customer_id, date_from, date_to)
    if needle.isdigit():
        for c in campaigns:
            if c["id"] == needle:
                return c, campaigns
        raise SystemExit(f"No campaign with id {needle} found in the last window queried.")

    needle_lower = needle.lower()
    exact = [c for c in campaigns if c["name"].lower() == needle_lower]
    if len(exact) == 1:
        return exact[0], campaigns
    if len(exact) > 1:
        raise SystemExit(f"Multiple campaigns named exactly '{needle}' — use --days to widen/narrow or pass the campaign id instead.")

    partial = [c for c in campaigns if needle_lower in c["name"].lower()]
    if len(partial) == 1:
        return partial[0], campaigns
    if len(partial) > 1:
        names = "\n".join(f"  {c['id']}  {c['name']}" for c in partial)
        raise SystemExit(f"'{needle}' matches multiple campaigns — pass the exact name or id:\n{names}")

    raise SystemExit(f"No campaign matching '{needle}' had activity in this window. Run `list` to see what's available.")


# ─── GA4 side ───────────────────────────────────────────────────────────────

def ga4_query(property_id, headers, dimensions, metrics, date_from, date_to,
              campaign_name=None, campaign_field="sessionCampaignName",
              order_by=None, limit=10):
    body = {
        "dateRanges": [{"startDate": date_from, "endDate": date_to}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }
    if campaign_name is not None:
        body["dimensionFilter"] = {
            "filter": {
                "fieldName": campaign_field,
                "stringFilter": {"matchType": "EXACT", "value": campaign_name},
            }
        }
    if order_by:
        is_metric = order_by in metrics
        order = {"desc": True}
        if is_metric:
            order["metric"] = {"metricName": order_by}
        else:
            order["dimension"] = {"dimensionName": order_by, "orderType": "ALPHANUMERIC"}
        body["orderBys"] = [order]

    r = requests.post(f"{GA4_DATA_API}/properties/{property_id}:runReport", headers=headers, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"GA4 API error {r.status_code}: {r.text[:500]}")
    return r.json()


def rows_of(data, dim_count, metric_names):
    out = []
    for row in data.get("rows", []):
        dims = [dv.get("value", "") for dv in row.get("dimensionValues", [])][:dim_count]
        mets = [mv.get("value", "0") for mv in row.get("metricValues", [])]
        out.append((dims, dict(zip(metric_names, mets))))
    return out


def agg(property_id, headers, metrics, date_from, date_to, campaign_name, campaign_field="sessionCampaignName"):
    """Single aggregate row (no dimension breakdown) for the given metrics."""
    data = ga4_query(property_id, headers, [], metrics, date_from, date_to, campaign_name, campaign_field, limit=1)
    rows = data.get("rows", [])
    if not rows:
        return {m: 0.0 for m in metrics}
    vals = [mv.get("value", "0") for mv in rows[0].get("metricValues", [])]
    return {m: float(v) for m, v in zip(metrics, vals)}


def money(v, currency):
    return f"{v:,.2f} {currency}".strip()


def pct(v):
    return f"{v * 100:.1f}%"


def print_table(headers, rows):
    widths = [max(len(str(h)), 12) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(str(c)))
    line = " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def section(title):
    print(f"\n{'=' * len(title)}\n{title}\n{'=' * len(title)}")


# ─── Commands ───────────────────────────────────────────────────────────────

def cmd_list(args):
    client_meta = resolve(args.client)
    ads_client = get_ads_client()
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    campaigns = fetch_campaigns(ads_client, client_meta["customer_id"], date_from, date_to)
    campaigns = [c for c in campaigns if c["cost"] > 0 or c["clicks"] > 0]
    campaigns.sort(key=lambda c: c["cost"], reverse=True)

    print(f"Client : {client_meta['name']} ({args.client})")
    print(f"Period : {date_from} -> {date_to} ({args.days} days)\n")
    rows = []
    for c in campaigns:
        cpa = c["cost"] / c["conversions"] if c["conversions"] else 0
        rows.append([
            c["id"], c["name"], c["status"],
            money(c["cost"], client_meta.get("currency", "")),
            c["clicks"], f"{c['conversions']:.1f}",
            money(cpa, client_meta.get("currency", "")) if cpa else "n/a",
        ])
    print_table(["id", "name", "status", "cost", "clicks", "conversions", "CPA"], rows)
    print("\nRun a deep dive: python3 scripts/campaign_analyst.py run", args.client, "\"<campaign name or id>\"")


def cmd_run(args):
    client_meta = resolve(args.client)
    property_id = client_meta.get("ga4_property_id")
    if not property_id:
        print(f"No GA4 property configured for '{args.client}' in client_registry.py")
        sys.exit(2)

    currency = client_meta.get("currency", "")
    is_ecommerce = client_meta.get("business_type") == "ecommerce"

    ads_client = get_ads_client()
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    campaign, all_campaigns = resolve_campaign(ads_client, client_meta["customer_id"], args.campaign, date_from, date_to)
    name = campaign["name"]

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    print(f"Client   : {client_meta['name']} ({args.client})")
    print(f"Campaign : {name}  (id {campaign['id']}, {campaign['status']})")
    print(f"Period   : {date_from} -> {date_to} ({args.days} days)")

    # --- 1. Business Overview & cross-system check ---
    section("1. Business Overview & Cross-System Check")
    ga4_metrics = ["sessions", "totalUsers", "conversions", "engagementRate"]
    ga4_totals = agg(property_id, headers, ga4_metrics, date_from, date_to, name)
    ads_cpa = campaign["cost"] / campaign["conversions"] if campaign["conversions"] else 0
    ga4_conv_rate = ga4_totals["conversions"] / ga4_totals["sessions"] if ga4_totals["sessions"] else 0
    print_table(
        ["source", "cost", "clicks/sessions", "conversions", "conv value", "CPA / conv rate"],
        [
            ["Google Ads", money(campaign["cost"], currency), campaign["clicks"],
             f"{campaign['conversions']:.1f}", money(campaign["conversions_value"], currency),
             money(ads_cpa, currency) if ads_cpa else "n/a"],
            ["GA4", "—", int(ga4_totals["sessions"]), f"{ga4_totals['conversions']:.1f}", "—", pct(ga4_conv_rate)],
        ]
    )
    print("\nNote: Ads and GA4 usually define \"conversion\" differently — Ads counts only the specific conversion")
    print("actions configured in the account; GA4's conversions metric here sums every key event (view_item,")
    print("add_to_cart, purchase, etc.), so it will usually run several times higher. Compare trend and CPA, not")
    print("the raw ratio, between the two — unless GA4 shows conversions dropping toward zero (see below).")
    if campaign["conversions"] > 0 and ga4_totals["conversions"] == 0:
        print(f"\nFLAG: GA4 shows ZERO conversions for this campaign despite Ads reporting {campaign['conversions']:.1f} —"
              f" check that this campaign's name/UTM matches GA4 tagging correctly.")
    elif campaign["conversions"] > 0 and (ga4_totals["conversions"] / campaign["conversions"]) < 0.5:
        print(f"\nFLAG: GA4 shows fewer conversions ({ga4_totals['conversions']:.1f}) than Ads ({campaign['conversions']:.1f}) for"
              f" this campaign — unusual, since GA4 normally counts more event types, not fewer. Worth checking tagging.")

    # --- 2. Engagement Quality vs account baseline ---
    section("2. Engagement Quality (vs. account baseline)")
    eng_metrics = ["bounceRate", "engagementRate", "averageSessionDuration", "screenPageViewsPerSession"]
    camp_eng = agg(property_id, headers, eng_metrics, date_from, date_to, name)
    account_eng = agg(property_id, headers, eng_metrics, date_from, date_to, None)
    print_table(
        ["scope", "bounce rate", "engagement rate", "avg session duration", "pages/session"],
        [
            ["This campaign", pct(camp_eng["bounceRate"]), pct(camp_eng["engagementRate"]),
             f"{camp_eng['averageSessionDuration']:.0f}s", f"{camp_eng['screenPageViewsPerSession']:.2f}"],
            ["Account-wide", pct(account_eng["bounceRate"]), pct(account_eng["engagementRate"]),
             f"{account_eng['averageSessionDuration']:.0f}s", f"{account_eng['screenPageViewsPerSession']:.2f}"],
        ]
    )

    # --- 3. Landing Pages ---
    section("3. Landing Page Breakdown")
    lp_data = ga4_query(property_id, headers, ["landingPage"], ["sessions", "conversions", "bounceRate", "averageSessionDuration"],
                         date_from, date_to, name, order_by="sessions", limit=15)
    lp_rows = rows_of(lp_data, 1, ["sessions", "conversions", "bounceRate", "averageSessionDuration"])
    if lp_rows:
        print_table(["landing page", "sessions", "conversions", "bounce rate", "avg time on page"],
                     [[d[0], m["sessions"], f"{float(m['conversions']):.1f}", pct(float(m["bounceRate"])),
                       f"{float(m['averageSessionDuration']):.0f}s"] for d, m in lp_rows])
        print("\n(\"avg time on page\" = average session duration for sessions that landed on this page — GA4 doesn't")
        print(" track true per-pageview dwell time as a standard aggregate metric, this is the closest honest proxy.)")
    else:
        print("(no landing page rows for this campaign in this window)")

    # --- 4. Device Breakdown ---
    section("4. Device Breakdown")
    dev_data = ga4_query(property_id, headers, ["deviceCategory"], ["sessions", "conversions", "bounceRate"],
                          date_from, date_to, name, order_by="sessions", limit=10)
    dev_rows = rows_of(dev_data, 1, ["sessions", "conversions", "bounceRate"])
    if dev_rows:
        print_table(["device", "sessions", "conversions", "bounce rate"],
                     [[d[0], m["sessions"], f"{float(m['conversions']):.1f}", pct(float(m["bounceRate"]))] for d, m in dev_rows])
    else:
        print("(no device rows for this campaign in this window)")

    # --- 5. New vs Returning ---
    section("5. New vs Returning")
    nvr_data = ga4_query(property_id, headers, ["newVsReturning"], ["sessions", "conversions", "engagementRate"],
                          date_from, date_to, name, order_by="sessions", limit=5)
    nvr_rows = rows_of(nvr_data, 1, ["sessions", "conversions", "engagementRate"])
    if nvr_rows:
        print_table(["segment", "sessions", "conversions", "engagement rate"],
                     [[d[0], m["sessions"], f"{float(m['conversions']):.1f}", pct(float(m["engagementRate"]))] for d, m in nvr_rows])
    else:
        print("(no new-vs-returning rows for this campaign in this window)")

    # --- 6. Geo Breakdown ---
    section("6. Geo Breakdown (city)")
    geo_data = ga4_query(property_id, headers, ["city"], ["sessions", "conversions"],
                          date_from, date_to, name, order_by="sessions", limit=10)
    geo_rows = rows_of(geo_data, 1, ["sessions", "conversions"])
    if geo_rows:
        print_table(["city", "sessions", "conversions"],
                     [[d[0], m["sessions"], f"{float(m['conversions']):.1f}"] for d, m in geo_rows])
    else:
        print("(no city rows for this campaign in this window)")

    # --- 7. First-Touch vs Last-Touch Attribution Role ---
    section("7. First-Touch vs Last-Touch Attribution Role")
    print("(GA4's Data API doesn't expose full multi-touch path sequences — this compares session-based")
    print(" [last click] vs. first-user [first touch] attribution as a proxy for the campaign's role.)\n")
    last_touch = agg(property_id, headers, ["sessions", "conversions"], date_from, date_to, name, "sessionCampaignName")
    first_touch = agg(property_id, headers, ["totalUsers", "conversions"], date_from, date_to, name, "firstUserCampaignName")
    print_table(
        ["attribution", "sessions/users", "conversions"],
        [
            ["Last-touch (session-based)", int(last_touch["sessions"]), f"{last_touch['conversions']:.1f}"],
            ["First-touch (first user touch)", int(first_touch["totalUsers"]), f"{first_touch['conversions']:.1f}"],
        ]
    )
    if last_touch["conversions"] and first_touch["conversions"]:
        if first_touch["conversions"] < last_touch["conversions"] * 0.85:
            print(f"\nMore conversions are attributed last-touch than first-touch — this campaign tends to act as a"
                  f" CLOSER (users discovered the brand elsewhere, this campaign brought them back to convert).")
        elif first_touch["conversions"] > last_touch["conversions"] * 1.15:
            print(f"\nMore conversions trace back to this campaign as the first touch than as the last touch — this"
                  f" campaign tends to act as an OPENER (it introduces users who convert later via another channel).")
        else:
            print("\nFirst-touch and last-touch conversion counts are close — this campaign both introduces and closes users at similar rates.")

    # --- 8. Customer Value Trend ---
    section("8. Customer Value Trend")
    if is_ecommerce:
        val_data = ga4_query(property_id, headers, ["date"], ["sessions", "conversions", "purchaseRevenue", "transactions"],
                              date_from, date_to, name, order_by="date", limit=90)
        val_rows = rows_of(val_data, 1, ["sessions", "conversions", "purchaseRevenue", "transactions"])
        if val_rows:
            table = []
            for d, m in val_rows:
                rev = float(m["purchaseRevenue"])
                txn = float(m["transactions"])
                aov = rev / txn if txn else 0
                date_str = f"{d[0][:4]}-{d[0][4:6]}-{d[0][6:]}" if len(d[0]) == 8 and d[0].isdigit() else d[0]
                table.append([date_str, m["sessions"], f"{float(m['conversions']):.1f}", money(rev, currency), money(aov, currency) if txn else "n/a"])
            print_table(["date", "sessions", "conversions", "revenue", "AOV"], table)
        else:
            print("(no daily revenue rows for this campaign in this window)")
    else:
        val_data = ga4_query(property_id, headers, ["date"], ["sessions", "conversions", "eventValue"],
                              date_from, date_to, name, order_by="date", limit=90)
        val_rows = rows_of(val_data, 1, ["sessions", "conversions", "eventValue"])
        if val_rows:
            table = []
            total_value = sum(float(m["eventValue"]) for _, m in val_rows)
            for d, m in val_rows:
                date_str = f"{d[0][:4]}-{d[0][4:6]}-{d[0][6:]}" if len(d[0]) == 8 and d[0].isdigit() else d[0]
                table.append([date_str, m["sessions"], f"{float(m['conversions']):.1f}", money(float(m["eventValue"]), currency)])
            print_table(["date", "sessions", "conversions", "event value"], table)
            if total_value == 0:
                print("\nEvent value is 0 across the whole window — this account likely doesn't assign monetary value to"
                      " leads/events. Track the conversions column above as the value trend instead.")
        else:
            print("(no daily rows for this campaign in this window)")


def main():
    parser = argparse.ArgumentParser(description="GA4 per-campaign deep dive, cross-referenced with Google Ads")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List campaigns with spend in the window, to pick one for `run`")
    p_list.add_argument("client")
    p_list.add_argument("--days", type=int, default=30)
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="Run the 8-section deep dive for one campaign")
    p_run.add_argument("client")
    p_run.add_argument("campaign", help="Exact campaign name (or id) — see `list` for options")
    p_run.add_argument("--days", type=int, default=30)
    p_run.add_argument("--pdf", action="store_true", help="Also write a branded PDF to clients/<slug>/reports/")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()

    if args.cmd == "run" and args.pdf:
        from text_report_pdf import capture_stdout, render_text_report
        client_meta = resolve(args.client)
        text = capture_stdout(args.func, args)
        reports_dir = Path(__file__).resolve().parent.parent / "clients" / client_meta["slug"] / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        safe_campaign = "".join(c if c.isalnum() else "_" for c in args.campaign)[:40]
        pdf_path = reports_dir / f"campaign_analyst_{safe_campaign}_{datetime.now().strftime('%Y-%m-%d')}.pdf"
        render_text_report(client_meta, f"Campaign Deep Dive — {args.campaign}", text, pdf_path)
        print(f"\nPDF written: {pdf_path}")
    else:
        args.func(args)


if __name__ == "__main__":
    main()
