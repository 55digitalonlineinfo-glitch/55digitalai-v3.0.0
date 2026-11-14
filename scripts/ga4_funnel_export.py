#!/usr/bin/env python3
"""
55DigitalAI — GA4 Funnel Exploration Export
=============================================================
Purpose  : Pull a real ecommerce purchase funnel (session_start -> view_item
           -> add_to_cart -> begin_checkout -> purchase) from GA4's Funnel
           Exploration API (runFunnelReport, v1alpha) for a given client and
           date range, with a device-category breakdown per step, and write
           it as clean JSON — meant to be embedded directly into a client
           report (the CRO audit PDF picks it up automatically).

           Uses runFunnelReport, not the regular runReport endpoint used by
           ga4_reports.py — funnel step completion/abandonment rates require
           GA4's own ordered/session-aware funnel matching, which a plain
           eventName event-count report cannot reproduce (raw event counts
           don't enforce step order and can double-count within a session).

Auth     : Same OAuth pattern as ga4_reports.py / drive_deck.py — reuses the
           refresh_token/client_id/client_secret in google-ads.yaml (the
           analytics.readonly scope was already granted on that token).

Usage    : python3 scripts/ga4_funnel_export.py <client_slug> \
               [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--out path.json]
           Defaults to the previous calendar month if --start/--end omitted.

Changelog: 2026-09-11  Initial version — built so a client report's funnel section pulls real
           GA4 data instead of being retyped by hand.
"""

import argparse
import calendar
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"
GA4_DATA_API_ALPHA = "https://analyticsdata.googleapis.com/v1alpha"

FUNNEL_STEPS = [
    ("Session start", "session_start"),
    ("View product", "view_item"),
    ("Add to cart", "add_to_cart"),
    ("Begin checkout", "begin_checkout"),
    ("Purchase", "purchase"),
]


def _previous_month_range(today=None):
    today = today or date.today()
    first_of_this_month = today.replace(day=1)
    last_day_prev = first_of_this_month - timedelta(days=1)
    first_day_prev = last_day_prev.replace(day=1)
    return first_day_prev.isoformat(), last_day_prev.isoformat()


def get_credentials():
    cfg = yaml.safe_load(GOOGLE_ADS_YAML.read_text())
    creds = Credentials(
        token=None, refresh_token=cfg["refresh_token"],
        client_id=cfg["client_id"], client_secret=cfg["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return creds


def run_funnel_report(property_id, headers, date_from, date_to, breakdown_dimension="deviceCategory"):
    body = {
        "dateRanges": [{"startDate": date_from, "endDate": date_to}],
        "funnel": {
            "isOpenFunnel": True,
            "steps": [
                {"name": name, "filterExpression": {"funnelEventFilter": {"eventName": event}}}
                for name, event in FUNNEL_STEPS
            ],
        },
        "funnelBreakdown": {"breakdownDimension": {"name": breakdown_dimension}},
    }
    r = requests.post(f"{GA4_DATA_API_ALPHA}/properties/{property_id}:runFunnelReport", headers=headers, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"GA4 runFunnelReport error {r.status_code}: {r.text[:800]}")
    return r.json()


def parse_funnel_table(raw):
    """Returns [{name, users, completion_rate, abandon_count, abandon_rate, breakdown:{device: {...}}}]"""
    rows = raw.get("funnelTable", {}).get("rows", [])
    steps = {}
    order = []
    for row in rows:
        step_name = row["dimensionValues"][0]["value"]
        device = row["dimensionValues"][1]["value"]
        users, completion_rate, abandon_count, abandon_rate = (v["value"] for v in row["metricValues"])
        entry = {
            "users": int(users),
            "completion_rate": round(float(completion_rate), 4),
            "abandon_count": int(abandon_count),
            "abandon_rate": round(float(abandon_rate), 4),
        }
        if step_name not in steps:
            steps[step_name] = {"name": step_name, "breakdown": {}}
            order.append(step_name)
        if device == "RESERVED_TOTAL":
            steps[step_name].update(entry)
        else:
            steps[step_name]["breakdown"][device] = entry
    return [steps[name] for name in order]


def cmd_run(args):
    client = resolve(args.client)
    property_id = client.get("ga4_property_id")
    if not property_id:
        print(f"'{args.client}' has no ga4_property_id in clients.json")
        sys.exit(1)

    if args.start and args.end:
        date_from, date_to = args.start, args.end
    else:
        date_from, date_to = _previous_month_range()

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

    raw = run_funnel_report(property_id, headers, date_from, date_to)
    steps = parse_funnel_table(raw)

    output = {
        "client": args.client,
        "property_id": property_id,
        "date_from": date_from,
        "date_to": date_to,
        "steps": steps,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("client")
    parser.add_argument("--start", help="YYYY-MM-DD (default: 1st of previous month)")
    parser.add_argument("--end", help="YYYY-MM-DD (default: last day of previous month)")
    parser.add_argument("--out", help="Write JSON to this path instead of stdout")
    parser.set_defaults(func=cmd_run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
