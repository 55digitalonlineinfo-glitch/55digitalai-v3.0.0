#!/usr/bin/env python3
"""
55DigitalAI — Daily Account Pulse-Check
=============================================================
Purpose  : Fast read-only health check for one client's Google Ads account:
           conversion tracking sanity (did it drop to zero unexpectedly),
           budget pacing (under-spending / budget-limited campaigns), and
           cost/CPA anomalies vs a trailing baseline. Flags near public
           holidays are annotated, not suppressed — numbers still print so
           a human can judge.

           Read-only. Makes zero changes to the account.

Usage    : python3 scripts/daily_check.py <client_slug> [--check-days 4] [--baseline-days 14]
Changelog: 2026-07-18  Initial version
           2026-11-12  Section 2 adds an impression-share split per Search campaign
                       (won / lost to budget / lost to rank, weighted by eligible
                       impressions) so budget- vs rank-limited is visible. The
                       budget-limited flag uses the same share. Window totals come
                       from an un-segmented query (exact), not from daily averages.
           2026-07-18  Budget pacing switched from per-campaign daily-budget %
                       to account-level month-to-date spend vs. monthly_budget
                       (client_registry.py), compared against expected pace.
           2026-07-18  Conversion tracking now also flags partial swings (not
                       just drop-to-zero): conversion volume and conversion
                       value % change vs. baseline, both gated on a minimum
                       baseline conversion rate to avoid noise.
           2026-07-18  Each run now appends to clients/<slug>/reports/daily_check_
                       YYYY-MM-DD.log (in addition to stdout), matching the
                       audit scripts' report convention.
           2026-07-18  Fixed conversion metric: was using metrics.all_conversions
                       (includes every secondary/page-view action regardless of
                       "include in conversions" setting), switched to
                       metrics.conversions to match the Ads UI "Conversions" column.
           2026-07-18  Added account-level CONVERSION TREND section: a per-day
                       breakdown over --trend-days, plus check-window vs.
                       previous-period comparison. Ecommerce clients
                       (business_type in client_registry.py) get conversion
                       value + ROAS by day; lead-gen clients get conversion
                       count only.
           2026-07-18  Conversion-value anomaly check in CONVERSION TRACKING
                       now only runs for ecommerce clients (business_type) —
                       conversion value isn't a meaningful signal for lead-gen.
           2026-07-18  Budget pacing's required-daily-spend recommendation now
                       compares against yesterday's actual spend (freshest
                       single day) instead of the MTD average, since that's
                       what should drive a same-day budget adjustment.
           2026-07-18  CONVERSION TRACKING now checks a fixed 4-day window
                       (CONV_CHECK_DAYS), independent of --check-days which
                       still controls budget-pacing/cost-CPA sections — 2 days
                       was too short and produced noisy flags on low-volume
                       campaigns (near-even odds of a false zero by chance).
           2026-07-18  Conversion/conv.-value swing flags in CONVERSION TRACKING
                       are now one-directional — only a drop vs. baseline gets
                       flagged. An increase in conversions or conversion value
                       is good news, not something to alert on.
           2026-07-19  CPA anomaly flag is now one-directional — only a rise
                       vs. baseline gets flagged. A CPA drop is good news.
           2026-07-19  Default --check-days raised from 2 to 4, matching
                       CONV_CHECK_DAYS. 2 days was noisy for the cost/CPA
                       section for the same reason it was noisy for
                       conversion tracking — a single unlucky/lucky day could
                       swing the average enough to false-flag.
"""

import argparse
import calendar
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

# Manually maintained — small enough to not warrant an API. Add years as needed.
PUBLIC_HOLIDAYS = {
    "PL": {
        "2026-01-01", "2026-01-06", "2026-04-05", "2026-04-06", "2026-05-01",
        "2026-05-03", "2026-05-24", "2026-06-04", "2026-08-15", "2026-11-01",
        "2026-11-11", "2026-12-25", "2026-12-26",
    },
    "UA": {
        "2026-01-01", "2026-01-07", "2026-03-08", "2026-05-01", "2026-05-09",
        "2026-06-28", "2026-08-24", "2026-10-14", "2026-12-25",
    },
}

COST_ANOMALY_PCT = 50.0
CPA_ANOMALY_PCT = 50.0
CONV_ANOMALY_PCT = 50.0
CONV_VALUE_ANOMALY_PCT = 50.0
LOST_IS_BUDGET_PCT = 20.0
API_TIMEOUT_S = 90  # per Google Ads call; a hung gRPC call once blocked every client for weeks
MIN_BASELINE_CONVERSIONS = 0.3  # per day, over the whole baseline window
CONV_CHECK_DAYS = 4  # conversion tracking uses its own (wider) window, independent of --check-days
MONTHLY_PACE_TOLERANCE_PP = 15.0  # percentage points actual pace may deviate from expected pace


def micros(v):
    return v / 1_000_000


def pct_change(new, old):
    if old == 0:
        return None
    return (new - old) / old * 100


def fetch_rows(client_meta, check_days, baseline_days):
    from google.ads.googleads.client import GoogleAdsClient

    ga_client = GoogleAdsClient.load_from_storage("google-ads.yaml")
    ga = ga_client.get_service("GoogleAdsService")

    today = datetime.utcnow().date()
    date_from = today - timedelta(days=check_days + baseline_days)
    date_to = today - timedelta(days=1)  # exclude today (partial day)
    month_start = today.replace(day=1)
    date_from = min(date_from, month_start)  # guarantee full month-to-date coverage for the trend section

    query = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign_budget.amount_micros,
               segments.date,
               metrics.cost_micros, metrics.clicks, metrics.impressions,
               metrics.conversions, metrics.conversions_value,
               metrics.search_budget_lost_impression_share,
               metrics.search_rank_lost_impression_share,
               metrics.search_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
          AND campaign.status = 'ENABLED'
        ORDER BY campaign.name, segments.date
    """
    rows = list(ga.search(customer_id=client_meta["customer_id"], query=query, timeout=API_TIMEOUT_S))

    # Month-vs-month: this month-to-date (day 1 -> yesterday) vs. the same day-of-month
    # range last month, e.g. running on the 19th compares 01-18 this month to 01-18 last month.
    day_offset = (date_to - month_start).days
    last_month_last_day = month_start - timedelta(days=1)
    last_month_start = last_month_last_day.replace(day=1)
    last_month_days = (last_month_last_day - last_month_start).days + 1
    last_month_to = last_month_start + timedelta(days=min(day_offset, last_month_days - 1))

    cmp_query = f"""
        SELECT segments.date, metrics.cost_micros, metrics.conversions, metrics.conversions_value
        FROM customer
        WHERE segments.date BETWEEN '{last_month_start}' AND '{date_to}'
    """
    cmp_rows = list(ga.search(customer_id=client_meta["customer_id"], query=cmp_query, timeout=API_TIMEOUT_S))
    this_month = {"cost": 0.0, "conv": 0.0, "conv_value": 0.0}
    last_month = {"cost": 0.0, "conv": 0.0, "conv_value": 0.0}
    for r in cmp_rows:
        d = datetime.strptime(r.segments.date, "%Y-%m-%d").date()
        bucket = this_month if d >= month_start else (last_month if d <= last_month_to else None)
        if bucket is None:
            continue
        bucket["cost"] += micros(r.metrics.cost_micros)
        bucket["conv"] += r.metrics.conversions
        bucket["conv_value"] += r.metrics.conversions_value
    mtd_spend = this_month["cost"]
    month_comparison = {
        "this_from": month_start, "this_to": date_to,
        "last_from": last_month_start, "last_to": last_month_to,
        "this": this_month, "last": last_month,
    }

    # Impression share for the whole check window, aggregated by Google itself (no date
    # segment) - exact, unlike averaging the rounded daily ratios.
    check_from = today - timedelta(days=check_days)
    is_query = f"""
        SELECT campaign.name, metrics.impressions, metrics.search_impression_share,
               metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{check_from}' AND '{date_to}'
          AND campaign.status = 'ENABLED'
          AND campaign.advertising_channel_type = 'SEARCH'
    """
    month_comparison["impression_share"] = {
        r.campaign.name: (r.metrics.search_impression_share, r.metrics.search_budget_lost_impression_share,
                          r.metrics.search_rank_lost_impression_share)
        for r in ga.search(customer_id=client_meta["customer_id"], query=is_query, timeout=API_TIMEOUT_S)
        if r.metrics.impressions and r.metrics.search_impression_share
    }

    return rows, date_from, date_to, mtd_spend, month_start, month_comparison


def build_report(client_meta, rows, date_from, date_to, check_days, baseline_days, mtd_spend, month_start, trend_days, month_comparison=None):
    today = datetime.utcnow().date()
    check_start = today - timedelta(days=check_days)

    by_campaign = defaultdict(lambda: {"baseline": [], "check": [], "budget": None, "status": None})
    by_date = defaultdict(lambda: {"conv": 0.0, "conv_value": 0.0, "cost": 0.0})
    for r in rows:
        name = r.campaign.name
        d = datetime.strptime(r.segments.date, "%Y-%m-%d").date()
        entry = {
            "date": d, "cost": micros(r.metrics.cost_micros),
            "conv": r.metrics.conversions, "conv_value": r.metrics.conversions_value,
            "clicks": r.metrics.clicks, "impressions": r.metrics.impressions,
            "lost_is_budget": r.metrics.search_budget_lost_impression_share,
            "lost_is_rank": r.metrics.search_rank_lost_impression_share,
            "is_won": r.metrics.search_impression_share,
        }
        by_campaign[name]["budget"] = micros(r.campaign_budget.amount_micros)
        if d >= check_start:
            by_campaign[name]["check"].append(entry)
        else:
            by_campaign[name]["baseline"].append(entry)

        by_date[d]["conv"] += entry["conv"]
        by_date[d]["conv_value"] += entry["conv_value"]
        by_date[d]["cost"] += entry["cost"]

    holidays = PUBLIC_HOLIDAYS.get(client_meta["country"], set())
    check_window_dates = {(check_start + timedelta(days=i)).isoformat() for i in range((today - check_start).days)}
    holidays_in_window = sorted(check_window_dates & holidays)

    lines = []
    lines.append("=" * 60)
    lines.append(f"  Daily Pulse-Check: {client_meta['name']}")
    lines.append(f"  Check window   : {check_start} → {date_to} ({check_days}d)")
    lines.append(f"  Baseline window: {date_from} → {check_start - timedelta(days=1)} ({baseline_days}d)")
    if holidays_in_window:
        lines.append(f"  NOTE: public holiday(s) in check window: {', '.join(holidays_in_window)} — low traffic may be expected")
    lines.append("=" * 60)

    flags = 0
    business_type = client_meta.get("business_type", "lead_gen")

    conv_check_start = date_to - timedelta(days=CONV_CHECK_DAYS - 1)
    if conv_check_start < date_from:
        conv_check_start = date_from

    lines.append(f"\n## 1. CONVERSION TRACKING (last {CONV_CHECK_DAYS} days vs. prior {baseline_days}-day baseline)")
    campaign_blocks = []
    n_steady = n_low_volume = n_flagged = 0
    for name, d in sorted(by_campaign.items()):
        all_entries = d["baseline"] + d["check"]
        conv_check_entries = [e for e in all_entries if e["date"] >= conv_check_start]
        conv_baseline_entries = [e for e in all_entries if e["date"] < conv_check_start]

        baseline_days_n = len(conv_baseline_entries) or 1
        check_days_n = len(conv_check_entries) or 1
        baseline_conv_total = sum(e["conv"] for e in conv_baseline_entries)
        baseline_conv_per_day = baseline_conv_total / baseline_days_n
        check_conv_total = sum(e["conv"] for e in conv_check_entries)
        check_conv_per_day = check_conv_total / check_days_n

        block = [
            f"  {name}",
            f"    Prior {baseline_days} days average: {baseline_conv_per_day:.2f} conversions/day",
            f"    Last {CONV_CHECK_DAYS} days   : {check_conv_per_day:.2f} conversions/day ({check_conv_total:.0f} total)",
        ]

        if baseline_conv_per_day < MIN_BASELINE_CONVERSIONS:
            block.append(f"    [OK] Low volume — under {MIN_BASELINE_CONVERSIONS:.1f}/day baseline, not enough data for a reliable comparison.")
            n_low_volume += 1
            campaign_blocks.append(block)
            continue

        if check_conv_total == 0:
            block.append(f"    [FLAG] Dropped to zero over the last {CONV_CHECK_DAYS} days — possible tracking break.")
            flags += 1
            n_flagged += 1
            campaign_blocks.append(block)
            continue

        note = []
        conv_delta = pct_change(check_conv_per_day, baseline_conv_per_day)
        if conv_delta is not None and conv_delta <= -CONV_ANOMALY_PCT:
            note.append(f"conversions down {abs(conv_delta):.0f}% vs the prior {baseline_days} days average")

        if business_type == "ecommerce":
            baseline_value_per_day = sum(e["conv_value"] for e in conv_baseline_entries) / baseline_days_n
            check_value_per_day = sum(e["conv_value"] for e in conv_check_entries) / check_days_n
            value_delta = pct_change(check_value_per_day, baseline_value_per_day)
            if value_delta is not None and value_delta <= -CONV_VALUE_ANOMALY_PCT:
                note.append(f"conversion value down {abs(value_delta):.0f}% vs the prior {baseline_days} days average")

        if note:
            block.append(f"    [FLAG] {'; '.join(note)}.")
            flags += 1
            n_flagged += 1
        else:
            block.append(f"    [OK] Steady — in line with the prior {baseline_days} days average.")
            n_steady += 1
        campaign_blocks.append(block)

    summary_bits = []
    if n_steady:
        summary_bits.append(f"{n_steady} steady")
    if n_flagged:
        summary_bits.append(f"{n_flagged} flagged")
    if n_low_volume:
        summary_bits.append(f"{n_low_volume} low volume")
    lines.append(f"  Summary: {len(campaign_blocks)} campaigns checked — {', '.join(summary_bits)}.")
    for block in campaign_blocks:
        lines.extend(block)

    lines.append("\n## 2. BUDGET PACING")
    currency = client_meta.get("currency", "")
    monthly_budget = client_meta.get("monthly_budget")
    if monthly_budget:
        days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
        days_elapsed = (date_to - month_start).days + 1
        expected_pct = days_elapsed / days_in_month * 100
        actual_pct = mtd_spend / monthly_budget * 100
        delta = actual_pct - expected_pct

        lines.append(f"  Monthly budget: {monthly_budget:.2f} {currency}")
        lines.append(f"  Spent so far  : {mtd_spend:.2f} {currency} ({actual_pct:.0f}% of budget)")
        lines.append(f"  Days elapsed  : {days_elapsed} of {days_in_month} (expected ~{expected_pct:.0f}% spent by now)")
        if abs(delta) > MONTHLY_PACE_TOLERANCE_PP:
            direction = "Under-pacing" if delta < 0 else "Over-pacing"
            lines.append(f"  [FLAG] {direction} — {abs(delta):.0f} percentage points off the expected pace.")
            flags += 1
        else:
            lines.append("  [OK] On pace — within the expected range for this point in the month.")

        lines.append("")
        remaining_days = days_in_month - days_elapsed
        remaining_budget = monthly_budget - mtd_spend
        yesterday_spend = by_date.get(date_to, {"cost": 0.0})["cost"]
        if remaining_days > 0:
            lines.append(f"  Remaining days  : {remaining_days}")
            lines.append(f"  Remaining budget: {remaining_budget:.2f} {currency}")
            if remaining_budget < 0:
                lines.append(f"  [INFO] Already over budget by {abs(remaining_budget):.2f} {currency} with {remaining_days} days left — consider pausing or cutting daily spend.")
            else:
                required_daily = remaining_budget / remaining_days
                pace_delta = required_daily - yesterday_spend
                direction2 = "Increase" if pace_delta > 0 else "Decrease"
                lines.append(f"  Required pace   : {required_daily:.2f} {currency}/day to land on budget by month-end (yesterday spent {yesterday_spend:.2f} {currency})")
                lines.append(f"  [INFO] {direction2} daily spend by {abs(pace_delta):.2f} {currency}/day to stay on pace.")
        else:
            lines.append(f"  [INFO] Last day of the month — spend will land at ~{mtd_spend:.2f} {currency} ({actual_pct:.0f}% of budget).")
    else:
        lines.append("  [OK] No monthly budget configured for this client — add one in client_registry.py to enable this check.")

    # Impression share split per Search campaign over the check window, weighted by
    # eligible impressions (impressions / impression share) so busy days count more.
    # won + lost to budget + lost to rank ~= 100%. Non-Search campaigns report 0 and are skipped.
    is_split = []
    is_agg = (month_comparison or {}).get("impression_share")
    if is_agg is not None:
        # exact window totals straight from Google (see fetch_rows)
        for name, (won, lost_b, lost_r) in sorted(is_agg.items()):
            is_split.append((name, won * 100, (lost_b or 0) * 100, (lost_r or 0) * 100))
    else:
        for name, d in sorted(by_campaign.items()):
            eligible = won = lost_b = lost_r = 0.0
            for e in d["check"]:
                if e["is_won"] and e["impressions"]:
                    elig = e["impressions"] / e["is_won"]
                    eligible += elig
                    won += e["impressions"]
                    lost_b += elig * (e["lost_is_budget"] or 0)
                    lost_r += elig * (e["lost_is_rank"] or 0)
            if eligible:
                is_split.append((name, won / eligible * 100, lost_b / eligible * 100, lost_r / eligible * 100))

    for name, won_pct, lost_b_pct, lost_r_pct in is_split:
        if lost_b_pct > LOST_IS_BUDGET_PCT:
            lines.append(f"\n  {name}")
            lines.append(f"    Impression share lost to budget limits: {lost_b_pct:.0f}%")
            lines.append(f"    Impression share lost to ad rank: {lost_r_pct:.0f}%")
            lines.append("    [FLAG] This campaign could spend more if its budget allowed.")
            flags += 1

    if is_split:
        lines.append(f"\n  Impression share split (last {check_days} days, Search campaigns):")
        for name, won_pct, lost_b_pct, lost_r_pct in is_split:
            lines.append(f"    IS | {name} | won {won_pct:.0f}% | lost to budget {lost_b_pct:.0f}% | lost to rank {lost_r_pct:.0f}%")

    lines.append(f"\n## 3. COST / CPA ANOMALIES (last {check_days} days vs. prior {baseline_days}-day baseline)")
    campaign_blocks = []
    n_steady = n_flagged = 0
    for name, d in sorted(by_campaign.items()):
        baseline_days_n = len(d["baseline"]) or 1
        check_days_n = len(d["check"]) or 1
        baseline_cost_avg = sum(e["cost"] for e in d["baseline"]) / baseline_days_n
        check_cost_avg = sum(e["cost"] for e in d["check"]) / check_days_n
        cost_delta = pct_change(check_cost_avg, baseline_cost_avg)

        baseline_conv = sum(e["conv"] for e in d["baseline"])
        check_conv = sum(e["conv"] for e in d["check"])
        baseline_cpa = (sum(e["cost"] for e in d["baseline"]) / baseline_conv) if baseline_conv > 0 else None
        check_cpa = (sum(e["cost"] for e in d["check"]) / check_conv) if check_conv > 0 else None
        cpa_delta = pct_change(check_cpa, baseline_cpa) if (baseline_cpa and check_cpa) else None

        block = [f"  {name}"]
        block.append(f"    Daily cost: {baseline_cost_avg:.2f} {currency}/day (prior {baseline_days} days avg) → {check_cost_avg:.2f} {currency}/day (last {check_days} days)")
        if baseline_cpa is not None and check_cpa is not None:
            block.append(f"    CPA       : {baseline_cpa:.2f} {currency} (prior {baseline_days} days avg) → {check_cpa:.2f} {currency} (last {check_days} days)")
        else:
            block.append("    CPA       : not enough conversions in one of the windows to compute")

        note = []
        cost_up_suppressed = (
            cost_delta is not None and cost_delta > 0
            and cpa_delta is not None and cpa_delta <= 0
        )
        if cost_delta is not None and abs(cost_delta) >= COST_ANOMALY_PCT and not cost_up_suppressed:
            note.append(f"cost {'up' if cost_delta > 0 else 'down'} {abs(cost_delta):.0f}%")
        if cpa_delta is not None and cpa_delta >= CPA_ANOMALY_PCT:
            note.append(f"CPA up {cpa_delta:.0f}%")

        if note:
            block.append(f"    [FLAG] {'; '.join(note)} vs the prior {baseline_days} days average.")
            flags += 1
            n_flagged += 1
        elif cost_up_suppressed and abs(cost_delta) >= COST_ANOMALY_PCT:
            block.append(f"    [OK] Cost up {cost_delta:.0f}% but CPA improved {abs(cpa_delta):.0f}% — looks like scaling, not flagged.")
            n_steady += 1
        else:
            block.append(f"    [OK] Steady — in line with the {baseline_days}-day average.")
            n_steady += 1
        campaign_blocks.append(block)

    summary_bits = []
    if n_steady:
        summary_bits.append(f"{n_steady} steady")
    if n_flagged:
        summary_bits.append(f"{n_flagged} flagged")
    lines.append(f"  Summary: {len(campaign_blocks)} campaigns checked — {', '.join(summary_bits)}.")
    for block in campaign_blocks:
        lines.extend(block)

    if trend_days is None:
        trend_start = month_start
    else:
        trend_start = max(date_to - timedelta(days=trend_days - 1), date_from)
    trend_label = "month-to-date" if trend_days is None else f"last {trend_days}d"
    lines.append(f"\n## 4. CONVERSION TREND ({trend_label}, account-level)")
    d = trend_start
    while d <= date_to:
        day = by_date.get(d, {"conv": 0.0, "conv_value": 0.0, "cost": 0.0})
        if business_type == "ecommerce":
            roas = (day["conv_value"] / day["cost"]) if day["cost"] > 0 else None
            roas_str = f"{roas:.2f}" if roas is not None else "n/a"
            lines.append(f"  {d.strftime('%d.%m')} - conv {day['conv']:.1f} | value {day['conv_value']:.2f} | cost {day['cost']:.2f} | ROAS {roas_str}")
        else:
            lines.append(f"  {d.strftime('%d.%m')} - {day['conv']:.1f} conv")
        d += timedelta(days=1)

    prev_start = check_start - timedelta(days=check_days)
    prev_end = check_start - timedelta(days=1)

    def sum_range(start, end):
        totals = {"conv": 0.0, "conv_value": 0.0, "cost": 0.0}
        dd = start
        while dd <= end:
            day = by_date.get(dd, {"conv": 0.0, "conv_value": 0.0, "cost": 0.0})
            for k in totals:
                totals[k] += day[k]
            dd += timedelta(days=1)
        return totals

    check_totals = sum_range(check_start, date_to)
    prev_totals = sum_range(prev_start, prev_end)

    lines.append(f"  Check window ({check_start} → {date_to}) vs. previous period ({prev_start} → {prev_end}):")
    if business_type == "ecommerce":
        v_delta = pct_change(check_totals["conv_value"], prev_totals["conv_value"])
        v_delta_str = f" ({'+' if v_delta > 0 else ''}{v_delta:.0f}%)" if v_delta is not None else ""
        lines.append(f"    Conv. value : {prev_totals['conv_value']:.2f} → {check_totals['conv_value']:.2f}{v_delta_str}")

        check_roas = (check_totals["conv_value"] / check_totals["cost"]) if check_totals["cost"] > 0 else None
        prev_roas = (prev_totals["conv_value"] / prev_totals["cost"]) if prev_totals["cost"] > 0 else None
        roas_delta = pct_change(check_roas, prev_roas) if (check_roas is not None and prev_roas is not None) else None
        roas_delta_str = f" ({'+' if roas_delta > 0 else ''}{roas_delta:.0f}%)" if roas_delta is not None else ""
        prev_roas_str = f"{prev_roas:.2f}" if prev_roas is not None else "n/a"
        check_roas_str = f"{check_roas:.2f}" if check_roas is not None else "n/a"
        lines.append(f"    ROAS        : {prev_roas_str} → {check_roas_str}{roas_delta_str}")
    else:
        c_delta = pct_change(check_totals["conv"], prev_totals["conv"])
        c_delta_str = f" ({'+' if c_delta > 0 else ''}{c_delta:.0f}%)" if c_delta is not None else ""
        lines.append(f"    Conversions : {prev_totals['conv']:.1f} → {check_totals['conv']:.1f}{c_delta_str}")

    lines.append("\n## 5. SUMMARY")
    lines.append(f"  Campaigns checked : {len(by_campaign)}")
    lines.append(f"  Flags raised      : {flags}")
    lines.append(f"  Mode              : READ-ONLY — zero changes made")

    if month_comparison:
        mc = month_comparison
        lines.append(
            f"\n## 6. MONTH VS. MONTH ({mc['this_from']} → {mc['this_to']} vs. "
            f"{mc['last_from']} → {mc['last_to']}, same day-of-month range)"
        )
        cost_delta = pct_change(mc["this"]["cost"], mc["last"]["cost"])
        cost_delta_str = f" ({'+' if cost_delta > 0 else ''}{cost_delta:.0f}%)" if cost_delta is not None else ""
        if business_type == "ecommerce":
            lines.append(f"  Cost   : {mc['last']['cost']:.2f} → {mc['this']['cost']:.2f} {currency}{cost_delta_str}")
            rev_delta = pct_change(mc["this"]["conv_value"], mc["last"]["conv_value"])
            rev_delta_str = f" ({'+' if rev_delta > 0 else ''}{rev_delta:.0f}%)" if rev_delta is not None else ""
            lines.append(f"  Revenue: {mc['last']['conv_value']:.2f} → {mc['this']['conv_value']:.2f} {currency}{rev_delta_str}")
            this_roas = (mc["this"]["conv_value"] / mc["this"]["cost"]) if mc["this"]["cost"] > 0 else None
            last_roas = (mc["last"]["conv_value"] / mc["last"]["cost"]) if mc["last"]["cost"] > 0 else None
            roas_delta = pct_change(this_roas, last_roas) if (this_roas is not None and last_roas is not None) else None
            roas_delta_str = f" ({'+' if roas_delta > 0 else ''}{roas_delta:.0f}%)" if roas_delta is not None else ""
            last_roas_str = f"{last_roas:.2f}" if last_roas is not None else "n/a"
            this_roas_str = f"{this_roas:.2f}" if this_roas is not None else "n/a"
            lines.append(f"  ROAS   : {last_roas_str} → {this_roas_str}{roas_delta_str}")
        else:
            lines.append(f"  Cost       : {mc['last']['cost']:.2f} → {mc['this']['cost']:.2f} {currency}{cost_delta_str}")
            conv_delta = pct_change(mc["this"]["conv"], mc["last"]["conv"])
            conv_delta_str = f" ({'+' if conv_delta > 0 else ''}{conv_delta:.0f}%)" if conv_delta is not None else ""
            lines.append(f"  Conversions: {mc['last']['conv']:.1f} → {mc['this']['conv']:.1f}{conv_delta_str}")

    lines.append("=" * 60)

    return "\n".join(lines), flags


def main():
    parser = argparse.ArgumentParser(description="Daily Google Ads account pulse-check (read-only)")
    parser.add_argument("client", help="Client slug (e.g. acme) or raw customer_id")
    parser.add_argument("--check-days", type=int, default=4, help="Most recent N complete days to evaluate (default: 4)")
    parser.add_argument("--baseline-days", type=int, default=14, help="Prior comparison window in days (default: 14)")
    parser.add_argument("--trend-days", type=int, default=None, help="Days shown in the daily conversion-trend breakdown (default: full month-to-date)")
    parser.add_argument("--pdf", action="store_true", help="Also write a branded PDF of this report to clients/<slug>/reports/")
    args = parser.parse_args()

    try:
        client_meta = resolve(args.client)
    except KeyError as e:
        print(str(e).strip('"'))
        sys.exit(2)

    rows, date_from, date_to, mtd_spend, month_start, month_comparison = fetch_rows(client_meta, args.check_days, args.baseline_days)
    report, flags = build_report(client_meta, rows, date_from, date_to, args.check_days, args.baseline_days, mtd_spend, month_start, args.trend_days, month_comparison)
    print(report)

    workspace_root = Path(__file__).resolve().parent.parent
    reports_dir = workspace_root / "clients" / client_meta["slug"] / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / f"daily_check_{date.today().isoformat()}.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[Run at {datetime.now().isoformat(timespec='seconds')}]\n")
        f.write(report + "\n")

    if args.pdf:
        from text_report_pdf import render_text_report
        pdf_path = reports_dir / f"daily_check_{date.today().isoformat()}.pdf"
        render_text_report(client_meta, "Daily Pulse-Check", report, pdf_path)
        print(f"\nPDF written: {pdf_path}")

    sys.exit(1 if flags > 0 else 0)


if __name__ == "__main__":
    main()
