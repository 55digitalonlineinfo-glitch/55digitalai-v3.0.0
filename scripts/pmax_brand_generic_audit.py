#!/usr/bin/env python3
"""
PMax Brand/Generic Search Term Audit — any client
=============================================================
Purpose  : Analyse PMax search terms and exclude mismatched ones, for any
           client in client_registry.py that runs Performance Max.
           - Branded PMax : exclude GENERIC (non-brand) terms
           - Generic PMax : exclude IRRELEVANT terms per client brief

           Named "brand_generic" to distinguish it from a separate, simpler
           pmax_audit.py planned for later — a plain irrelevant-keyword scan
           for PMax analogous to keyword_audit.py, without the branded-vs-
           generic split this script does.

Generalised (2026-07-27) from an earlier client-specific script (clients/_template/scripts/
pmax_audit.py) into a shared, per-client tool — same fetch/analyze/apply
logic, just driven by client_registry.py + clients/<slug>/client-brief.md
instead of hardcoded constants. See client_registry.py's docstring for the
per-client fields this reads.

Per-client requirements:
  - client_registry.py: "customer_id" (always present) and "negative_list_id"
    (general negatives list — reused from the existing negative-keyword-audit
    field, since it's the same list). Branded-campaign analysis additionally
    needs "pmax_branded_generic_list_id" — create it once with `--setup`.
  - clients/<slug>/client-brief.md: a "## Brand Terms" (or "Brand Term(s)")
    heading whose next line(s) are a comma-separated brand term list — only
    required if the client has a campaign with "branded" in its name.
    Generic-campaign analysis reads the whole brief (Always Negate rules etc).

Architecture note (2026-07-24, carried over from the original single-client version):
this script used to interleave Google Ads API calls (gRPC) with
subprocess.run() calls to the `claude` CLI (which forks) inside one
long-lived process. gRPC is not fork-safe — forking a process that already
holds an active gRPC channel corrupts it, which caused real failures in
production (2026-07-22): the next Ads API call either crashed outright with
"Connection reset by peer", or the next `claude` subprocess inherited broken
fd state and its stderr filled with gRPC's own internal warnings, which the
old error handling misreported as "AI analysis failed" for every campaign —
the run still exited 0 ("finished successfully") despite negating zero
terms, so the daily retry-guard never noticed.

Fix: the default (no internal flag) invocation is an orchestrator that never
touches google-ads/gRPC itself — it only spawns three kinds of short-lived
subprocesses, each of which does exactly one kind of work and then exits:
  --phase-fetch   : Ads API only (fetch campaigns + search terms), no forking
  --phase-analyze : forking (calls `claude` per campaign) only, never
                    imports google-ads, so there is no gRPC state to corrupt
  --phase-apply   : Ads API only (writes negatives), no forking
No single process ever both holds a gRPC channel and forks.

Usage    : python3 pmax_brand_generic_audit.py <client_slug> [--confirm] [--days N] [--limit N]
           python3 pmax_brand_generic_audit.py <client_slug> --setup   # first-time: create branded list

           Safe by default: without --confirm, this only ever prints what it
           WOULD negate — no account changes. Pass --confirm to actually
           write. (--dry-run is still accepted as an explicit synonym for
           the default, kept for scripts written against the old flag.)
Changelog: 2026-05-08  Initial version (single-client-only)
           2026-07-24  Split into fetch/analyze/apply subprocesses to fix
                       gRPC-not-fork-safe corruption (see note above)
           2026-07-27  Generalised to any client via client_registry.py +
                       client-brief.md instead of hardcoded per-client constants
           2026-07-25  Flipped write default from live to dry-run — apply
                       phase now requires explicit --confirm to write,
                       instead of --dry-run being something you had to
                       remember to opt into. Wired into the shared change_log.
           2026-07-27  Renamed pmax_audit.py -> pmax_brand_generic_audit.py to
                       free up "pmax_audit" for a separate, simpler script.
"""

import sys
import json
import argparse
import re
import subprocess
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]  # ppc-workspace/
GOOGLE_ADS_YAML = WORKSPACE_ROOT / "google-ads.yaml"

sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))
from client_registry import resolve  # noqa: E402
from change_log import log_change, new_run_id  # noqa: E402


def load_client(slug: str) -> dict:
    try:
        client = resolve(slug)
    except KeyError as e:
        sys.exit(str(e))
    brief_path = WORKSPACE_ROOT / "clients" / client["slug"] / "client-brief.md"
    if not brief_path.exists():
        sys.exit(f"ERROR: no client brief at {brief_path}")
    client["brief_path"] = brief_path
    client["general_negatives_list_id"] = client.get("negative_list_id")
    if not client["general_negatives_list_id"]:
        sys.exit(f"ERROR: client_registry.py entry for '{slug}' has no 'negative_list_id'.")
    return client


def parse_brand_terms(brief_text: str) -> list:
    """Extract the comma-separated list under a '## Brand Term(s)...' heading."""
    match = re.search(
        r"^##\s*Brand Terms?\b.*?\n(.+?)(?=\n##\s|\Z)",
        brief_text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    if not match:
        return []
    raw = match.group(1)
    terms = [t.strip() for chunk in raw.splitlines() for t in chunk.split(",")]
    return [t for t in terms if t and not t.startswith("#")]


def find_claude_binary() -> str:
    import shutil
    binary = shutil.which("claude")
    if binary:
        return binary
    # Fallback: the VS Code extension bundles its own claude binary, which isn't
    # always on PATH. Uses the current user's actual home directory — this used
    # to be hardcoded to one specific developer's username, which would silently
    # fail for every other buyer of this toolkit.
    home = Path.home()
    fallback = sorted(
        Path.home().glob("Library/Application Support/Claude/claude-code/**/claude"),
        key=lambda p: str(p),
    )
    for p in reversed(fallback):
        if "MacOS" in str(p):
            return str(p)
    win_candidates = sorted(
        [
            *home.glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
            *home.glob(".vscode-insiders/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
            *home.glob(".cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
        ],
        key=lambda p: str(p),
    )
    for p in reversed(win_candidates):
        if p.is_file():
            return str(p)
    sys.exit("ERROR: Claude binary not found. Is Claude Code installed?")


def call_claude(prompt: str, claude_binary: str, timeout: int = 1800, model: str = None) -> str:
    cmd = [claude_binary, "--dangerously-skip-permissions"]
    if model:
        cmd += ["--model", model]
    cmd += ["--add-dir", str(WORKSPACE_ROOT), "-p"]
    result = subprocess.run(
        cmd,
        input=prompt, capture_output=True, text=True,
        timeout=timeout, cwd=str(WORKSPACE_ROOT),
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()[-2000:] or f"exit {result.returncode} (no stderr/stdout)"
        raise RuntimeError(f"exit {result.returncode}: {detail}")
    return result.stdout


def classify_campaign(name: str) -> str:
    return "branded" if "branded" in name.lower() else "generic"


def get_pmax_campaigns(ga_service, customer_id):
    query = """
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
          AND campaign.status = 'ENABLED'
    """
    campaigns = []
    for row in ga_service.search(customer_id=customer_id, query=query, timeout=120):
        campaigns.append({
            "id": str(row.campaign.id),
            "name": row.campaign.name,
            "type": classify_campaign(row.campaign.name),
        })
    return campaigns


def get_search_terms(ga_service, customer_id, campaign_id, date_from, date_to):
    query = f"""
        SELECT
            campaign_search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign_search_term_view
        WHERE campaign.id = {campaign_id}
          AND segments.date BETWEEN '{date_from}' AND '{date_to}'
          AND metrics.impressions >= 1
        ORDER BY metrics.cost_micros DESC
        LIMIT 2000
    """
    terms = []
    for row in ga_service.search(customer_id=customer_id, query=query, timeout=120):
        terms.append({
            "term": row.campaign_search_term_view.search_term,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": round(row.metrics.cost_micros / 1_000_000, 2),
            "conversions": row.metrics.conversions,
        })
    return terms


def extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    brace = text.find("{")
    if brace > 0:
        text = text[brace:]
    return json.loads(text)


def analyze_branded_pmax(client, terms, claude_binary, model=None):
    if not client["brand_signals"]:
        raise RuntimeError(
            f"no '## Brand Terms' section found in {client['brief_path']} — "
            f"required to audit a branded PMax campaign for '{client['slug']}'"
        )
    terms_text = "\n".join(
        f"{t['cost']:.2f}|{t['impressions']}i|{t['clicks']}c|{t['conversions']:.0f}cv|{t['term']}"
        for t in terms
    )
    brand_signals_str = ", ".join(client["brand_signals"])

    prompt = f"""You are a PPC specialist auditing a BRANDED Performance Max campaign for {client['name']} ({client['domain']}).

Your task: identify search terms that are GENERIC — they contain NO recognizable brand signal and waste budget in a branded campaign.

Brand signals (a term is "branded" if it contains ANY of these):
{brand_signals_str}

Rules:
- NEGATE: zero brand signal
- KEEP: contains any brand signal, however partial
- When in doubt, KEEP

Search terms (format: cost | impressions | clicks | conversions | term):
{terms_text}

Respond ONLY with valid JSON — no markdown, no explanation outside the JSON (reason: max 3 words):
{{
  "negate": [{{"term": "...", "reason": "no brand signal"}}]
}}"""

    raw = call_claude(prompt, claude_binary, model=model)
    return extract_json(raw)


def analyze_generic_pmax(client, campaign_name, terms, client_brief, claude_binary, model=None):
    terms_text = "\n".join(
        f"{t['cost']:.2f}|{t['impressions']}i|{t['clicks']}c|{t['conversions']:.0f}cv|{t['term']}"
        for t in terms
    )

    prompt = f"""You are a PPC specialist auditing a GENERIC Performance Max campaign: "{campaign_name}" for {client['name']} ({client['domain']}).

CLIENT BRIEF:
{client_brief}

Your task: identify clearly irrelevant search terms to exclude, per the brief's "Always Negate" categories and "Protected"/"NEVER negate" sections.
- KEEP any term with genuine product/purchase intent for what this client sells — including borderline ones
- NEGATE only clear matches to the brief's "Always Negate" categories
- When in doubt, KEEP

Search terms (format: cost | impressions | clicks | conversions | term):
{terms_text}

Respond ONLY with valid JSON — no markdown, no explanation outside the JSON (reason: max 3 words):
{{
  "negate": [{{"term": "...", "reason": "..."}}]
}}"""

    raw = call_claude(prompt, claude_binary, model=model)
    return extract_json(raw)


def add_negatives(ads_client, customer_id, items, list_id, client_slug, dry_run=True, run_id=None):
    if not items or not list_id:
        return 0

    terms = [i["term"] if isinstance(i, dict) else i for i in items]
    reasons = {i["term"]: i.get("reason") for i in items if isinstance(i, dict)}

    if dry_run:
        print(f"    [DRY RUN] Would add {len(terms)} terms to list {list_id} — pass --confirm to write")
        return len(terms)

    shared_criterion_service = ads_client.get_service("SharedCriterionService")
    operations = []
    for term in terms:
        op = ads_client.get_type("SharedCriterionOperation")
        sc = op.create
        sc.shared_set = f"customers/{customer_id}/sharedSets/{list_id}"
        sc.keyword.text = term
        sc.keyword.match_type = ads_client.enums.KeywordMatchTypeEnum.EXACT
        operations.append(op)

    added = 0
    added_terms = []
    for i in range(0, len(operations), 1000):
        batch = operations[i : i + 1000]
        try:
            resp = shared_criterion_service.mutate_shared_criteria(
                customer_id=customer_id,
                operations=batch,
                timeout=60,
            )
            added += len(resp.results)
            added_terms.extend(terms[i : i + 1000])
        except Exception:
            for j, op in enumerate(batch):
                try:
                    resp = shared_criterion_service.mutate_shared_criteria(
                        customer_id=customer_id,
                        operations=[op],
                        timeout=60,
                    )
                    added += len(resp.results)
                    added_terms.append(terms[i + j])
                except Exception:
                    pass

    for term in added_terms:
        log_change(client_slug=client_slug, script="pmax_brand_generic_audit.py", action="add_negative_keyword",
                   resource_type="shared_criterion", resource_id=list_id, detail=term,
                   reason=reasons.get(term), run_id=run_id)
    return added


def setup_branded_pmax_list(client, ads_client, ga_service):
    print(f"Setting up branded PMax generic exclusion list for {client['name']}...\n")
    customer_id = client["customer_id"]

    shared_set_service = ads_client.get_service("SharedSetService")
    op = ads_client.get_type("SharedSetOperation")
    ss = op.create
    ss.name = f"{client['name']} - PMax Branded Generic Exclusions"
    ss.type_ = ads_client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS

    resp = shared_set_service.mutate_shared_sets(customer_id=customer_id, operations=[op], timeout=60)
    new_resource = resp.results[0].resource_name
    new_id = new_resource.split("/")[-1]
    print(f"Created shared set: ID={new_id}")

    campaigns = get_pmax_campaigns(ga_service, customer_id)
    branded = [c for c in campaigns if c["type"] == "branded"]

    if not branded:
        print("WARNING: No ENABLED branded PMax campaign found — apply the list manually.")
    else:
        css_service = ads_client.get_service("CampaignSharedSetService")
        for camp in branded:
            css_op = ads_client.get_type("CampaignSharedSetOperation")
            css = css_op.create
            css.campaign = f"customers/{customer_id}/campaigns/{camp['id']}"
            css.shared_set = new_resource
            css_service.mutate_campaign_shared_sets(customer_id=customer_id, operations=[css_op], timeout=60)
            print(f"Applied to: {camp['name']} (ID: {camp['id']})")

    print(f"\nAdd \"pmax_branded_generic_list_id\": \"{new_id}\" to the '{client['slug']}' entry in scripts/client_registry.py.")
    return new_id


# ─── phase 1: fetch (Ads API only, never forks) ───────────────────────────────

def phase_fetch(client, args):
    from google.ads.googleads.client import GoogleAdsClient
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    ga_service = ads_client.get_service("GoogleAdsService")
    customer_id = client["customer_id"]

    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    campaigns = get_pmax_campaigns(ga_service, customer_id)
    if args.branded_only:
        campaigns = [c for c in campaigns if c["type"] == "branded"]
    elif args.generic_only:
        campaigns = [c for c in campaigns if c["type"] == "generic"]

    for c in campaigns:
        c["terms"] = get_search_terms(ga_service, customer_id, c["id"], date_from, date_to)

    Path(args.out).write_text(json.dumps({
        "date_from": date_from, "date_to": date_to, "campaigns": campaigns,
    }, ensure_ascii=False), encoding="utf-8")


# ─── phase 2: analyze (forks to call `claude`, never imports google-ads) ─────

def phase_analyze(client, args):
    from term_cache import brief_hash, get_cached, set_cached

    data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    client_brief = client["brief_path"].read_text(encoding="utf-8")
    claude_binary = find_claude_binary()
    bh = brief_hash(client_brief)

    results = []
    for campaign in data["campaigns"]:
        terms = campaign["terms"]
        entry = {"id": campaign["id"], "name": campaign["name"], "type": campaign["type"],
                 "terms_total": len(terms), "sent_count": 0, "cache_hits": 0, "negate": [], "error": None}
        if not terms:
            results.append(entry)
            continue

        batch = terms[: args.limit]
        cached, miss_terms = get_cached(client["slug"], campaign["id"], [t["term"] for t in batch], bh)
        miss_items = [t for t in batch if t["term"] in miss_terms]
        entry["sent_count"] = len(miss_items)
        entry["cache_hits"] = len(cached)

        negate = [{"term": term, "reason": info["reason"]} for term, info in cached.items() if info["negate"]]

        if miss_items:
            try:
                if campaign["type"] == "branded":
                    analysis = analyze_branded_pmax(client, miss_items, claude_binary, model=args.model)
                else:
                    analysis = analyze_generic_pmax(client, campaign["name"], miss_items, client_brief, claude_binary, model=args.model)
                new_negate = analysis.get("negate", [])
                negate.extend(new_negate)

                negated_terms = {n["term"] for n in new_negate}
                cache_rows = [
                    {"term": t["term"], "negate": t["term"] in negated_terms,
                     "reason": next((n["reason"] for n in new_negate if n["term"] == t["term"]), None)}
                    for t in miss_items
                ]
                set_cached(client["slug"], campaign["id"], bh, cache_rows)
            except (json.JSONDecodeError, Exception) as e:
                entry["error"] = str(e)

        entry["negate"] = negate
        results.append(entry)

    Path(args.out).write_text(json.dumps({"campaigns": results}, ensure_ascii=False), encoding="utf-8")


# ─── phase 3: apply (Ads API only, never forks) ───────────────────────────────

def phase_apply(client, args):
    from google.ads.googleads.client import GoogleAdsClient
    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    customer_id = client["customer_id"]
    dry_run = not args.confirm  # safe by default — only --confirm writes
    run_id = new_run_id()

    data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    results = []
    for campaign in data["campaigns"]:
        to_negate = campaign["negate"]
        added = 0
        list_id = None
        if to_negate:
            if campaign["type"] == "branded":
                list_id = client.get("pmax_branded_generic_list_id")
                if not list_id:
                    results.append({"id": campaign["id"], "name": campaign["name"], "added": 0, "list_id": None,
                                     "error": f"no 'pmax_branded_generic_list_id' set for '{client['slug']}' — run --setup first"})
                    continue
            else:
                list_id = client["general_negatives_list_id"]
            added = add_negatives(ads_client, customer_id, to_negate, list_id, client["slug"],
                                   dry_run=dry_run, run_id=run_id)
        results.append({"id": campaign["id"], "name": campaign["name"], "added": added, "list_id": list_id})

    Path(args.out).write_text(json.dumps({"campaigns": results}, ensure_ascii=False), encoding="utf-8")


# ─── orchestrator (default mode — never touches google-ads/gRPC itself) ──────

def orchestrate(client, args):
    print(f"{client['name']} — PMax Search Term Audit — {datetime.utcnow().date()}")
    print(f"Mode     : {'LIVE — changes will be applied' if args.confirm else 'DRY RUN (no changes — pass --confirm to write)'}")
    print(f"AI limit : top {args.limit} terms per campaign (by spend)")
    print(f"General negatives list : {client['general_negatives_list_id']}")
    print(f"Branded exclusion list : {client.get('pmax_branded_generic_list_id') or '(none set — run --setup if branded campaigns exist)'}")
    print("=" * 64)

    fetch_out = tempfile.mktemp(suffix=".json", prefix="pmax_fetch_")
    analyze_out = tempfile.mktemp(suffix=".json", prefix="pmax_analyze_")
    apply_out = tempfile.mktemp(suffix=".json", prefix="pmax_apply_")

    try:
        print("\nFetching PMax campaigns and search terms (Ads API)...")
        fetch_cmd = [sys.executable, __file__, client["slug"], "--phase-fetch", "--out", fetch_out, "--days", str(args.days)]
        if args.branded_only:
            fetch_cmd.append("--branded-only")
        if args.generic_only:
            fetch_cmd.append("--generic-only")
        r = subprocess.run(fetch_cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            print(r.stderr)
            sys.exit(f"ERROR: fetch phase failed (exit {r.returncode})")
        fetched = json.loads(Path(fetch_out).read_text(encoding="utf-8"))
        campaigns = fetched["campaigns"]
        print(f"Period   : {fetched['date_from']} -> {fetched['date_to']} ({args.days} days)")

        if not campaigns:
            print("  No ENABLED PMax campaigns found. Exiting.")
            return
        for c in campaigns:
            print(f"  [{c['type'].upper():8s}] {c['name']} (ID: {c['id']})")

        print("\nAnalysing search terms with Claude (subprocess, no Ads API in this phase)...")
        analyze_cmd = [sys.executable, __file__, client["slug"], "--phase-analyze", "--in", fetch_out,
                       "--out", analyze_out, "--limit", str(args.limit)]
        if args.model:
            analyze_cmd += ["--model", args.model]
        r = subprocess.run(analyze_cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            print(r.stderr)
            sys.exit(f"ERROR: analyze phase failed (exit {r.returncode})")
        analyzed = json.loads(Path(analyze_out).read_text(encoding="utf-8"))["campaigns"]

        # attach negate lists back for the apply phase
        apply_input = {"campaigns": []}
        total_campaigns = 0
        for a in analyzed:
            print(f"\n{'─' * 64}")
            print(f"Campaign : {a['name']}")
            print(f"Type     : {a['type'].upper()}")
            if a["terms_total"] == 0:
                print("  No search terms found — skipping.")
                continue
            print(f"  Terms total    : {a['terms_total']}")
            if a["terms_total"] > a["sent_count"] + a.get("cache_hits", 0):
                print(f"  Sending top    : {a['sent_count'] + a.get('cache_hits', 0)} (by cost) to AI")
            if a.get("cache_hits"):
                print(f"  Cache hits     : {a['cache_hits']} (already classified under the current client brief — not re-sent)")
            if a["sent_count"]:
                print(f"  New to AI      : {a['sent_count']}")
            total_campaigns += 1

            if a["sent_count"]:
                print("  Analysing with Claude...")
            if a["error"]:
                print(f"  ERROR: AI analysis failed — {a['error']}")
                continue

            to_negate = a["negate"]
            print(f"\n  NEGATE ({len(to_negate)}):")
            for item in to_negate:
                print(f"    [NEGATE] {item['term']} | {item['reason']}")

            apply_input["campaigns"].append({"id": a["id"], "name": a["name"], "type": a["type"], "negate": to_negate})

        Path(fetch_out).write_text(json.dumps(apply_input, ensure_ascii=False), encoding="utf-8")

        print("\nApplying negatives (Ads API)...")
        apply_cmd = [sys.executable, __file__, client["slug"], "--phase-apply", "--in", fetch_out, "--out", apply_out]
        if args.confirm:
            apply_cmd.append("--confirm")
        r = subprocess.run(apply_cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print(r.stderr)
            sys.exit(f"ERROR: apply phase failed (exit {r.returncode})")
        applied = json.loads(Path(apply_out).read_text(encoding="utf-8"))["campaigns"]

        total_negated = 0
        for res in applied:
            if res.get("error"):
                print(f"\n  ERROR [{res['name']}]: {res['error']}")
                continue
            if res["added"]:
                list_name = "PMax Branded - Generic Exclusions" if res["list_id"] == client.get("pmax_branded_generic_list_id") else "General Negatives"
                verb = "Added" if args.confirm else "Would add"
                print(f"\n  {verb} {res['added']} terms -> {list_name} ({res['list_id']}) [{res['name']}]")
                total_negated += res["added"]

        print(f"\n{'=' * 64}")
        print("SUMMARY")
        print(f"  Campaigns analysed : {total_campaigns}")
        print(f"  Terms negated      : {total_negated}")
        print(f"  Mode               : {'LIVE — changes applied' if args.confirm else 'DRY RUN — no changes made, pass --confirm to write'}")
        print(f"\n=== Audit finished successfully at {datetime.now()} ===")
    finally:
        for p in (fetch_out, analyze_out, apply_out):
            if os.path.exists(p):
                os.unlink(p)


def main():
    parser = argparse.ArgumentParser(description="PMax Search Term Audit — any client")
    parser.add_argument("client", help="Client slug from client_registry.py (e.g. acme)")
    parser.add_argument("--confirm", action="store_true",
                         help="Actually write to the account. Without this, dry-run only (the default).")
    parser.add_argument("--dry-run", action="store_true",
                         help=argparse.SUPPRESS)  # accepted no-op — dry-run is now the default regardless
    parser.add_argument("--days", type=int, default=4)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--branded-only", action="store_true")
    parser.add_argument("--generic-only", action="store_true")
    parser.add_argument("--model", default=None, help="Model for the claude CLI subprocess (e.g. fable, opus, sonnet)")
    # internal phase flags — not for direct use, orchestrate() calls itself with these
    parser.add_argument("--phase-fetch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--phase-analyze", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--phase-apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--in", dest="inp", help=argparse.SUPPRESS)
    parser.add_argument("--out", help=argparse.SUPPRESS)
    args = parser.parse_args()

    client = load_client(args.client)
    client["brand_signals"] = parse_brand_terms(client["brief_path"].read_text(encoding="utf-8"))

    if args.phase_fetch:
        phase_fetch(client, args)
        return
    if args.phase_analyze:
        phase_analyze(client, args)
        return
    if args.phase_apply:
        phase_apply(client, args)
        return

    if args.setup:
        try:
            from google.ads.googleads.client import GoogleAdsClient
        except ImportError:
            sys.exit("ERROR: google-ads not installed. Run: pip install google-ads")
        ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
        ga_service = ads_client.get_service("GoogleAdsService")
        setup_branded_pmax_list(client, ads_client, ga_service)
        return

    orchestrate(client, args)


if __name__ == "__main__":
    main()
