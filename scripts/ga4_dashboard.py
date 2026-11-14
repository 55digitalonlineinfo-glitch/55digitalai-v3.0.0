#!/usr/bin/env python3
"""
55DigitalAI — GA4 Client Dashboard (HTML)
=============================================================
Purpose  : Turns every applicable report from ga4_reports.py's REPORTS
           library into a single self-contained, client-facing HTML page
           for one client — KPI tiles / charts / tables instead of
           terminal text — so the client can look at this directly
           instead of texting the agency a question each time. Read-only,
           reuses ga4_reports.py's report definitions and API plumbing
           without modifying that file.

           Captions and anomaly flags embedded in this dashboard are
           simple, deterministic derived-stats (direction/magnitude of
           change, top-row share of total, funnel stage-ordering checks)
           computed once here in Python — NOT analyst judgment about
           whether a number is good or bad in context. They exist to save
           the reader from re-deriving basic arithmetic by hand, nothing
           more.

Usage    : python3 ga4_dashboard.py <client_slug> [--days 30] [--limit 20] [--out path]
                                     [--conversion-event NAME[,NAME2,...]]
           python3 ga4_dashboard.py <client_slug> --list-events [--days 30]
Output   : clients/<slug>/reports/ga4_dashboard_<YYYY-MM-DD>.html (default)
Changelog: 2026-07-27  Initial version — 43 reports classified into 4
                       rendering shapes (kpi/trend/bar_table/table_only)
                       purely from their existing REPORTS config; visual
                       language ported from dashboard_template.html for
                       consistency with the toolkit's other dashboard.
           2026-07-27  Added --list-events / --conversion-event: GA4's native
                       "conversions" metric is a raw count of every event
                       marked a "key event" in the property, not unique
                       conversions — on a real client this meant view_item +
                       view_item_list (pure browsing) made up 84% of the
                       reported total, with actual purchases under 1%.
                       --list-events shows the real per-event breakdown plus
                       a recommended pick; --conversion-event overrides every
                       report using the "conversions" metric to instead count
                       only the chosen event(s), via ga4_reports.py's existing
                       event_filter mechanism (no changes to that file).
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ga4_reports import REPORTS, run_report, get_credentials, format_dim_value  # noqa: E402
from client_registry import resolve  # noqa: E402
from brand import AGENCY_NAME  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "ga4_dashboard_template.html"

TREND_DIMENSIONS = {"date", "hour", "dayOfWeek"}
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# The two strictly-ordered ecommerce funnels — each stage's count should never exceed the
# previous stage's. A violation is a real, recurring GA4 data-quality pattern (e.g. begin_checkout
# firing without a preceding add_to_cart, or firing multiple times per session), worth flagging
# automatically rather than needing a human to notice it by hand every time.
FUNNEL_CHECKS = {
    "purchase_funnel": ["itemsViewed", "itemsAddedToCart", "itemsCheckedOut", "itemsPurchased"],
    "ecommerce_funnel_by_channel": ["sessions", "addToCarts", "checkouts", "ecommercePurchases"],
}

# For --conversion-event's recommendation: a starter list, extend as new clients surface new
# naming patterns — same "documented list, never silently trusted" philosophy as
# feed_title_optimizer.py's KNOWN_BAD_TERMS. Always shown alongside the FULL real event list so
# a human can override the guess, never presented as a decision made for them.
KNOWN_STRONG_CONVERSION_EVENTS = ["purchase", "generate_lead", "submit_lead_form", "form_submit"]
KNOWN_BROAD_EVENTS = {
    "view_item", "view_item_list", "page_view", "session_start", "user_engagement",
    "scroll", "click", "first_visit", "view_promotion", "select_promotion", "view_search_results",
}


# ─── formatting (ported 1:1 from ga4_reports.format_report()'s fmt_metric closure — keep in sync;
#     that function returns one pre-joined fixed-width terminal string, the wrong shape for JSON
#     cells, so the *rule* is duplicated here in ~15 lines rather than imported) ────────────────

def fmt_metric(metric_name, val, currency=""):
    try:
        fval = float(val)
    except (ValueError, TypeError):
        return str(val)
    lname = metric_name.lower()
    if "revenue" in lname or "value" in lname:
        return f"{fval:,.2f} {currency}".strip()
    if "rate" in lname:
        return f"{fval * 100:.1f}%"
    if fval == int(fval):
        return f"{int(fval):,}"
    return f"{fval:,.2f}"


def fmt_derived(numerator_val, denominator_val, derived_name, currency=""):
    try:
        num, den = float(numerator_val), float(denominator_val)
    except (ValueError, TypeError):
        return "n/a"
    if not den:
        return "n/a"
    return fmt_metric(derived_name, num / den, currency)


def format_trend_label(dim_name, val):
    """dayOfWeek/hour need client-facing labels, not raw GA4 digit codes — date passthrough
    reuses ga4_reports.format_dim_value() as-is, unchanged."""
    if dim_name == "dayOfWeek" and str(val).isdigit():
        return DAY_NAMES[int(val) % 7]
    if dim_name == "hour" and str(val).isdigit():
        return f"{int(val):02d}:00"
    return format_dim_value(dim_name, val)


def humanize(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return s.replace("_", " ").title()


# ─── classification (purely from each report's existing REPORTS config) ───────────────────────

def classify_shape(config):
    dims = config["dimensions"]
    if not dims:
        return "kpi"
    if len(dims) == 1 and dims[0] in TREND_DIMENSIONS:
        return "trend"
    if len(dims) == 1:
        return "bar_table"
    return "table_only"


def pick_primary_metric(config):
    order_by = config.get("order_by")
    if order_by and order_by in config["metrics"]:
        return order_by
    return config["metrics"][0]


# ─── conversion-event override ──────────────────────────────────────────────────────────────────
# GA4's native "conversions" metric is a raw count of every event marked a "key event" in the
# property — NOT unique conversions, and not limited to a meaningful action. On a real account this
# meant view_item + view_item_list (pure browsing) made up 84% of the reported total. --list-events
# shows the real per-event breakdown; --conversion-event lets the human pick which event(s) should
# actually count, reusing ga4_reports.py's existing event_filter mechanism (already used by
# lead_funnel/contact_clicks) rather than adding anything new to that file.

def fetch_event_breakdown(property_id, headers, date_from, date_to, limit=25):
    """Every real event for this property in the period, with GA4's native conversions count
    alongside the true raw eventCount — the same ad hoc query used to diagnose this issue live,
    now reusable. Config is hand-built here (not from REPORTS) since this is a diagnostic view,
    not one of the 43 dashboard reports."""
    config = {"dimensions": ["eventName"], "metrics": ["conversions", "eventCount"], "order_by": "conversions"}
    data = run_report(property_id, headers, config, date_from, date_to, limit)
    rows = []
    for row in data.get("rows", []):
        name = row["dimensionValues"][0]["value"]
        conv = float(row["metricValues"][0].get("value", 0) or 0)
        cnt = float(row["metricValues"][1].get("value", 0) or 0)
        rows.append({"event": name, "conversions": conv, "event_count": cnt})
    return rows


def recommend_conversion_event(event_rows, business_type):
    """Returns (recommended_event_or_None, reason, confident_bool). Never silently confident on
    an unrecognized name — always paired with the full event_rows list so a human can override."""
    by_name = {r["event"]: r["event_count"] for r in event_rows}

    if business_type == "ecommerce" and by_name.get("purchase", 0) > 0:
        return "purchase", "the standard ecommerce purchase event, present with real volume", True

    for name in KNOWN_STRONG_CONVERSION_EVENTS:
        if by_name.get(name, 0) > 0:
            return name, f"a standard conversion event name, present with real volume", True

    candidates = [r for r in event_rows if r["event"] not in KNOWN_BROAD_EVENTS and r["event_count"] > 0]
    if candidates:
        top = max(candidates, key=lambda r: r["event_count"])
        return (top["event"],
                "no standard conversion event name (purchase/generate_lead/...) was found — this is "
                "just the highest-volume event that isn't an obviously passive/structural one "
                "(view_item, page_view, session_start, etc.). Verify this is actually meaningful "
                "before trusting it.", False)
    return None, "no non-broad event with any volume was found in this period.", False


CONVERSION_LOOKUP_LIMIT = 500  # generous cap so the merge below rarely misses a long-tail dimension value


def apply_conversion_override(config, data, property_id, headers, date_from, date_to, conversion_events):
    """GA4's dimensionFilter (the event_filter mechanism) restricts EVERY metric in a request to
    rows matching that filter, not just one metric — confirmed live: adding event_filter=['purchase']
    to a request that also asks for 'sessions' dropped total sessions from 9,907 to 194 (sessions
    that happened to contain a purchase event), not the true session count. So the 'conversions'
    metric can't just be swapped in-place inside the original request.

    Instead: run a SEPARATE lookup query (same dimensions, metric=eventCount, filtered to the
    chosen event(s)), then merge its per-dimension counts into the ALREADY-FETCHED, unfiltered
    `data`'s 'conversions' position by matching dimension-value tuples. Every other metric in
    `data` (sessions, totalUsers, engagementRate, ...) is completely untouched. A dimension value
    with zero matching filtered events simply won't appear in the lookup — treated as 0, which is
    correct. Returns (data, overridden_bool); `data` is mutated in place for the conversions cells."""
    if not conversion_events or "conversions" not in config["metrics"]:
        return data, False
    conv_idx = config["metrics"].index("conversions")
    lookup_config = {"dimensions": config["dimensions"], "metrics": ["eventCount"], "order_by": None,
                      "event_filter": conversion_events}
    lookup_data = run_report(property_id, headers, lookup_config, date_from, date_to, CONVERSION_LOOKUP_LIMIT)
    lookup = {}
    for row in lookup_data.get("rows", []):
        key = tuple(dv.get("value", "") for dv in row.get("dimensionValues", []))
        lookup[key] = row["metricValues"][0].get("value", "0")
    for row in data.get("rows", []):
        key = tuple(dv.get("value", "") for dv in row.get("dimensionValues", []))
        row["metricValues"][conv_idx]["value"] = lookup.get(key, "0")
    return data, True


# ─── funnel anomaly check — deterministic, no judgment ─────────────────────────────────────────

def funnel_violations(stage_order, values_by_metric):
    out = []
    for earlier, later in zip(stage_order, stage_order[1:]):
        v_e = values_by_metric.get(earlier, 0.0)
        v_l = values_by_metric.get(later, 0.0)
        if v_l > v_e:
            out.append((earlier, later, v_e, v_l))
    return out


# ─── raw GA4 API response -> row dicts ─────────────────────────────────────────────────────────

def extract_rows(config, data, currency):
    dim_names = config["dimensions"]
    met_names = config["metrics"]
    derived = config.get("derived", [])
    rows = []
    for row in data.get("rows", []):
        dim_vals_raw = [dv.get("value", "") for dv in row.get("dimensionValues", [])]
        dim_vals = [format_dim_value(h, v) for h, v in zip(dim_names, dim_vals_raw)]
        met_vals_raw = [mv.get("value", "0") for mv in row.get("metricValues", [])]
        raw_metrics = {}
        for name, v in zip(met_names, met_vals_raw):
            try:
                raw_metrics[name] = float(v)
            except ValueError:
                raw_metrics[name] = 0.0
        met_vals = [fmt_metric(h, v, currency) for h, v in zip(met_names, met_vals_raw)]
        derived_vals = [fmt_derived(raw_metrics.get(num_m, 0), raw_metrics.get(den_m, 0), d_name, currency)
                         for d_name, num_m, den_m in derived]
        rows.append({
            "dim": dim_vals, "dim_raw": dim_vals_raw, "metrics": met_vals, "derived": derived_vals,
            "raw_metrics": raw_metrics, "anomaly": False,
        })

    totals_metrics = {}
    totals = data.get("totals", [])
    if totals:
        tot_vals = [mv.get("value", "0") for mv in totals[0].get("metricValues", [])]
        for name, v in zip(met_names, tot_vals):
            try:
                totals_metrics[name] = float(v)
            except ValueError:
                totals_metrics[name] = 0.0
    return rows, totals_metrics


# ─── per-shape payload builders ─────────────────────────────────────────────────────────────────

def build_kpi_report(name, config, data, currency):
    met_names = config["metrics"]
    derived = config.get("derived", [])
    api_rows = data.get("rows", [])
    met_vals_raw = [mv.get("value", "0") for mv in api_rows[0].get("metricValues", [])] if api_rows else ["0"] * len(met_names)
    raw = {}
    for n, v in zip(met_names, met_vals_raw):
        try:
            raw[n] = float(v)
        except ValueError:
            raw[n] = 0.0

    kpis = [{"label": humanize(n), "value": fmt_metric(n, v, currency)} for n, v in zip(met_names, met_vals_raw)]
    for d_name, num_m, den_m in derived:
        kpis.append({"label": humanize(d_name), "value": fmt_derived(raw.get(num_m, 0), raw.get(den_m, 0), d_name, currency)})

    anomaly, caption = None, None
    stage_order = FUNNEL_CHECKS.get(name)
    if stage_order:
        violations = funnel_violations(stage_order, raw)
        if violations:
            e0, l0, v_e0, v_l0 = violations[0]
            msg = (f"{humanize(l0)} ({v_l0:,.0f}) exceeds {humanize(e0)} ({v_e0:,.0f}) — possible tracking "
                   f"issue (e.g. a later-stage event firing without the earlier one, or firing multiple "
                   f"times per session).")
            if len(violations) > 1:
                extra = "; ".join(f"{humanize(l)} vs {humanize(e)}" for e, l, _, _ in violations[1:3])
                msg += f" Also: {extra}."
            anomaly = {"message": msg, "severity": "warn"}

        bad_pairs = {(e, l) for e, l, _, _ in violations}
        best = None
        for e, l in zip(stage_order, stage_order[1:]):
            if (e, l) in bad_pairs:
                continue
            v_e, v_l = raw.get(e, 0.0), raw.get(l, 0.0)
            if v_e <= 0:
                continue
            pct = v_l / v_e * 100
            if best is None or pct < best[2]:
                best = (e, l, pct)
        if best:
            caption = f"{humanize(best[1])} shows the largest drop-off ({best[2]:.0f}% of {humanize(best[0])})."
    elif derived:
        d_name, num_m, den_m = derived[0]
        val = fmt_derived(raw.get(num_m, 0), raw.get(den_m, 0), d_name, currency)
        if val != "n/a":
            caption = f"{humanize(d_name)}: {val}."

    return {"shape": "kpi", "kpis": kpis, "caption": caption, "anomaly": anomaly}


def build_trend_report(name, config, data, currency):
    dim_name = config["dimensions"][0]
    primary = pick_primary_metric(config)
    rows, _totals = extract_rows(config, data, currency)

    series = []
    for row in rows:
        raw_val = row["dim_raw"][0] if row["dim_raw"] else ""
        x_label = format_trend_label(dim_name, raw_val)
        y = row["raw_metrics"].get(primary, 0.0)
        series.append({"x": x_label, "y": y, "y_formatted": fmt_metric(primary, y, currency)})

    if not series:
        caption = "No data returned for this period."
    else:
        first, last = series[0]["y"], series[-1]["y"]
        if first == 0 and last == 0:
            caption = f"{humanize(primary)} stayed at 0 across the period."
        elif first == 0:
            caption = f"{humanize(primary)} went from 0 to {fmt_metric(primary, last, currency)}."
        else:
            pct = (last - first) / first * 100
            word = "stayed roughly flat" if abs(pct) < 5 else ("rose" if pct > 0 else "fell")
            caption = (f"{humanize(primary)} {word} from {fmt_metric(primary, first, currency)} "
                       f"to {fmt_metric(primary, last, currency)} ({pct:+.0f}%).")

    headers = {
        "dimensions": [humanize(dim_name)],
        "metrics": [humanize(m) for m in config["metrics"]],
        "derived": [humanize(d[0]) for d in config.get("derived", [])],
    }
    return {"shape": "trend", "series": series, "rows": rows, "headers": headers, "caption": caption, "anomaly": None}


def build_bar_table_report(name, config, data, currency):
    primary = pick_primary_metric(config)
    rows, totals = extract_rows(config, data, currency)

    anomaly = None
    stage_order = FUNNEL_CHECKS.get(name)
    if stage_order:
        offending = []
        for row in rows:
            if funnel_violations(stage_order, row["raw_metrics"]):
                row["anomaly"] = True
                offending.append(row["dim"][0] if row["dim"] else "?")
        if offending:
            names = ", ".join(offending[:8]) + ("..." if len(offending) > 8 else "")
            anomaly = {
                "message": f"{len(offending)} of {len(rows)} rows show a later funnel stage exceeding an "
                           f"earlier one — possible tracking issue (see highlighted rows): {names}.",
                "severity": "warn",
            }

    total_raw = totals.get(primary)
    if total_raw is None:
        total_raw = sum(r["raw_metrics"].get(primary, 0.0) for r in rows)
    for r in rows:
        raw_v = r["raw_metrics"].get(primary, 0.0)
        r["primary_raw"] = raw_v
        r["share"] = (raw_v / total_raw) if total_raw else 0.0
        r["primary_formatted"] = fmt_metric(primary, raw_v, currency)

    if not rows:
        caption = "No data returned for this period."
    elif "rate" in primary.lower():
        top = rows[0]
        asc = bool(config.get("order_numeric_asc"))
        caption = (f"{top['dim'][0] if top['dim'] else '—'} has the {'lowest' if asc else 'highest'} "
                   f"{humanize(primary)} at {top['primary_formatted']}.")
    elif not total_raw:
        caption = f"No {humanize(primary)} recorded in this period."
    else:
        top = rows[0]
        caption = (f"{top['dim'][0] if top['dim'] else '—'} leads with {top['primary_formatted']} "
                   f"({top['share'] * 100:.0f}% of total).")

    headers = {
        "dimensions": [humanize(d) for d in config["dimensions"]],
        "metrics": [humanize(m) for m in config["metrics"]],
        "derived": [humanize(d[0]) for d in config.get("derived", [])],
    }
    return {"shape": "bar_table", "rows": rows, "headers": headers, "caption": caption, "anomaly": anomaly}


def build_table_only_report(name, config, data, currency):
    rows, _totals = extract_rows(config, data, currency)
    primary = pick_primary_metric(config)
    if not rows:
        caption = "No data returned for this period."
    else:
        top = rows[0]
        caption = (f"Top combination: {' × '.join(top['dim'])} with "
                   f"{fmt_metric(primary, top['raw_metrics'].get(primary, 0), currency)} {humanize(primary)}.")

    headers = {
        "dimensions": [humanize(d) for d in config["dimensions"]],
        "metrics": [humanize(m) for m in config["metrics"]],
        "derived": [humanize(d[0]) for d in config.get("derived", [])],
    }
    return {"shape": "table_only", "rows": rows, "headers": headers, "caption": caption, "anomaly": None}


SHAPE_BUILDERS = {
    "kpi": build_kpi_report,
    "trend": build_trend_report,
    "bar_table": build_bar_table_report,
    "table_only": build_table_only_report,
}


# ─── overview KPIs — reuses data already fetched for acquisition_channels / revenue_by_channel,
#     no extra API calls ────────────────────────────────────────────────────────────────────────

def build_overview(report_payloads, is_ecommerce, currency):
    kpis = []
    acq = report_payloads.get("acquisition_channels")
    if acq and acq.get("rows"):
        sessions = sum(r["raw_metrics"].get("sessions", 0) for r in acq["rows"])
        conversions = sum(r["raw_metrics"].get("conversions", 0) for r in acq["rows"])
        weighted = sum(r["raw_metrics"].get("engagementRate", 0) * r["raw_metrics"].get("sessions", 0) for r in acq["rows"])
        eng_rate = (weighted / sessions) if sessions else 0
        kpis.append({"label": "Sessions", "value": fmt_metric("sessions", sessions, currency)})
        kpis.append({"label": "Conversions", "value": fmt_metric("conversions", conversions, currency)})
        kpis.append({"label": "Engagement Rate", "value": fmt_metric("engagementRate", eng_rate, currency)})
    if is_ecommerce:
        rev = report_payloads.get("revenue_by_channel")
        if rev and rev.get("rows"):
            revenue = sum(r["raw_metrics"].get("totalRevenue", 0) for r in rev["rows"])
            transactions = sum(r["raw_metrics"].get("transactions", 0) for r in rev["rows"])
            kpis.append({"label": "Revenue", "value": fmt_metric("totalRevenue", revenue, currency)})
            kpis.append({"label": "Transactions", "value": fmt_metric("transactions", transactions, currency)})
            kpis.append({"label": "Avg Order Value", "value": fmt_derived(revenue, transactions, "avgOrderValue", currency)})
    return {"kpis": kpis}


# ─── main ────────────────────────────────────────────────────────────────────────────────────

def cmd_list_events(args):
    client_meta = resolve(args.client)
    property_id = client_meta.get("ga4_property_id")
    if not property_id:
        print(f"No GA4 property configured for '{args.client}' in client_registry.py")
        sys.exit(2)

    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)
    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    rows = fetch_event_breakdown(property_id, headers, date_from, date_to)
    print(f"Client   : {client_meta['name']} ({args.client})")
    print(f"Period   : {date_from} -> {date_to} ({args.days} days)\n")
    print(f"{'event':<30} {'conversions (GA4 key-event count)':>34} {'eventCount (real occurrences)':>30}")
    print("-" * 96)
    for r in rows:
        print(f"{r['event']:<30} {r['conversions']:>34,.0f} {r['event_count']:>30,.0f}")

    business_type = client_meta.get("business_type", "")
    rec, reason, confident = recommend_conversion_event(rows, business_type)
    print()
    if rec:
        conf_note = "" if confident else " (LOW CONFIDENCE — verify before trusting)"
        print(f"Recommended --conversion-event: {rec}{conf_note}")
        print(f"  Reason: {reason}")
    else:
        print(f"No recommendation could be made: {reason}")
    print("\nGA4's native 'conversions' metric (left column) counts every occurrence of EVERY event "
          "marked a key event in this property — not unique conversions. Pick the event(s) that "
          "actually represent a real conversion and pass them via --conversion-event, e.g.:")
    print(f"  python3 {Path(__file__).name} {args.client} --conversion-event {rec or '<event_name>'}")


def cmd_run(args):
    client_meta = resolve(args.client)
    property_id = client_meta.get("ga4_property_id")
    if not property_id:
        print(f"No GA4 property configured for '{args.client}' in client_registry.py")
        sys.exit(2)

    is_ecommerce = client_meta.get("business_type") == "ecommerce"
    currency = client_meta.get("currency", "")
    conversion_events = [e.strip() for e in args.conversion_event.split(",")] if args.conversion_event else None

    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    applicable = {n: c for n, c in REPORTS.items() if not (c["ecommerce_only"] and not is_ecommerce)}

    print(f"Client   : {client_meta['name']} ({args.client})")
    print(f"Property : {property_id}")
    print(f"Period   : {date_from} -> {date_to} ({args.days} days)")
    print(f"Building GA4 dashboard — {len(applicable)} reports "
          f"({len(applicable)} sequential API calls, this takes a bit)...\n")

    report_payloads = {}
    categories_seen = []
    any_overridden = False
    for name, config in applicable.items():
        shape = classify_shape(config)
        try:
            data = run_report(property_id, headers, config, date_from, date_to, args.limit)
            data, overridden = apply_conversion_override(
                config, data, property_id, headers, date_from, date_to, conversion_events)
            any_overridden = any_overridden or overridden
            payload = SHAPE_BUILDERS[shape](name, config, data, currency)
            status = "ok"
        except Exception as e:  # noqa: BLE001 — one bad report shouldn't blank the whole dashboard
            payload = {"shape": "error", "error": str(e), "caption": None, "anomaly": None}
            status = "FAILED"
        payload.update({
            "name": name, "display_name": humanize(name), "category": config["category"],
            "description": config["description"],
        })
        report_payloads[name] = payload
        if config["category"] not in categories_seen:
            categories_seen.append(config["category"])
        print(f"  [{status:6s}] {shape:10s} {name}")

    overview = build_overview(report_payloads, is_ecommerce, currency)
    conversion_note = (
        f"Conversions in this dashboard = {', '.join(conversion_events)} occurrences "
        f"(not GA4's blended key-event metric)."
        if conversion_events and any_overridden else None
    )

    data_out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "agency_name": AGENCY_NAME,
        "client": {
            "slug": args.client, "name": client_meta["name"],
            "business_type": client_meta.get("business_type", ""), "currency": currency,
        },
        "period": {"date_from": date_from, "date_to": date_to, "days": args.days},
        "categories": categories_seen,
        "overview": overview,
        "reports": list(report_payloads.values()),
        "conversion_note": conversion_note,
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("__AGENCY_NAME__", AGENCY_NAME)
    html = html.replace("__CLIENT_NAME__", client_meta["name"])
    html = html.replace("__PAGE_TITLE__", f"{client_meta['name']} — GA4 Dashboard")
    html = html.replace(
        "/*__DASHBOARD_DATA__*/{}",
        json.dumps(data_out, ensure_ascii=False).replace("</script", "<\\/script"),
    )

    out_path = Path(args.out) if args.out else ROOT / "clients" / args.client / "reports" / f"ga4_dashboard_{today}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    failed = sum(1 for p in report_payloads.values() if p["shape"] == "error")
    print(f"\nDashboard built → {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")
    print(f"  {len(report_payloads)} reports across {len(categories_seen)} categories"
          + (f" ({failed} failed to load)" if failed else ""))
    print(f"  Open with: open {out_path}")


def main():
    parser = argparse.ArgumentParser(description="GA4 client-facing HTML dashboard — every applicable report, visualized")
    parser.add_argument("client")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default=None, help="Override output path (default: clients/<slug>/reports/ga4_dashboard_<date>.html)")
    parser.add_argument("--list-events", action="store_true",
                         help="Print every real event with its volume + a recommended --conversion-event pick, then exit (no dashboard built)")
    parser.add_argument("--conversion-event", default=None,
                         help="Comma-separated event name(s) to use as the real 'conversions' metric everywhere it "
                              "appears in the dashboard, instead of GA4's blended key-event count. See --list-events.")
    args = parser.parse_args()
    if args.list_events:
        cmd_list_events(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
