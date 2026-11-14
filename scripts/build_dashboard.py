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
           2026-11-12  Slimmed output (was 14 MB): index.html now holds only metadata
                       + stats; heavy per-client data (brief, changes, last 30 days of
                       log text) goes to dashboard/data/<slug>.js, loaded on demand.
                       Client report HTML pages are no longer embedded - the dashboard
                       links to the client's "report_url" (clients.json) instead; old
                       drafts/previews are skipped. New look: floating dark sidebar with
                       client logos, dark mode, archived clients ("archived": true).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

LOG_EMBED_DAYS = 30          # log text older than this is not embedded (stats are kept)
LOG_EMBED_MAX_BYTES = 200_000  # larger text files are never embedded
# Client report HTML: keep only <slug>.html and <slug>-YYYY-MM.html, skip drafts/previews/backups
KEEP_HTML_RE = re.compile(r"^(?P<slug>[a-z0-9]+)(?:-\d{4}-\d{2})?\.html$")

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
        # keyword audit: "Negated this run: N"; PMax audit: "Terms negated      : N"
        m = re.search(r"Negated this run:\s*(\d+)", content) or re.search(r"Terms negated\s*:\s*(\d+)", content)
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
        {"campaign": name.strip(), "lost_is_pct": int(pct),
         "lost_rank_pct": int(rank) if rank else None, "message": message.strip()}
        for name, pct, rank, message in re.findall(
            r"  ([^\n]+)\n    Impression share lost to budget limits: (\d+)%\n"
            r"(?:    Impression share lost to ad rank: (\d+)%\n)?    \[FLAG\] (.+)",
            budget_sec,
        )
    ]
    # won / lost-to-budget / lost-to-rank per Search campaign (logs from 2026-11-12 on)
    pulse["impression_share"] = [
        {"campaign": name.strip(), "won": int(won), "lost_budget": int(lb), "lost_rank": int(lr)}
        for name, won, lb, lr in re.findall(
            r"    IS \| (.+) \| won (\d+)% \| lost to budget (\d+)% \| lost to rank (\d+)%", budget_sec)
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
        title, summary, when, writes = SCRIPT_INFO.get(f.name, (None, None, None, None))
        if summary is None:
            # unknown script: first sentence of "Purpose", else the first header line
            head = "\n".join(header_lines)
            m = re.search(r"Purpose\s*:\s*(.+?)(?:\n\s*\n|\n[A-Z][a-z]+\s*:|$)", head, re.S)
            text = re.sub(r"\s+", " ", m.group(1) if m else (header_lines[0] if header_lines else "")).strip()
            summary = re.split(r"(?<=\.)\s", text)[0][:220]
        out.append({
            "filename": f.name,
            "ext": f.suffix.lstrip("."),
            "title": title or f.stem.replace("_", " ").capitalize(),
            "summary": summary,
            "when": when,
            "writes": writes,
            "size_bytes": f.stat().st_size,
        })
    return out



# Plain-language cards for the Scripts tab, keyed by file name. "when" = how it is started,
# "writes" = whether it changes anything in the ad account / Merchant Center.
SCRIPT_INFO = {
    "run_audit.sh": ("Negative keyword audit",
        "Reads recent search terms, judges each one against the client brief with AI and adds the irrelevant ones as negative keywords.",
        "Automatic, on the schedule set with /55-setup-keyword-audit-automation", True),
    "run_pmax_audit.sh": ("PMax search term audit (scheduled)",
        "Starts the Performance Max irrelevant search term audit on its schedule.",
        "Automatic, on the schedule set with /55-setup-pmax-audit-automation", True),
    "run_pmax_brand_generic_audit.sh": ("PMax brand/generic audit (scheduled)",
        "Starts the PMax brand/generic search term audit on its schedule.",
        "Automatic, on the schedule set with /55-setup-pmax-brand-generic-audit-automation", True),
    "pmax_brand_generic_audit.py": ("PMax brand/generic search term audit",
        "Branded campaign: blocks terms without a brand mention. Generic campaigns: blocks irrelevant terms.",
        "Started by the scheduled job above", True),
    "run_daily_check.sh": ("Daily pulse-check",
        "Checks conversion tracking, budget pacing and cost changes. Feeds the Daily Check tab.",
        "Automatic, when scheduled", False),
}

BINARY_REPORT_EXTS = {"pdf"}  # not text — never decode as UTF-8, never embed content


def scan_reports(reports_dir: Path, slug: str = "") -> list:
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
        ext = f.suffix.lstrip(".").lower()
        is_html = ext == "html"
        if is_html and not KEEP_HTML_RE.match(f.name):
            continue  # old drafts / previews / backups - not worth listing
        is_binary = ext in BINARY_REPORT_EXTS
        # HTML pages are never read: they are linked to their live copy instead
        content = "" if (is_binary or is_html) else f.read_text(encoding="utf-8", errors="replace")
        url = (CLIENT_META.get(slug) or {}).get("report_url") if is_html else None
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
            "is_binary": is_binary,
            "is_html": is_html,
            "url": url,
        })
    out.sort(key=lambda r: r["timestamp"], reverse=True)
    return out


def copy_logo(slug: str, client_dir: Path):
    """clients/<slug>/logo.png (from scripts/fetch_client_logos.py, or saved by hand) -> dashboard/logos/<slug>.png.
    Returns the relative URL with a cache-buster, or None (initials avatar is used)."""
    src = client_dir / "logo.png"
    if not src.exists():
        return None
    dst = OUT_DIR / "logos" / f"{slug}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    if not dst.exists() or dst.read_bytes() != data:
        dst.write_bytes(data)
    return f"logos/{slug}.png?v={int(src.stat().st_mtime)}"


NEG_KEEP_DAYS = 90  # negatives shown in the Negatives tab (lazy data file)


def short_reason(text: str, limit: int = 90) -> str:
    """First sentence of the audit's reason, capped - the Reports view shows short reasons only."""
    t = re.split(r"(?<=[.;])\s", text.strip(), maxsplit=1)[0].rstrip(".;")
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


def last_attempt(content: str) -> str:
    """A log can hold several retries ('Attempt: ...'); only the last one with results counts."""
    chunks = re.split(r"\n\s*Attempt:\s.*\n", content)
    for chunk in reversed(chunks):
        if re.search(r"\[(NEGATED|NEGATE|KEPT|BROAD)\]", chunk):
            return chunk
    return content


def parse_audit(r: dict, content: str):
    """Structured result of one keyword / PMax audit log:
    {"n": [[term, reason, campaign]], "b": [[term, reason]], "k": [[[terms...], reason]], "rev": N, "live": bool}
    keywords_audit: '[NEGATED] t | why' (exact), '[BROAD] t | why', '[KEPT] a / b | why'.
    pmax_audit    : '[NEGATE] t | why' under 'Campaign : X'; changes only count when 'changes applied'."""
    if r["type"] not in ("keywords_audit", "pmax_audit", "pmax_brand_generic_audit"):
        return None
    body = last_attempt(content)
    out = {"d": r["date"], "n": [], "b": [], "k": [], "rev": None, "live": True}
    m = re.search(r"Terms reviewed:\s*(\d+)", body) or re.search(r"Terms total\s*:\s*(\d+)", body)
    if r["type"] == "keywords_audit":
        out["rev"] = int(m.group(1)) if m else None
        for kind, term, why in re.findall(r"\[(NEGATED|BROAD|KEPT)\]\s*(.+?)\s*\|\s*(.+)", body):
            if kind == "NEGATED":
                out["n"].append([term.strip(), short_reason(why), ""])
            elif kind == "BROAD":
                out["b"].append([term.strip(), short_reason(why)])
            else:
                out["k"].append([[t.strip() for t in term.split(" / ") if t.strip()], short_reason(why)])
        out["live"] = r["status"] in ("success", None)
    else:
        out["live"] = "changes applied" in body
        out["rev"] = sum(int(x) for x in re.findall(r"Terms total\s*:\s*(\d+)", body)) or None
        campaign = ""
        for line in body.splitlines():
            cm = re.match(r"Campaign\s*:\s*(.+)", line)
            if cm:
                campaign = cm.group(1).strip()
                continue
            nm = re.search(r"\[NEGATE\]\s*(.+?)\s*\|\s*(.+)", line)
            if nm:
                out["n"].append([nm.group(1).strip(), short_reason(nm.group(2)), campaign])
    return out if (out["n"] or out["b"] or out["k"]) else None


def parse_negatives(r: dict, content: str) -> list:
    """Negatives an audit actually added (exact + broad), for the Negatives tab."""
    a = parse_audit(r, content)
    if not a or not a["live"]:
        return []
    return ([{"d": r["date"], "t": t, "r": why, "m": "exact", "c": c} for t, why, c in a["n"]]
            + [{"d": r["date"], "t": t, "r": why, "m": "broad", "c": ""} for t, why in a["b"]])


def split_heavy(c: dict) -> dict:
    """Move the heavy per-client fields out of the client dict (so index.html stays small)
    and return them for dashboard/data/<slug>.js. Log text is embedded only for recent,
    reasonably small text files; everything else keeps its stats but no body."""
    heavy = {"brief_markdown": c.pop("brief_markdown"), "changes": c.pop("changes"), "logs": {}, "audits": {}}
    negatives = []
    today = datetime.now().date()
    for r in c["reports"]:
        content = r.pop("content")
        age = (today - datetime.fromisoformat(r["date"]).date()).days
        if age <= NEG_KEEP_DAYS and content:
            # one store for both tabs: Reports shows an audit, Negatives flattens the live ones
            negatives.extend(parse_negatives(r, content))
            audit = parse_audit(r, content)
            if audit:
                heavy["audits"][r["filename"]] = audit
        embed = bool(content) and age <= LOG_EMBED_DAYS and r["size_bytes"] <= LOG_EMBED_MAX_BYTES
        r["has_content"] = embed
        if embed:
            heavy["logs"][r["filename"]] = content
    c["changes_count"] = len(heavy["changes"])
    c["negatives_30d"] = sum(1 for n in negatives
                             if (today - datetime.fromisoformat(n["d"]).date()).days < 30)
    c["negatives_90d"] = len(negatives)
    return heavy


def write_client_data(slug: str, heavy: dict) -> None:
    """Write dashboard/data/<slug>.js - a plain script (works from file:// and https)."""
    data_dir = OUT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(heavy, ensure_ascii=False).replace("</script", "<\\/script")
    (data_dir / f"{slug}.js").write_text(
        f"window.CLIENT_DATA=window.CLIENT_DATA||{{}};window.CLIENT_DATA[{json.dumps(slug)}]={payload};",
        encoding="utf-8",
    )


def build():
    clients = []
    heavy_by_slug = {}
    for client_dir in sorted(CLIENTS_DIR.iterdir()):
        if not client_dir.is_dir() or client_dir.name.startswith("_"):
            continue  # skip clients/_template/ and any other underscore-prefixed scaffolding folder
        slug = client_dir.name
        brief_file = client_dir / "client-brief.md"
        brief_md = brief_file.read_text(encoding="utf-8", errors="replace") if brief_file.exists() else ""
        reports = scan_reports(client_dir / "reports", slug)
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
            "archived": bool(meta.get("archived", False)),
            "logo": copy_logo(slug, client_dir),
            # quick links + the live monthly report page, when the client has one
            "links": ({"Monthly report": meta["report_url"]} if meta.get("report_url") else {})
                     | meta.get("links", {}),
            "brief_markdown": brief_md,
            "reports": reports,
            "scripts": scripts,
            "changes": changes,
            "report_count": len(reports),
            "latest_report_date": reports[0]["date"] if reports else None,
            "recent_negated": recent_negated,
            "pulse": pulse,
        })

    for c in clients:
        heavy_by_slug[c["slug"]] = split_heavy(c)
    for old in (OUT_DIR / "data").glob("*.js") if (OUT_DIR / "data").exists() else []:
        old.unlink()  # drop data files of clients that no longer exist
    for slug, heavy in heavy_by_slug.items():
        write_client_data(slug, heavy)

    total_reports = sum(c["report_count"] for c in clients)
    total_negated_7d = sum(c["recent_negated"] for c in clients)
    total_changes = sum(c["changes_count"] for c in clients)
    latest = max(
        (c for c in clients if c["latest_report_date"]),
        key=lambda c: c["latest_report_date"],
        default=None,
    )

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "clients": clients,
        "summary": {
            "total_clients": sum(1 for c in clients if not c["archived"]),
            "archived_clients": sum(1 for c in clients if c["archived"]),
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
