#!/usr/bin/env python3
"""
55DigitalAI — Merchant Center Product Feed Review
=============================================================
Purpose  : Product feed health for a client's Merchant Center account, in
           one place — approval status per destination (Shopping, Free
           Listings, Display Ads), disapprovals grouped by concrete reason,
           free-listings-specific monitoring, and (where Google's
           competitive-pricing program is enabled for the account) a price
           vs. benchmark comparison. Read-only — uses the Content API for
           Shopping (content scope), same OAuth token as everything else.

           IMPORTANT interpretation note (found live on a real client account,
           2026-07-25):
           `destinationStatuses[].status` can say "disapproved" for a
           destination even when every itemLevelIssue listed for that same
           destination has servability "unaffected" — e.g. a whole catalog
           showed destination-level "disapproved" for Shopping and
           SurfacesAcrossGoogle, but the only issue with servability
           "disapproved" was scoped to the DisplayAds destination (a
           "legal_restrictions_policy_violation" tied to personalized/
           remarketing ads for a regulated product category — this shows up
           for alcohol, tobacco, financial services, etc.) — Shopping/Free
           Listings' own regulated-category policy issues were explicitly
           servability "unaffected". Google's top-level rollup doesn't
           always match what's actually blocking the listing — likely an
           account-level flag (e.g. a regulated-category ads certification)
           bleeding into the destination summary rather than a per-item
           content problem. The reliable signal is itemLevelIssues[].servability:
           "disapproved"/"demoted" = actually blocking that destination;
           "unaffected" = Google is tracking the flag but NOT currently
           blocking. This script leads with servability, and only shows
           the destination-level rollup as secondary context — with an
           explicit conflict callout when the two disagree, rather than
           asserting "your whole feed is disapproved" when live campaign
           performance may say otherwise. Recommend the user confirm
           against Merchant Center's own Diagnostics page for anything
           this script flags as a live conflict, rather than trusting
           either signal in isolation.

Usage    : python3 merchant_review.py <client_slug>
Changelog: 2026-07-25  Initial version — tested live against a real client
                       account; price-competitiveness view unavailable for
                       that account (not enrolled in Google's pricing
                       program / feature may not be available for that
                       country) — script degrades gracefully with an
                       explanatory note.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402
from ga4_reports import get_credentials, run_report, GA4_DATA_API  # noqa: E402

CONTENT_API = "https://shoppingcontent.googleapis.com/content/v2.1"


def fetch_organic_shopping_sessions(property_id, ga4_creds, days=30):
    """Real free-listings traffic, as a cross-check against Merchant Center's eligibility-only view."""
    headers = {"Authorization": f"Bearer {ga4_creds.token}"}
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)
    config = {"dimensions": ["sessionDefaultChannelGroup"], "metrics": ["sessions", "conversions"], "order_by": "sessions"}
    data = run_report(property_id, headers, config, date_from, date_to, limit=25)
    for row in data.get("rows", []):
        channel = row["dimensionValues"][0]["value"]
        if channel == "Organic Shopping":
            sessions = int(row["metricValues"][0]["value"])
            conversions = float(row["metricValues"][1]["value"])
            return {"sessions": sessions, "conversions": conversions}
    return None


def fetch_merchant_performance(merchant_id, headers, days=30):
    """Authoritative impressions/clicks/CTR per program (Shopping Ads vs Free Product Listing),
    straight from Merchant Center itself — not an approximation via GA4 channel classification."""
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)
    query = f"""
        SELECT segments.program, metrics.impressions, metrics.clicks, metrics.ctr
        FROM MerchantPerformanceView
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    r = requests.post(f"{CONTENT_API}/{merchant_id}/reports/search", headers=headers, json={"query": query})
    if r.status_code != 200:
        return None, r.json().get("error", {}).get("message", r.text[:300])
    out = {}
    for row in r.json().get("results", []):
        program = row["segments"]["program"]
        m = row["metrics"]
        out[program] = {"impressions": int(m.get("impressions", 0)), "clicks": int(m.get("clicks", 0)), "ctr": float(m.get("ctr", 0))}
    return out, None


def fetch_top_free_listing_products(merchant_id, headers, days=30, limit=10):
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)
    query = f"""
        SELECT segments.offer_id, segments.title, metrics.impressions, metrics.clicks, metrics.ctr
        FROM MerchantPerformanceView
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}' AND segments.program = 'FREE_PRODUCT_LISTING'
        ORDER BY metrics.impressions DESC
        LIMIT {limit}
    """
    r = requests.post(f"{CONTENT_API}/{merchant_id}/reports/search", headers=headers, json={"query": query})
    if r.status_code != 200:
        return None
    rows = []
    for row in r.json().get("results", []):
        seg = row["segments"]
        m = row["metrics"]
        rows.append({
            "title": seg.get("title", ""), "offer_id": seg.get("offerId", ""),
            "impressions": int(m.get("impressions", 0)), "clicks": int(m.get("clicks", 0)), "ctr": float(m.get("ctr", 0)),
        })
    return rows


def fetch_all_product_statuses(merchant_id, headers):
    products = []
    page_token = None
    while True:
        params = {"maxResults": 250}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(f"{CONTENT_API}/{merchant_id}/productstatuses", headers=headers, params=params)
        if r.status_code != 200:
            raise RuntimeError(f"Content API error {r.status_code}: {r.text[:500]}")
        data = r.json()
        products.extend(data.get("resources", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return products


def analyze(products):
    dest_rollup = {}          # destination -> {status: count}  (Google's top-level field, informational)
    dest_blocking = {}        # destination -> count of products with a servability=disapproved/demoted issue
    issue_groups = {}         # code -> {description, detail, destination, servability, count, example}
    conflicts = {}            # destination -> count of products where rollup says disapproved but no blocking issue found

    for p in products:
        blocking_destinations = set()
        for issue in p.get("itemLevelIssues", []):
            key = (issue["code"], issue.get("destination", ""))
            g = issue_groups.setdefault(key, {
                "description": issue.get("description", ""),
                "detail": issue.get("detail", ""),
                "destination": issue.get("destination", ""),
                "servability": issue.get("servability", ""),
                "count": 0,
                "example": (p.get("title", ""), p.get("link", "")),
            })
            g["count"] += 1
            if issue.get("servability") in ("disapproved", "demoted"):
                blocking_destinations.add(issue.get("destination"))
                dest_blocking[issue["destination"]] = dest_blocking.get(issue["destination"], 0) + 1

        for ds in p.get("destinationStatuses", []):
            dest = ds["destination"]
            status = ds["status"]
            dest_rollup.setdefault(dest, {})
            dest_rollup[dest][status] = dest_rollup[dest].get(status, 0) + 1
            if status == "disapproved" and dest not in blocking_destinations:
                conflicts[dest] = conflicts.get(dest, 0) + 1

    return dest_rollup, dest_blocking, issue_groups, conflicts


def try_price_competitiveness(merchant_id, headers, limit=20):
    query = f"""
        SELECT price_competitiveness_product_view.id,
               price_competitiveness_product_view.title,
               price_competitiveness_product_view.price_micros,
               price_competitiveness_product_view.price_currency_code,
               price_competitiveness_product_view.benchmark_price_micros,
               price_competitiveness_product_view.benchmark_price_currency_code
        FROM PriceCompetitivenessProductView
        LIMIT {limit}
    """
    r = requests.post(f"{CONTENT_API}/{merchant_id}/reports/search", headers=headers, json={"query": query})
    if r.status_code != 200:
        return None, r.json().get("error", {}).get("message", r.text[:300])
    return r.json().get("results", []), None


def print_table(headers_row, rows):
    widths = [max(len(str(h)), 10) for h in headers_row]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(str(c)))
    line = " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers_row))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def section(title):
    print(f"\n{'=' * len(title)}\n{title}\n{'=' * len(title)}")


def cmd_run(args):
    client_meta = resolve(args.client)
    merchant_id = client_meta.get("merchant_center_id")
    if not merchant_id:
        print(f"No Merchant Center account configured for '{args.client}' in client_registry.py")
        sys.exit(2)

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

    print(f"Client          : {client_meta['name']} ({args.client})")
    print(f"Merchant Center : {merchant_id}")

    products = fetch_all_product_statuses(merchant_id, headers)
    dest_rollup, dest_blocking, issue_groups, conflicts = analyze(products)
    total = len(products)

    # --- 1. Feed Overview ---
    section("1. Feed Overview")
    print(f"Total products in feed: {total}\n")
    rows = []
    for dest in sorted(dest_rollup):
        rollup = dest_rollup[dest]
        disapproved_rollup = rollup.get("disapproved", 0)
        real_blocking = dest_blocking.get(dest, 0)
        rows.append([dest, total, rollup.get("approved", 0), disapproved_rollup, rollup.get("pending", 0), real_blocking])
    print_table(["destination", "total", "approved (rollup)", "disapproved (rollup)", "pending (rollup)", "actually blocking (servability)"], rows)

    if conflicts:
        print("\nCAVEAT — Google's top-level status disagrees with the item-level servability data for:")
        for dest, count in conflicts.items():
            print(f"  {dest}: {count} product(s) marked \"disapproved\" at the destination level, but NONE of their")
            print(f"    listed issues for {dest} have servability disapproved/demoted (all are \"unaffected\").")
        print("  This usually reflects an account-level flag (e.g. an alcohol/restricted-category ads certification")
        print("  requirement) bleeding into the destination summary, not a real per-item content problem. Verify")
        print("  against Merchant Center's own Diagnostics page before treating this as a live outage — if a campaign")
        print("  using this feed is still getting real impressions/clicks in Ads, the destination is likely still serving.")

    # --- 2. Disapprovals with concrete reasons ---
    section("2. Disapprovals & Issues — Concrete Reasons")
    if not issue_groups:
        print("No item-level issues found.")
    else:
        ordered = sorted(issue_groups.items(), key=lambda kv: (kv[1]["servability"] != "disapproved", kv[1]["servability"] != "demoted", -kv[1]["count"]))
        rows = []
        for (code, dest), g in ordered:
            severity = "BLOCKING" if g["servability"] in ("disapproved", "demoted") else "flagged, not blocking"
            rows.append([code, dest, severity, g["count"], g["description"]])
        print_table(["issue code", "destination", "severity", "# products", "description"], rows)
        print("\nExamples (one per issue code + destination):")
        for (code, dest), g in ordered:
            title, link = g["example"]
            print(f"  [{code} / {dest}] {title}")
            if g["detail"]:
                print(f"    -> {g['detail']}")
            if link:
                print(f"    -> {link}")

    # --- 3. Free Listings Monitoring ---
    section("3. Free Listings Monitoring (SurfacesAcrossGoogle)")
    fl_rollup = dest_rollup.get("SurfacesAcrossGoogle")
    fl_blocking = dest_blocking.get("SurfacesAcrossGoogle", 0)
    if fl_rollup:
        print_table(
            ["metric", "value"],
            [
                ["Total products", total],
                ["Rollup: approved", fl_rollup.get("approved", 0)],
                ["Rollup: disapproved", fl_rollup.get("disapproved", 0)],
                ["Rollup: pending", fl_rollup.get("pending", 0)],
                ["Actually blocked (servability disapproved/demoted)", fl_blocking],
            ]
        )
        if fl_rollup.get("disapproved", 0) > fl_blocking:
            print(f"\n{fl_rollup.get('disapproved', 0) - fl_blocking} product(s) show \"disapproved\" in the rollup for free")
            print("listings with no actually-blocking issue attached — see the caveat in section 1. Free listings for")
            print("these products are likely still live; this needs confirming in Merchant Center directly, not assumed.")
    else:
        print("No SurfacesAcrossGoogle destination data returned — this feed may not be enrolled in free listings.")

    print("\nEligibility (above) only tells you whether Google is willing to show these products for free — not")
    print("whether they're actually getting seen. Real performance, straight from Merchant Center itself:")
    perf, perf_error = fetch_merchant_performance(merchant_id, headers)
    mc_free_clicks = None
    if perf is None:
        print(f"(MerchantPerformanceView unavailable: {perf_error})")
    else:
        rows = []
        for program, label in [("FREE_PRODUCT_LISTING", "Free listings"), ("SHOPPING_ADS", "Shopping ads (paid, for comparison)")]:
            p = perf.get(program)
            if p:
                if program == "FREE_PRODUCT_LISTING":
                    mc_free_clicks = p["clicks"]
                rows.append([label, f"{p['impressions']:,}", f"{p['clicks']:,}", f"{p['ctr']*100:.2f}%"])
        if rows:
            print_table(["program", "impressions (30d)", "clicks (30d)", "CTR"], rows)
        else:
            print("No FREE_PRODUCT_LISTING or SHOPPING_ADS rows returned for this window.")

        top_products = fetch_top_free_listing_products(merchant_id, headers)
        if top_products:
            print("\nTop 10 products by free-listing impressions:")
            print_table(
                ["product", "impressions", "clicks", "CTR"],
                [[p["title"][:60], f"{p['impressions']:,}", p["clicks"], f"{p['ctr']*100:.2f}%"] for p in top_products]
            )
            zero_click = [p for p in top_products if p["clicks"] == 0 and p["impressions"] >= 100]
            if zero_click:
                print(f"\n{len(zero_click)} of these get real impressions but zero clicks — visibility isn't the problem")
                print("for them, something about the listing itself (title, image, price) likely is.")

    ga4_property_id = client_meta.get("ga4_property_id")
    if ga4_property_id:
        organic_shopping = fetch_organic_shopping_sessions(ga4_property_id, creds)
        ga4_sessions = organic_shopping["sessions"] if organic_shopping else 0
        print(f"\nGA4 cross-check: \"Organic Shopping\" channel shows {ga4_sessions} session(s) in the same window.")
        if mc_free_clicks is not None and mc_free_clicks > 0:
            if ga4_sessions < mc_free_clicks * 0.5:
                print(f"That's well below Merchant Center's {mc_free_clicks} reported clicks — likely GA4 undercounting")
                print("(consent-mode cookie loss, or GA4's channel-classification rules not catching every free-listing")
                print("referral) rather than a real gap. Trust Merchant Center's click/impression numbers above as the")
                print("authoritative free-listings traffic figure; use GA4 only for on-site behavior once they land.")
    else:
        print("(No ga4_property_id configured for this client — skipping the GA4 cross-check)")

    # --- 4. Price Comparison vs Competitors ---
    section("4. Price Comparison vs. Competitors")
    results, error = try_price_competitiveness(merchant_id, headers)
    if results is None:
        print("Not available for this account. This isn't an enrollable program (no API or UI opt-in) — it's an")
        print("auto-computed Google analytics view (Merchant Center > Analytics > Products > Competitors) gated on")
        print("Google's own eligibility (enough competitor/category benchmark data for this country/category).")
        print(f"(API response: {error})")
    elif not results:
        print("The view returned successfully, but no benchmark data came back for any product in this window —")
        print("Google may not have enough competitor pricing signal for these specific SKUs yet.")
    else:
        rows = []
        for row in results:
            v = row.get("priceCompetitivenessProductView", {})
            price = float(v.get("priceMicros", 0)) / 1e6
            bench = float(v.get("benchmarkPriceMicros", 0)) / 1e6
            diff_pct = ((price - bench) / bench * 100) if bench else 0
            rows.append([v.get("title", "")[:50], f"{price:,.2f} {v.get('priceCurrencyCode','')}",
                         f"{bench:,.2f} {v.get('benchmarkPriceCurrencyCode','')}", f"{diff_pct:+.1f}%"])
        print_table(["product", "your price", "benchmark price", "difference"], rows)


def main():
    parser = argparse.ArgumentParser(description="Merchant Center product feed review")
    parser.add_argument("client")
    parser.add_argument("--pdf", action="store_true", help="Also write a branded PDF to clients/<slug>/reports/")
    parser.set_defaults(func=cmd_run)
    args = parser.parse_args()

    if args.pdf:
        from text_report_pdf import capture_stdout, render_text_report
        client_meta = resolve(args.client)
        text = capture_stdout(args.func, args)
        reports_dir = Path(__file__).resolve().parent.parent / "clients" / client_meta["slug"] / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = reports_dir / f"merchant_review_{datetime.now().strftime('%Y-%m-%d')}.pdf"
        render_text_report(client_meta, "Merchant Center Feed Review", text, pdf_path)
        print(f"\nPDF written: {pdf_path}")
    else:
        args.func(args)


if __name__ == "__main__":
    main()
