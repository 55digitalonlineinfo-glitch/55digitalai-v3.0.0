#!/usr/bin/env python3
"""
55DigitalAI — GA4 Data Analyst (Ready-Made Reports)
=============================================================
Purpose  : Predefined GA4 Data API reports, runnable per client from the
           terminal — 24 general reports across acquisition, retention,
           engagement, and conversion, plus 19 ecommerce-only scenarios
           (purchase funnel, top products, revenue by channel/page/device/
           country/day, AOV, cart abandonment, ...). Read-only.

           This is the backing script for /ga4-data-analyst — see that
           command file for how a natural-language question ("how's the
           purchase path looking?") maps to one of the report names below.

Usage    : python3 ga4_reports.py list [--client <slug>]
           python3 ga4_reports.py run <client_slug> <report_name> [--days 30] [--limit 20]
Changelog: 2026-07-25  Initial version (10 general + 5 ecommerce reports)
           2026-07-25  Expanded to 24 general + 19 ecommerce (43 total);
                       added event_filter (dimensionFilter) support for
                       lead_funnel/contact_clicks; all 43 tested live
                       against a lead-gen client and the ecommerce client
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"
GA4_DATA_API = "https://analyticsdata.googleapis.com/v1beta"

# ─── report library ───────────────────────────────────────────────────────────
# Each report: dimensions + metrics passed straight to runReport, an order_by
# metric (descending) to sort by, and whether it requires ecommerce data.

REPORTS = {
    # --- Acquisition (6) ---
    "acquisition_channels": {
        "category": "Acquisition", "ecommerce_only": False,
        "description": "Sessions, engagement, and conversions by channel (Organic Search, Paid Search, Direct, ...)",
        "dimensions": ["sessionDefaultChannelGroup"],
        "metrics": ["sessions", "totalUsers", "engagementRate", "conversions"],
        "order_by": "sessions",
    },
    "source_medium": {
        "category": "Acquisition", "ecommerce_only": False,
        "description": "Sessions and conversions by exact source/medium (google/cpc, google/organic, direct/none, ...)",
        "dimensions": ["sessionSourceMedium"],
        "metrics": ["sessions", "totalUsers", "conversions"],
        "order_by": "sessions",
    },
    "campaign_performance": {
        "category": "Acquisition", "ecommerce_only": False,
        "description": "Sessions and conversions by GA4-tracked campaign name (utm_campaign)",
        "dimensions": ["sessionCampaignName"],
        "metrics": ["sessions", "totalUsers", "conversions"],
        "order_by": "sessions",
    },
    "first_touch_channels": {
        "category": "Acquisition", "ecommerce_only": False,
        "description": "First-touch channel attribution (who got the user in the door originally) vs session-based acquisition_channels",
        "dimensions": ["firstUserDefaultChannelGroup"],
        "metrics": ["totalUsers", "sessions", "conversions"],
        "order_by": "totalUsers",
    },
    "country_breakdown": {
        "category": "Acquisition", "ecommerce_only": False,
        "description": "Sessions and conversions by country",
        "dimensions": ["country"],
        "metrics": ["sessions", "conversions"],
        "order_by": "sessions",
    },
    "language_breakdown": {
        "category": "Acquisition", "ecommerce_only": False,
        "description": "Sessions by browser/device language — useful for multi-market clients",
        "dimensions": ["language"],
        "metrics": ["sessions", "totalUsers"],
        "order_by": "sessions",
    },

    # --- Retention (2) ---
    "new_vs_returning": {
        "category": "Retention", "ecommerce_only": False,
        "description": "New vs returning users — the simplest retention signal",
        "dimensions": ["newVsReturning"],
        "metrics": ["totalUsers", "sessions", "engagementRate", "conversions"],
        "order_by": "totalUsers",
    },
    "returning_user_engagement": {
        "category": "Retention", "ecommerce_only": False,
        "description": "Engagement depth (session duration, pages/session) split by new vs returning",
        "dimensions": ["newVsReturning"],
        "metrics": ["averageSessionDuration", "screenPageViewsPerSession", "bounceRate"],
        "order_by": None,
    },

    # --- Engagement (12) ---
    "top_landing_pages": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Which landing pages bring in sessions and convert",
        "dimensions": ["landingPage"],
        "metrics": ["sessions", "engagementRate", "conversions"],
        "order_by": "sessions",
    },
    "top_pages": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Most-viewed pages site-wide",
        "dimensions": ["pagePath"],
        "metrics": ["screenPageViews", "userEngagementDuration", "totalUsers"],
        "order_by": "screenPageViews",
    },
    "device_breakdown": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Sessions and conversions by device category (mobile/desktop/tablet)",
        "dimensions": ["deviceCategory"],
        "metrics": ["sessions", "engagementRate", "conversions"],
        "order_by": "sessions",
    },
    "browser_breakdown": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Sessions by browser — useful for spotting rendering/tracking issues on one browser",
        "dimensions": ["browser"],
        "metrics": ["sessions", "engagementRate"],
        "order_by": "sessions",
    },
    "os_breakdown": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Sessions by operating system",
        "dimensions": ["operatingSystem"],
        "metrics": ["sessions", "conversions"],
        "order_by": "sessions",
    },
    "geo_breakdown": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Sessions and conversions by city",
        "dimensions": ["city"],
        "metrics": ["sessions", "conversions"],
        "order_by": "sessions",
    },
    "hourly_pattern": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Traffic by hour of day — useful for ad-schedule decisions",
        "dimensions": ["hour"],
        "metrics": ["sessions", "conversions"],
        "order_by": "hour",
        "order_numeric": True,
    },
    "day_of_week_pattern": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Traffic by day of week (0=Sunday) — pairs with hourly_pattern for ad schedule decisions",
        "dimensions": ["dayOfWeek"],
        "metrics": ["sessions", "conversions"],
        "order_by": "dayOfWeek",
        "order_numeric": True,
        "order_numeric_asc": True,
    },
    "daily_trend": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Day-by-day sessions/users/conversions trend over the period",
        "dimensions": ["date"],
        "metrics": ["sessions", "totalUsers", "conversions"],
        "order_by": "date",
        "order_numeric": True,
        "order_numeric_asc": True,
    },
    "conversion_events": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Volume of every tracked event (form_start, click_tel, purchase, ...)",
        "dimensions": ["eventName"],
        "metrics": ["eventCount", "totalUsers"],
        "order_by": "eventCount",
    },
    "engagement_by_channel": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Engagement rate, bounce rate, and avg session duration by channel — a deeper cut than acquisition_channels",
        "dimensions": ["sessionDefaultChannelGroup"],
        "metrics": ["engagementRate", "bounceRate", "averageSessionDuration"],
        "order_by": None,
    },
    "high_bounce_landing_pages": {
        "category": "Engagement", "ecommerce_only": False,
        "description": "Landing pages with the worst bounce rate — candidates for a landing-page fix",
        "dimensions": ["landingPage"],
        "metrics": ["bounceRate", "sessions"],
        "order_by": "bounceRate",
    },

    # --- Conversion / Lead Gen (4) ---
    "landing_page_channel_mix": {
        "category": "Conversion", "ecommerce_only": False,
        "description": "Which channel drives sessions to which landing page — top combinations",
        "dimensions": ["landingPage", "sessionDefaultChannelGroup"],
        "metrics": ["sessions", "conversions"],
        "order_by": "sessions",
    },
    "conversion_rate_by_page": {
        "category": "Conversion", "ecommerce_only": False,
        "description": "Sessions, conversions, and computed conversion rate per landing page",
        "dimensions": ["landingPage"],
        "metrics": ["sessions", "conversions"],
        "order_by": "sessions",
        "derived": [("conversionRate", "conversions", "sessions")],
    },
    "lead_funnel": {
        "category": "Conversion", "ecommerce_only": False,
        "description": "Lead-gen funnel volume: form_start -> form_submit/formularz -> generate_lead (whichever events this account actually uses)",
        "dimensions": ["eventName"],
        "metrics": ["eventCount", "totalUsers"],
        "order_by": "eventCount",
        "event_filter": ["form_start", "form_submit", "formularz", "generate_lead", "submit_lead_form"],
    },
    "contact_clicks": {
        "category": "Conversion", "ecommerce_only": False,
        "description": "Phone/email/social contact-intent micro-conversions",
        "dimensions": ["eventName"],
        "metrics": ["eventCount", "totalUsers"],
        "order_by": "eventCount",
        "event_filter": ["click_tel", "click_email", "click_social_button", "click_to_call"],
    },

    # --- Ecommerce only (19) ---
    "purchase_funnel": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Drop-off from product view -> add to cart -> checkout -> purchase",
        "dimensions": [],
        "metrics": ["itemsViewed", "itemsAddedToCart", "itemsCheckedOut", "itemsPurchased"],
        "order_by": None,
    },
    "ecommerce_funnel_by_channel": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Session-level funnel (add to cart -> checkout -> purchase) broken out by acquisition channel",
        "dimensions": ["sessionDefaultChannelGroup"],
        "metrics": ["sessions", "addToCarts", "checkouts", "ecommercePurchases"],
        "order_by": "sessions",
    },
    "top_products": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Best-selling products by revenue",
        "dimensions": ["itemName"],
        "metrics": ["itemRevenue", "itemsPurchased", "itemsViewed", "cartToViewRate", "purchaseToViewRate"],
        "order_by": "itemRevenue",
    },
    "top_products_by_units": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Best-selling products by units sold (not revenue) — useful for inventory/ops conversations",
        "dimensions": ["itemName"],
        "metrics": ["itemsPurchased", "itemRevenue"],
        "order_by": "itemsPurchased",
    },
    "most_viewed_products": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Highest-traffic products alongside their purchase count — flags high-interest/low-conversion products worth a pricing or description review",
        "dimensions": ["itemName"],
        "metrics": ["itemsViewed", "itemsPurchased"],
        "order_by": "itemsViewed",
    },
    "product_view_to_cart_rate": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Per-product view-to-cart-add rate — which products get looked at but not added to cart",
        "dimensions": ["itemName"],
        "metrics": ["itemsViewed", "itemsAddedToCart", "cartToViewRate"],
        "order_by": "itemsViewed",
    },
    "product_purchase_to_view_rate": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Per-product view-to-purchase conversion rate",
        "dimensions": ["itemName"],
        "metrics": ["itemsViewed", "itemsPurchased", "purchaseToViewRate"],
        "order_by": "itemsViewed",
    },
    "product_categories": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Revenue and units by product category",
        "dimensions": ["itemCategory"],
        "metrics": ["itemRevenue", "itemsPurchased"],
        "order_by": "itemRevenue",
    },
    "cart_abandonment": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Cart-to-purchase rate, account-wide — abandonment rate is 1 minus this",
        "dimensions": [],
        "metrics": ["itemsAddedToCart", "itemsPurchased"],
        "order_by": None,
        "derived": [("cartToPurchaseRate", "itemsPurchased", "itemsAddedToCart")],
    },
    "revenue_by_channel": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Purchase revenue and transactions by acquisition channel",
        "dimensions": ["sessionDefaultChannelGroup"],
        "metrics": ["totalRevenue", "transactions", "sessions"],
        "order_by": "totalRevenue",
    },
    "revenue_by_source_medium": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Purchase revenue by exact source/medium — more granular than revenue_by_channel",
        "dimensions": ["sessionSourceMedium"],
        "metrics": ["totalRevenue", "transactions"],
        "order_by": "totalRevenue",
    },
    "revenue_by_landing_page": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Which landing page a purchase session started on",
        "dimensions": ["landingPage"],
        "metrics": ["totalRevenue", "transactions"],
        "order_by": "totalRevenue",
    },
    "revenue_by_device": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Revenue and transactions by device category",
        "dimensions": ["deviceCategory"],
        "metrics": ["totalRevenue", "transactions", "sessions"],
        "order_by": "totalRevenue",
    },
    "revenue_by_country": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Revenue and transactions by country",
        "dimensions": ["country"],
        "metrics": ["totalRevenue", "transactions"],
        "order_by": "totalRevenue",
    },
    "revenue_by_day_of_week": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Revenue and transactions by day of week — useful for promo/scheduling timing",
        "dimensions": ["dayOfWeek"],
        "metrics": ["totalRevenue", "transactions"],
        "order_by": "dayOfWeek",
        "order_numeric": True,
        "order_numeric_asc": True,
    },
    "revenue_by_new_vs_returning": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "How much revenue comes from new vs returning customers",
        "dimensions": ["newVsReturning"],
        "metrics": ["totalRevenue", "transactions", "totalUsers"],
        "order_by": "totalRevenue",
    },
    "aov_trend": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Daily revenue, transactions, and average order value trend",
        "dimensions": ["date"],
        "metrics": ["totalRevenue", "transactions"],
        "order_by": "date",
        "order_numeric": True,
        "order_numeric_asc": True,
        "derived": [("avgOrderValue", "totalRevenue", "transactions")],
    },
    "ecommerce_conversion_rate_trend": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Daily sessions vs transactions, with computed ecommerce conversion rate",
        "dimensions": ["date"],
        "metrics": ["sessions", "transactions"],
        "order_by": "date",
        "order_numeric": True,
        "order_numeric_asc": True,
        "derived": [("ecommerceConvRate", "transactions", "sessions")],
    },
    "average_items_per_order": {
        "category": "Ecommerce", "ecommerce_only": True,
        "description": "Account-wide average number of items per completed order",
        "dimensions": [],
        "metrics": ["itemsPurchased", "transactions"],
        "order_by": None,
        "derived": [("avgItemsPerOrder", "itemsPurchased", "transactions")],
    },
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def get_credentials():
    cfg = yaml.safe_load(GOOGLE_ADS_YAML.read_text())
    creds = Credentials(
        token=None, refresh_token=cfg["refresh_token"],
        client_id=cfg["client_id"], client_secret=cfg["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return creds


def run_report(property_id, headers, config, date_from, date_to, limit):
    body = {
        "dateRanges": [{"startDate": date_from, "endDate": date_to}],
        "dimensions": [{"name": d} for d in config["dimensions"]],
        "metrics": [{"name": m} for m in config["metrics"]],
        "limit": limit,
    }
    if config.get("order_by"):
        is_metric = config["order_by"] in config["metrics"]
        order = {"desc": not config.get("order_numeric_asc", False)}
        if is_metric:
            order["metric"] = {"metricName": config["order_by"]}
        else:
            order["dimension"] = {"dimensionName": config["order_by"], "orderType": "NUMERIC" if config.get("order_numeric") else "ALPHANUMERIC"}
        body["orderBys"] = [order]

    if config.get("event_filter"):
        body["dimensionFilter"] = {
            "filter": {
                "fieldName": "eventName",
                "inListFilter": {"values": config["event_filter"]},
            }
        }

    r = requests.post(f"{GA4_DATA_API}/properties/{property_id}:runReport", headers=headers, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"GA4 API error {r.status_code}: {r.text[:500]}")
    return r.json()


def format_dim_value(dim_name, val):
    if dim_name == "date" and len(val) == 8 and val.isdigit():
        return f"{val[:4]}-{val[4:6]}-{val[6:]}"
    return val


def format_report(name, config, data, currency=""):
    dim_headers = config["dimensions"]
    met_headers = config["metrics"]
    derived = config.get("derived", [])
    derived_headers = [d[0] for d in derived]
    all_headers = dim_headers + met_headers + derived_headers
    rows = data.get("rows", [])

    lines = [f"=== {name} ===", config["description"], ""]
    if not rows:
        lines.append("(no rows returned for this period)")
        return "\n".join(lines)

    col_widths = [max(len(h), 24) for h in dim_headers] + [max(len(h), 14) for h in met_headers + derived_headers]
    header_line = " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(all_headers)
    )
    lines.append(header_line)
    lines.append("-" * len(header_line))

    for row in rows:
        dim_vals = [format_dim_value(h, dv.get("value", "")) for h, dv in zip(dim_headers, row.get("dimensionValues", []))]
        met_vals = [mv.get("value", "") for mv in row.get("metricValues", [])]
        met_lookup = dict(zip(met_headers, met_vals))

        def fmt_metric(name_m, val):
            try:
                fval = float(val)
                if "revenue" in name_m.lower() or "value" in name_m.lower():
                    return f"{fval:,.2f} {currency}".strip()
                if "rate" in name_m.lower():
                    return f"{fval*100:.1f}%"
                if fval == int(fval):
                    return f"{int(fval):,}"
                return f"{fval:,.2f}"
            except (ValueError, ZeroDivisionError):
                return val

        formatted_mets = [fmt_metric(h, v) for h, v in zip(met_headers, met_vals)]

        formatted_derived = []
        for d_name, numerator, denominator in derived:
            try:
                num = float(met_lookup.get(numerator, 0))
                den = float(met_lookup.get(denominator, 0))
                formatted_derived.append(fmt_metric(d_name, num / den) if den else "n/a")
            except (ValueError, ZeroDivisionError):
                formatted_derived.append("n/a")

        cells = dim_vals + formatted_mets + formatted_derived
        lines.append(" | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells)))

    totals = data.get("totals", [])
    if totals:
        tot_vals = [mv.get("value", "") for mv in totals[0].get("metricValues", [])]
        lines.append("-" * len(header_line))
        tot_cells = [""] * len(dim_headers) + tot_vals + [""] * len(derived_headers)
        lines.append(" | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(tot_cells)) + "  (TOTAL)")

    return "\n".join(lines)


def cmd_list(args):
    by_category = {}
    for name, cfg in REPORTS.items():
        by_category.setdefault(cfg["category"], []).append((name, cfg))

    client_meta = resolve(args.client) if args.client else None
    is_ecommerce = client_meta and client_meta.get("business_type") == "ecommerce"

    for category, reports in by_category.items():
        print(f"\n{category}")
        for name, cfg in reports:
            if cfg["ecommerce_only"] and client_meta and not is_ecommerce:
                continue
            tag = " [ecommerce only]" if cfg["ecommerce_only"] else ""
            print(f"  {name:<24} {cfg['description']}{tag}")


def cmd_run(args):
    client_meta = resolve(args.client)
    property_id = client_meta.get("ga4_property_id")
    if not property_id:
        print(f"No GA4 property configured for '{args.client}' in client_registry.py")
        sys.exit(2)

    config = REPORTS.get(args.report)
    if not config:
        print(f"Unknown report '{args.report}'. Run `list` to see available reports.")
        sys.exit(2)

    if config["ecommerce_only"] and client_meta.get("business_type") != "ecommerce":
        print(f"WARNING: '{args.report}' is an ecommerce report; {args.client} is business_type="
              f"{client_meta.get('business_type')}. Running anyway — expect empty/zero rows if no ecommerce tracking exists.")

    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    print(f"Client   : {client_meta['name']} ({args.client})")
    print(f"Property : {property_id}")
    print(f"Period   : {date_from} -> {date_to} ({args.days} days)")

    data = run_report(property_id, headers, config, date_from, date_to, args.limit)
    print()
    print(format_report(args.report, config, data, currency=client_meta.get("currency", "")))


def main():
    parser = argparse.ArgumentParser(description="GA4 ready-made reports")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List available reports")
    p_list.add_argument("--client", help="Filter out ecommerce-only reports for non-ecommerce clients")
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="Run a report")
    p_run.add_argument("client")
    p_run.add_argument("report")
    p_run.add_argument("--days", type=int, default=30)
    p_run.add_argument("--limit", type=int, default=20)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
