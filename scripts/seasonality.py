#!/usr/bin/env python3
"""
55DigitalAI — Seasonality Analysis
=============================================================
Purpose  : Year-over-year comparison at 4 levels — campaigns, product
           types, brands, individual products — designed to answer one
           question in the client's language: "is this month's dip a
           seasonal pattern that happened last year too, or a real account
           problem?" Compares the target month's month-over-month change
           against the *same calendar transition last year*; if both years
           moved the same way by a similar amount, it's labeled SEASONAL;
           if this year's move doesn't match last year's, it's labeled an
           ANOMALY worth investigating. Read-only, Google Ads API only.

           HONEST LIMITATIONS — check these for each client before relying
           on this for them:
           1. Needs ~13 months of account history (target month + the same
              month and the month before it, both last year). Clients with
              less than that don't qualify for a full YoY comparison; the
              script says so explicitly rather than faking a shorter-window
              comparison. A client returning 0 months of data is a separate
              data-availability question to look into, not a code bug.
           2. Product types / brands / individual products all require a
              Shopping/PMax product feed (`shopping_performance_view`) — a
              client without one can't get these 3 levels regardless of
              history length. Check both conditions (history + feed) before
              promising the full 4-level treatment for a given client.
           3. Even with enough history and a feed, "product types" and
              "brands" can still collapse to a single bucket if the feed's
              product_type_l1/l2/l3 or product_brand fields aren't populated
              with distinguishing values per product line. Real segmentation
              at those 2 levels needs the client to set distinguishing
              values in their feed (e.g. a custom product_type of "Beer" /
              "Distillates" / "Gift Sets"), not something this script can
              fix. "Individual products" is unaffected — item_id/title are
              already granular per SKU.

Usage    : python3 seasonality.py <client_slug> [--month YYYY-MM] [--top 10]
Changelog: 2026-07-25  Initial version.
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

from google.ads.googleads.client import GoogleAdsClient

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"
METRICS = ["cost_micros", "clicks", "conversions", "conversions_value"]


def get_ads_client():
    return GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))


def shift_month(yyyymm, delta):
    year, month = map(int, yyyymm.split("-"))
    total = year * 12 + (month - 1) + delta
    return f"{total // 12}-{total % 12 + 1:02d}"


def month_bounds(yyyymm):
    year, month = map(int, yyyymm.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    return str(start), str(end)


def default_target_month():
    today = date.today()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    return f"{last_month_end.year}-{last_month_end.month:02d}"


def months_needed(target_month):
    return [shift_month(target_month, d) for d in (-13, -12, -1, 0)]


def fetch_campaign_history(ads_client, customer_id, date_from, date_to):
    """entity_key = (campaign_id, campaign_name) -> {month: {metric: value}}"""
    ga_service = ads_client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.id, campaign.name, segments.month,
               metrics.cost_micros, metrics.clicks, metrics.conversions, metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    out = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        key = (str(row.campaign.id), row.campaign.name)
        month = row.segments.month[:7]
        out.setdefault(key, {})[month] = {
            "cost": row.metrics.cost_micros / 1e6, "clicks": row.metrics.clicks,
            "conversions": row.metrics.conversions, "conversions_value": row.metrics.conversions_value,
        }
    return out


def fetch_shopping_history(ads_client, customer_id, date_from, date_to, segment_fields):
    ga_service = ads_client.get_service("GoogleAdsService")
    select_segments = ", ".join(f"segments.{f}" for f in segment_fields)
    query = f"""
        SELECT {select_segments}, segments.month,
               metrics.cost_micros, metrics.clicks, metrics.conversions, metrics.conversions_value
        FROM shopping_performance_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    out = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        key = tuple(getattr(row.segments, f) for f in segment_fields)
        month = row.segments.month[:7]
        out.setdefault(key, {})[month] = {
            "cost": row.metrics.cost_micros / 1e6, "clicks": row.metrics.clicks,
            "conversions": row.metrics.conversions, "conversions_value": row.metrics.conversions_value,
        }
    return out


def account_month_range(ads_client, customer_id):
    ga_service = ads_client.get_service("GoogleAdsService")
    query = """
        SELECT segments.month, metrics.cost_micros
        FROM customer
        WHERE segments.date BETWEEN '2023-01-01' AND '2027-01-01'
        ORDER BY segments.month ASC
    """
    months = [row.segments.month[:7] for row in ga_service.search(customer_id=customer_id, query=query)]
    return months


def classify(mom_this_year, mom_last_year):
    if mom_this_year is None or mom_last_year is None:
        return "n/a — missing a comparison month"
    same_direction = (mom_this_year >= 0) == (mom_last_year >= 0)
    gap = abs(mom_this_year - mom_last_year)
    if same_direction and gap <= 15:
        return "SEASONAL — matches last year's same transition"
    if same_direction and gap <= 30:
        return "MIXED — same direction as last year, but a bigger swing"
    return "ANOMALY — does not match last year's pattern, worth investigating"


def pct_change(cur, prev):
    if prev is None or cur is None or prev == 0:
        return None
    return (cur - prev) / prev * 100


def analyze_entity(history, target_month, metric="cost"):
    prior_month = shift_month(target_month, -1)
    ly_month = shift_month(target_month, -12)
    ly_prior_month = shift_month(target_month, -13)

    cur = history.get(target_month, {}).get(metric)
    prior = history.get(prior_month, {}).get(metric)
    ly = history.get(ly_month, {}).get(metric)
    ly_prior = history.get(ly_prior_month, {}).get(metric)

    mom_this_year = pct_change(cur, prior)
    mom_last_year = pct_change(ly, ly_prior)
    yoy = pct_change(cur, ly)

    return {
        "cur": cur, "prior": prior, "ly": ly, "ly_prior": ly_prior,
        "mom_this_year": mom_this_year, "mom_last_year": mom_last_year, "yoy": yoy,
        "label": classify(mom_this_year, mom_last_year),
    }


def fmt_pct(v):
    return f"{v:+.1f}%" if v is not None else "n/a"


def fmt_money(v, currency=""):
    return f"{v:,.0f} {currency}".strip() if v is not None else "n/a"


def print_table(headers, rows):
    widths = [max(len(str(h)), 10) for h in headers]
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


def check_history_sufficient(available_months, target_month):
    needed = months_needed(target_month)
    missing = [m for m in needed if m not in available_months]
    return missing


def cmd_run(args):
    client_meta = resolve(args.client)
    currency = client_meta.get("currency", "")
    target_month = args.month or default_target_month()
    top_n = args.top

    ads_client = get_ads_client()
    customer_id = client_meta["customer_id"]

    print(f"Client       : {client_meta['name']} ({args.client})")
    print(f"Target month : {target_month}")

    available_months = account_month_range(ads_client, customer_id)
    missing = check_history_sufficient(available_months, target_month)
    if missing:
        print(f"\nNOT ENOUGH HISTORY for a real year-over-year comparison — need data for {', '.join(months_needed(target_month))},")
        print(f"missing: {', '.join(missing)}. This account's data starts {available_months[0] if available_months else 'unknown'}")
        print(f"and has {len(available_months)} month(s) on record. YoY needs ~13 months; re-run once that's available.")
        return

    date_from, _ = month_bounds(months_needed(target_month)[0])
    _, date_to = month_bounds(target_month)

    # --- 1. Campaigns ---
    section("1. Campaigns")
    camp_history = fetch_campaign_history(ads_client, customer_id, date_from, date_to)
    ranked = sorted(camp_history.items(), key=lambda kv: kv[1].get(target_month, {}).get("cost", 0), reverse=True)[:top_n]
    rows = []
    for (cid, cname), hist in ranked:
        r = analyze_entity(hist, target_month, "cost")
        rows.append([cname[:40], fmt_money(r["cur"], currency), fmt_pct(r["mom_this_year"]), fmt_pct(r["mom_last_year"]), fmt_pct(r["yoy"]), r["label"]])
    if rows:
        print_table(["campaign", f"cost ({target_month})", "MoM this yr", "MoM last yr", "YoY", "verdict"], rows)
    else:
        print("No campaign data for this window.")

    # --- 2. Product Types ---
    section("2. Product Types")
    _run_shopping_level(ads_client, customer_id, date_from, date_to, target_month, currency, top_n,
                         segment_fields=["product_type_l1", "product_type_l2", "product_type_l3"],
                         label_fn=lambda k: " > ".join(p for p in k if p) or "(unspecified)")

    # --- 3. Brands ---
    section("3. Brands")
    _run_shopping_level(ads_client, customer_id, date_from, date_to, target_month, currency, top_n,
                         segment_fields=["product_brand"], label_fn=lambda k: k[0] or "(unspecified)")

    # --- 4. Individual Products ---
    section("4. Individual Products")
    _run_shopping_level(ads_client, customer_id, date_from, date_to, target_month, currency, top_n,
                         segment_fields=["product_item_id", "product_title"], label_fn=lambda k: (k[1] or k[0])[:50])


def _run_shopping_level(ads_client, customer_id, date_from, date_to, target_month, currency, top_n, segment_fields, label_fn):
    history = fetch_shopping_history(ads_client, customer_id, date_from, date_to, segment_fields)
    if not history:
        print("No Shopping/PMax product data for this account — this level requires a Merchant Center product feed.")
        return

    distinct_values = len(history)
    if distinct_values <= 1 and len(segment_fields) > 1:
        print(f"Only {distinct_values} distinct value found across this whole account — the feed doesn't set enough")
        print("differentiation on this attribute (e.g. product_type is the same for every SKU) for a meaningful")
        print("comparison. This is a feed data-quality gap, not something this script can work around.")

    ranked = sorted(history.items(), key=lambda kv: kv[1].get(target_month, {}).get("cost", 0), reverse=True)[:top_n]
    rows = []
    for key, hist in ranked:
        r = analyze_entity(hist, target_month, "cost")
        if r["ly"] is None and r["cur"] is not None:
            label = "NEW — no same-month-last-year data to compare"
        else:
            label = r["label"]
        rows.append([label_fn(key), fmt_money(r["cur"], currency), fmt_pct(r["mom_this_year"]), fmt_pct(r["mom_last_year"]), fmt_pct(r["yoy"]), label])
    if rows:
        print_table(["entity", f"cost ({target_month})", "MoM this yr", "MoM last yr", "YoY", "verdict"], rows)


def main():
    parser = argparse.ArgumentParser(description="Year-over-year seasonality analysis across 4 levels")
    parser.add_argument("client")
    parser.add_argument("--month", help="Target month as YYYY-MM (default: most recently completed month)")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--pdf", action="store_true", help="Also write a branded PDF to clients/<slug>/reports/")
    parser.set_defaults(func=cmd_run)
    args = parser.parse_args()

    if args.pdf:
        from text_report_pdf import capture_stdout, render_text_report
        client_meta = resolve(args.client)
        text = capture_stdout(args.func, args)
        reports_dir = Path(__file__).resolve().parent.parent / "clients" / client_meta["slug"] / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = reports_dir / f"seasonality_{args.month or date.today().isoformat()}.pdf"
        render_text_report(client_meta, "Seasonality Analysis", text, pdf_path)
        print(f"\nPDF written: {pdf_path}")
    else:
        args.func(args)


if __name__ == "__main__":
    main()
