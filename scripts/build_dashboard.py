#!/usr/bin/env python3
"""
55DigitalAI — Local Dashboard Builder
=============================================================
Purpose  : Scans clients/*/ (client-brief.md, reports/, scripts/) and
           renders a single self-contained dashboard/index.html.
           No server needed — open the file directly (file://) in a browser.
           No external dependencies — stdlib only.

Usage    : python3 scripts/build_dashboard.py
Output   : dashboard/index.html
Changelog: 2026-07-18  Initial version
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENTS_DIR = ROOT / "clients"
OUT_DIR = ROOT / "dashboard"
TEMPLATE = ROOT / "scripts" / "dashboard_template.html"

sys.path.insert(0, str(ROOT / "scripts"))
from client_registry import CLIENTS as CLIENT_META  # noqa: E402
from change_log import query_changes  # noqa: E402
from brand import AGENCY_NAME  # noqa: E402

REPORT_TYPE_RE = re.compile(
    r"^(?P<type>keywords_audit|pmax_audit|pmax_brand_generic_audit|best_sellers_rotate|feed_audit|full_account_audit|daily_check)_"
    r"(?P<date>\d{4}-\d{2}-\d{2})(?:_(?P<time>\d{2}-\d{2}))?\.(?:log|md)$"
)

REPORT_TYPE_LABELS = {
    "keywords_audit": "Negative Keyword Audit",
    "pmax_audit": "PMax Search Term Audit",
    "pmax_brand_generic_audit": "PMax Brand/Generic Search Term Audit",
    "best_sellers_rotate": "Best Sellers Rotation",
    "feed_audit": "Feed Audit",
    "full_account_audit": "Full Account Audit",
    "daily_check": "Daily Pulse-Check",
}


def parse_report_stats(report_type: str, content: str) -> dict:
    """Pull a few headline numbers out of a report body for list-view summaries."""
    stats = {}
    if report_type in ("keywords_audit", "pmax_audit"):
        m = re.search(r"Negated this run:\s*(\d+)", content)
        if m:
            stats["negated"] = int(m.group(1))
        m = re.search(r"Terms reviewed:\s*(\d+)", content)
        if m:
            stats["reviewed"] = int(m.group(1))
    elif report_type == "pmax_brand_generic_audit":
        m = re.search(r"Terms negated\s*:\s*(\d+)", content)
        if m:
            stats["negated"] = int(m.group(1))
        m = re.search(r"Campaigns analysed\s*:\s*(\d+)", content)
        if m:
            stats["campaigns"] = int(m.group(1))
    elif report_type == "best_sellers_rotate":
        m = re.search(r"(\d+)\s+products? (?:added|promoted)", content, re.IGNORECASE)
        if m:
            stats["products"] = int(m.group(1))
    elif report_type == "daily_check":
        # a daily_check log accumulates multiple runs per day — take the last "Flags raised" value
        m = re.findall(r"Flags raised\s*:\s*(\d+)", content)
        if m:
            stats["flags"] = int(m[-1])
    return stats


def parse_daily_check_pulse(content: str) -> dict:
    """Extract the latest run's budget-pacing + conversion-flag summary from a
    daily_check log (a file that accumulates multiple timestamped runs per day)."""
    runs = re.split(r"\n\[Run at ([\d\-T:]+)\]\n", content)
    if len(runs) < 3:
        return None
    run_at, body = runs[-2], runs[-1]

    pulse = {"run_at": run_at, "budget": None, "conversion_flags": [], "total_flags": None}

    m = re.search(r"Flags raised\s*:\s*(\d+)", body)
    if m:
        pulse["total_flags"] = int(m.group(1))
    m = re.search(r"Campaigns checked\s*:\s*(\d+)", body)
    if m:
        pulse["campaigns_checked"] = int(m.group(1))

    m = re.search(
        r"Check window\s*:\s*(\S+) → (\S+) \((\d+)d\)\n"
        r"\s*Baseline window:\s*(\S+) → (\S+) \((\d+)d\)",
        body,
    )
    if m:
        pulse["header"] = {
            "check_from": m.group(1), "check_to": m.group(2), "check_days": int(m.group(3)),
            "baseline_from": m.group(4), "baseline_to": m.group(5), "baseline_days": int(m.group(6)),
        }
    m = re.search(r"NOTE: (public holiday.+)", body)
    pulse["holiday_note"] = m.group(1).strip() if m else None

    budget_sec_m = re.search(r"## 2\. BUDGET PACING\n(.*?)(?=\n## 3\.|\Z)", body, re.DOTALL)
    budget_sec = budget_sec_m.group(1) if budget_sec_m else ""

    if "No monthly budget configured" in budget_sec:
        pulse["budget"] = {"status": "unconfigured"}
    else:
        m = re.search(
            r"Monthly budget: ([\d.]+) (\S+)\n"
            r"\s*Spent so far\s*: ([\d.]+) \S+ \((\d+)% of budget\)\n"
            r"\s*Days elapsed\s*: (\d+) of (\d+) \(expected ~(\d+)% spent by now\)\n"
            r"\s*\[(OK|FLAG)\] (?:(Under-pacing|Over-pacing) —.*|On pace.*)",
            budget_sec,
        )
        if m:
            (budget, currency, mtd, actual_pct, days_elapsed, days_total,
             expected_pct, status, direction) = m.groups()
            pulse["budget"] = {
                "status": "ok" if status == "OK" else "flag",
                "direction": direction.lower() if direction else None,
                "mtd_spend": float(mtd),
                "monthly_budget": float(budget),
                "currency": currency,
                "actual_pct": int(actual_pct),
                "expected_pct": int(expected_pct),
                "days_elapsed": int(days_elapsed),
                "days_total": int(days_total),
            }

    if pulse["budget"] and pulse["budget"].get("status") != "unconfigured":
        m = re.search(
            r"Required pace\s*: ([\d.]+) \S+/day to land on budget by month-end \(yesterday spent ([\d.]+) \S+\)\n"
            r"\s*\[INFO\] (Increase|Decrease) daily spend by ([\d.]+) \S+/day to stay on pace\.",
            budget_sec,
        )
        if m:
            required_daily, yesterday_spend, rec_direction, pace_delta = m.groups()
            remaining_m = re.search(r"Remaining days\s*: (\d+)", budget_sec)
            pulse["budget"]["pace_recommendation"] = {
                "type": "adjust",
                "required_daily": float(required_daily),
                "remaining_days": int(remaining_m.group(1)) if remaining_m else None,
                "yesterday_spend": float(yesterday_spend),
                "direction": rec_direction.lower(),
                "delta": float(pace_delta),
            }
        else:
            m = re.search(
                r"\[INFO\] Already over budget by ([\d.]+) \S+ with (\d+) days left", budget_sec
            )
            if m:
                pulse["budget"]["pace_recommendation"] = {
                    "type": "over_budget",
                    "over_amount": float(m.group(1)),
                    "remaining_days": int(m.group(2)),
                }
            elif "Last day of the month" in budget_sec:
                pulse["budget"]["pace_recommendation"] = {"type": "last_day"}

    sec1_m = re.search(r"## 1\. CONVERSION TRACKING(.*?)\n## 2\.", body, re.DOTALL)
    sec1 = sec1_m.group(1) if sec1_m else ""
    m = re.search(r"Summary: \d+ campaigns checked — (.+?)\.", sec1)
    pulse["conversion_summary"] = m.group(1) if m else None
    pulse["conversion_campaigns"] = []
    for name, baseline_avg, check_avg, check_total, status, message in re.findall(
        r"  ([^\n]+)\n"
        r"    Prior \d+ days average: ([\d.]+) conversions/day\n"
        r"    Last \d+ days   : ([\d.]+) conversions/day \((\d+) total\)\n"
        r"    \[(OK|FLAG)\] (.+)",
        sec1,
    ):
        entry = {
            "name": name.strip(), "baseline_avg": float(baseline_avg), "check_avg": float(check_avg),
            "check_total": int(check_total), "status": status.lower(), "message": message.strip(),
        }
        pulse["conversion_campaigns"].append(entry)
        if status == "FLAG":
            pulse["conversion_flags"].append({"campaign": entry["name"], "message": entry["message"]})

    pulse["budget_campaigns"] = [
        {"campaign": name.strip(), "lost_is_pct": int(pct), "message": message.strip()}
        for name, pct, message in re.findall(
            r"  ([^\n]+)\n    Impression share lost to budget limits: (\d+)%\n    \[FLAG\] (.+)",
            budget_sec,
        )
    ]

    sec3_m = re.search(r"## 3\. COST / CPA ANOMALIES(.*?)\n## 4\.", body, re.DOTALL)
    sec3 = sec3_m.group(1) if sec3_m else ""
    m = re.search(r"Summary: \d+ campaigns checked — (.+?)\.", sec3)
    pulse["cost_summary"] = m.group(1) if m else None
    pulse["cost_campaigns"] = []
    for name, baseline_cost, check_cost, cpa_part, status, message in re.findall(
        r"  ([^\n]+)\n"
        r"    Daily cost: ([\d.]+) \S+/day \(prior \d+ days avg\) → ([\d.]+) \S+/day \(last \d+ days\)\n"
        r"    CPA       : (.+)\n"
        r"    \[(OK|FLAG)\] (.+)",
        sec3,
    ):
        cpa_m = re.match(r"([\d.]+) \S+ \(prior \d+ days avg\) → ([\d.]+) \S+ \(last \d+ days\)", cpa_part)
        pulse["cost_campaigns"].append({
            "name": name.strip(),
            "baseline_cost": float(baseline_cost), "check_cost": float(check_cost),
            "baseline_cpa": float(cpa_m.group(1)) if cpa_m else None,
            "check_cpa": float(cpa_m.group(2)) if cpa_m else None,
            "status": status.lower(), "message": message.strip(),
        })

    pulse["trend"] = parse_conversion_trend(body)

    pulse["month_comparison"] = None
    sec6_m = re.search(r"## 6\. MONTH VS\. MONTH \((\S+) → (\S+) vs\. (\S+) → (\S+), same day-of-month range\)\n(.*?)(?=\n=|\Z)", body, re.DOTALL)
    if sec6_m:
        this_from, this_to, last_from, last_to, sec6 = sec6_m.groups()
        mc = {"this_from": this_from, "this_to": this_to, "last_from": last_from, "last_to": last_to}
        m = re.search(r"Cost\s*:\s*([\d.]+) → ([\d.]+) (\S+)", sec6)
        if m:
            mc["last_cost"], mc["this_cost"], mc["currency"] = float(m.group(1)), float(m.group(2)), m.group(3)
        m = re.search(r"Revenue:\s*([\d.]+) → ([\d.]+) \S+", sec6)
        if m:
            mc["last_revenue"], mc["this_revenue"] = float(m.group(1)), float(m.group(2))
        m = re.search(r"ROAS\s*:\s*(n/a|[\d.]+) → (n/a|[\d.]+)", sec6)
        if m:
            mc["last_roas"] = None if m.group(1) == "n/a" else float(m.group(1))
            mc["this_roas"] = None if m.group(2) == "n/a" else float(m.group(2))
        m = re.search(r"Conversions:\s*([\d.]+) → ([\d.]+)", sec6)
        if m:
            mc["last_conversions"], mc["this_conversions"] = float(m.group(1)), float(m.group(2))
        pulse["month_comparison"] = mc

    return pulse


def parse_conversion_trend(body: str) -> list:
    """Extract the day-by-day rows from the CONVERSION TREND section (dd.mm dated,
    either ecommerce's conv/value/cost/ROAS line or lead-gen's conv-only line)."""
    sec = re.search(r"## 4\. CONVERSION TREND[^\n]*\n(.*?)\n\s*Check window", body, re.DOTALL)
    if not sec:
        return []
    days = []
    for line in sec.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(
            r"(\d{2}\.\d{2}) - conv ([\d.]+) \| value ([\d.]+) \| cost ([\d.]+) \| ROAS (n/a|[\d.]+)", line
        )
        if m:
            date_s, conv, value, cost, roas = m.groups()
            days.append({
                "date": date_s, "conv": float(conv), "conv_value": float(value),
                "cost": float(cost), "roas": None if roas == "n/a" else float(roas),
            })
            continue
        m = re.match(r"(\d{2}\.\d{2}) - ([\d.]+) conv", line)
        if m:
            date_s, conv = m.groups()
            days.append({"date": date_s, "conv": float(conv)})
    return days


def parse_run_status(content: str):
    """Every run_*.sh wrapper stamps one of these three markers at the end of the log."""
    if re.search(r"Audit finished successfully", content):
        return "success"
    if re.search(r"Audit TIMED OUT", content):
        return "timeout"
    if re.search(r"Audit FAILED", content):
        return "failed"
    return None


def scan_scripts(scripts_dir: Path) -> list:
    out = []
    if not scripts_dir.exists():
        return out
    for f in sorted(scripts_dir.iterdir()):
        if not f.is_file() or f.suffix not in (".sh", ".py"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        header_lines = []
        if f.suffix == ".py":
            m = re.search(r'"""(.*?)"""', text, re.DOTALL)
            if m:
                header_lines = [l.strip() for l in m.group(1).strip().splitlines()]
        else:  # .sh — collect the leading '#' comment block (skipping the shebang)
            for line in text.splitlines()[:40]:
                stripped = line.strip()
                if stripped.startswith("#!"):
                    continue
                if stripped.startswith("#"):
                    header_lines.append(stripped.lstrip("#").strip())
                    continue
                if stripped == "" and header_lines:
                    break
                if stripped != "":
                    break
        out.append({
            "filename": f.name,
            "ext": f.suffix.lstrip("."),
            "header": "\n".join(header_lines).strip(),
            "size_bytes": f.stat().st_size,
        })
    return out


def scan_reports(reports_dir: Path) -> list:
    out = []
    if not reports_dir.exists():
        return out
    for f in sorted(reports_dir.iterdir()):
        if not f.is_file():
            continue
        m = REPORT_TYPE_RE.match(f.name)
        if m:
            rtype = m.group("type")
            date_str = m.group("date")
            time_str = m.group("time")
            ts = f"{date_str}T{time_str.replace('-', ':')}:00" if time_str else f"{date_str}T00:00:00"
        else:
            rtype = "other"
            date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
            ts = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        content = f.read_text(encoding="utf-8", errors="replace")
        out.append({
            "filename": f.name,
            "type": rtype,
            "type_label": REPORT_TYPE_LABELS.get(rtype, "Report"),
            "date": date_str,
            "timestamp": ts,
            "size_bytes": f.stat().st_size,
            "stats": parse_report_stats(rtype, content),
            "status": parse_run_status(content),
            "content": content,
        })
    out.sort(key=lambda r: r["timestamp"], reverse=True)
    return out


def build():
    clients = []
    for client_dir in sorted(CLIENTS_DIR.iterdir()):
        if not client_dir.is_dir() or client_dir.name.startswith("_"):
            continue  # skip clients/_template/ and any other underscore-prefixed scaffolding folder
        slug = client_dir.name
        brief_file = client_dir / "client-brief.md"
        brief_md = brief_file.read_text(encoding="utf-8", errors="replace") if brief_file.exists() else ""
        reports = scan_reports(client_dir / "reports")
        scripts = scan_scripts(client_dir / "scripts")
        meta = CLIENT_META.get(slug, {"name": slug.title(), "domain": None, "customer_id": None})

        recent_negated = sum(
            r["stats"].get("negated", 0)
            for r in reports
            if (datetime.now() - datetime.fromisoformat(r["timestamp"])).days <= 7
        )

        latest_daily_check = next((r for r in reports if r["type"] == "daily_check"), None)
        pulse = parse_daily_check_pulse(latest_daily_check["content"]) if latest_daily_check else None
        if pulse:
            pulse["date"] = latest_daily_check["date"]

        changes = query_changes(client_slug=slug, limit=200)

        clients.append({
            "slug": slug,
            "name": meta["name"],
            "domain": meta.get("domain"),
            "customer_id": meta.get("customer_id"),
            "business_type": meta.get("business_type", "lead_gen"),
            "links": meta.get("links", {}),
            "brief_markdown": brief_md,
            "reports": reports,
            "scripts": scripts,
            "changes": changes,
            "report_count": len(reports),
            "latest_report_date": reports[0]["date"] if reports else None,
            "recent_negated": recent_negated,
            "pulse": pulse,
        })

    total_reports = sum(c["report_count"] for c in clients)
    total_negated_7d = sum(c["recent_negated"] for c in clients)
    total_changes = sum(len(c["changes"]) for c in clients)
    latest = max(
        (c for c in clients if c["latest_report_date"]),
        key=lambda c: c["latest_report_date"],
        default=None,
    )

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "clients": clients,
        "summary": {
            "total_clients": len(clients),
            "total_reports": total_reports,
            "negated_7d": total_negated_7d,
            "total_changes": total_changes,
            "latest_client": latest["name"] if latest else None,
            "latest_date": latest["latest_report_date"] if latest else None,
        },
    }

    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("__AGENCY_NAME__", AGENCY_NAME)
    html = html.replace(
        "/*__DASHBOARD_DATA__*/{}",
        json.dumps(data, ensure_ascii=False).replace("</script", "<\\/script"),
    )

    OUT_DIR.mkdir(exist_ok=True)
    out_file = OUT_DIR / "index.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"Dashboard built → {out_file}  ({out_file.stat().st_size / 1024:.0f} KB)")
    print(f"  {len(clients)} clients, {total_reports} reports")
    print(f"  Open with: open {out_file}")


if __name__ == "__main__":
    build()
