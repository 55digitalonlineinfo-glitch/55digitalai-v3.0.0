#!/usr/bin/env python3
"""
cro_audit.py - backing script for /55-cro-audit (website conversion-rate audit, 342 checks).

Purpose
    The audit is a long fixed checklist (system-prompts/frameworks/cro-audit-checklist.txt).
    The failure mode of a long checklist is silently skipping items. This script makes that
    impossible to do unnoticed:
      1. Every check has a stable ID (GEN-01 ... TYP-23) assigned from the file order.
      2. EXPECTED_COUNTS pins how many checks each section must have (taken from the source
         list the source list supplied). `list` refuses to run if the file drifted.
      3. `scaffold` writes a results file with EVERY selected ID set to TODO.
      4. `validate` / `report` / the PDF refuse to finish while any ID is still TODO or has
         no evidence. A skipped item shows up as an error, never as a quietly shorter report.
    Judgement (is this page's CTA prominent?) is done by Claude from screenshots + the DOM
    facts from `capture`; this script only guarantees completeness and does the formatting.

Usage
    python3 scripts/cro_audit.py list [--sections HOME,PDP]           # menu + every point
    python3 scripts/cro_audit.py lang <slug>                      # language the business runs in (for the report)
    python3 scripts/cro_audit.py funnel <slug> [--start YYYY-MM-DD --end YYYY-MM-DD]   # GA4 sales funnel, start to end
    python3 scripts/cro_audit.py capture <slug> --page home=URL [--page pdp=URL ...]
    python3 scripts/cro_audit.py scaffold <slug> --sections ALL|GEN,HOME,...
    python3 scripts/cro_audit.py validate <results.json>
    python3 scripts/cro_audit.py report <results.json>                # text report + .md file
    PDF: scripts/cro_report_pdf.py <results.json> --brand brand.json

Statuses (results.json -> items.<ID>.status)
    PASS     implemented properly         FAIL    missing or broken
    PARTIAL  there but weak/incomplete    N/A     does not apply to this business (reason required)
    MANUAL   cannot be verified from outside the site (needs test purchase, GA4/GTM, CRM,
             email inbox...) - say exactly what is needed
    TODO     not assessed yet (scaffold default) - blocks validate/report

Changelog
    2026-10-28  Initial version.
    2026-10-28  `funnel` subcommand (GA4 ordered sales funnel, start to end, step-to-step %) + funnel_stats() used by the PDF.
"""
import argparse, json, os, re, sys, time
from collections import OrderedDict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKLIST = os.path.join(ROOT, "system-prompts", "frameworks", "cro-audit-checklist.txt")

SECTIONS = OrderedDict([
    ("GEN", "General & Navigation (site-wide)"),
    ("HOME", "Home page"),
    ("CAT", "Category page"),
    ("LP", "Landing page"),
    ("PDP", "Product page"),
    ("CART", "Cart page"),
    ("CHK", "Checkout page"),
    ("TYP", "Thank-you page"),
])
# Counts taken from the source list. If the checklist file ever loses/gains a line,
# `load()` stops with an error instead of auditing a shortened list.
EXPECTED_COUNTS = {"GEN": 25, "HOME": 20, "CAT": 46, "LP": 75, "PDP": 78, "CART": 30, "CHK": 45, "TYP": 23}
STATUSES = ("PASS", "FAIL", "PARTIAL", "N/A", "MANUAL", "TODO")
PRIO = {"H": "High", "M": "Medium", "L": "Low"}


def load():
    items, counters = OrderedDict(), {}
    for ln, raw in enumerate(open(CHECKLIST, encoding="utf-8"), 1):
        raw = raw.rstrip("\n")
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("|", 3)
        if len(parts) != 4 or parts[0] not in SECTIONS or parts[2] not in PRIO:
            sys.exit(f"checklist line {ln} malformed: {raw[:80]}")
        code, group, prio, text = parts
        counters[code] = counters.get(code, 0) + 1
        cid = f"{code}-{counters[code]:02d}"
        items[cid] = dict(id=cid, section=code, group=group, priority=prio, text=text.strip())
    for code, want in EXPECTED_COUNTS.items():
        if counters.get(code, 0) != want:
            sys.exit(f"CHECKLIST DRIFT: {code} has {counters.get(code, 0)} checks, expected {want}. "
                     f"Fix {CHECKLIST} - do not audit a shortened list.")
    return items


def pick_sections(arg):
    if not arg or arg.upper() == "ALL":
        return list(SECTIONS)
    codes = [c.strip().upper() for c in arg.split(",") if c.strip()]
    bad = [c for c in codes if c not in SECTIONS]
    if bad:
        sys.exit(f"unknown section(s) {bad}; valid: {', '.join(SECTIONS)}")
    return codes


def cmd_list(a):
    items = load()
    codes = pick_sections(a.sections)
    total = sum(EXPECTED_COUNTS[c] for c in codes)
    print("CRO AUDIT - available sections (counts verified against the source list)\n")
    for i, (code, title) in enumerate(SECTIONS.items(), 1):
        print(f"  {i}. [{code}] {title}: {EXPECTED_COUNTS[code]} checks")
    print(f"\n  Full audit = {sum(EXPECTED_COUNTS.values())} checks.  Selected now: {total}\n")
    for code in codes:
        print(f"\n=== [{code}] {SECTIONS[code]} - {EXPECTED_COUNTS[code]} checks ===")
        grp = None
        for it in items.values():
            if it["section"] != code:
                continue
            if it["group"] != grp:
                grp = it["group"]
                print(f"  -- {grp}")
            print(f"  {it['id']} [{PRIO[it['priority']]}] {it['text']}")


def results_path(slug):
    d = os.path.join(ROOT, "clients", slug, "reports")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"cro_audit_{date.today().isoformat()}.json")


def cmd_scaffold(a):
    items = load()
    codes = pick_sections(a.sections)
    out = a.out or results_path(a.slug)
    if os.path.exists(out) and not a.force:
        sys.exit(f"{out} exists (it may hold finished work). Use --force to overwrite.")
    data = dict(client=a.slug, date=date.today().isoformat(), sections=codes,
                pages={}, notes="",
                items={cid: dict(status="TODO", evidence="", fix="") for cid, it in items.items() if it["section"] in codes})
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Scaffolded {len(data['items'])} checks (all TODO) -> {out}")


def check_results(path, quiet=False):
    items = load()
    d = json.load(open(path, encoding="utf-8"))
    problems, counts = [], {s: 0 for s in STATUSES}
    want = [cid for cid, it in items.items() if it["section"] in d["sections"]]
    for cid in want:
        r = d["items"].get(cid)
        if r is None:
            problems.append(f"{cid}: MISSING from results ({items[cid]['text'][:60]})"); continue
        st = r.get("status", "TODO")
        if st not in STATUSES:
            problems.append(f"{cid}: invalid status {st!r}"); continue
        counts[st] += 1
        if st == "TODO":
            problems.append(f"{cid}: still TODO ({items[cid]['text'][:60]})")
        elif not (r.get("evidence") or "").strip():
            problems.append(f"{cid}: {st} but no evidence")
        elif st in ("FAIL", "PARTIAL") and not (r.get("fix") or "").strip():
            problems.append(f"{cid}: {st} but no fix")
        elif st == "N/A" and len(r["evidence"].strip()) < 8:
            problems.append(f"{cid}: N/A needs a real reason")
    extra = [c for c in d["items"] if c not in items]
    problems += [f"{c}: unknown id" for c in extra]
    if not quiet:
        print(f"Checks expected: {len(want)}   recorded: {sum(counts.values())}")
        print("  " + "  ".join(f"{s}={n}" for s, n in counts.items()))
    return items, d, problems, counts


def cmd_validate(a):
    _, _, problems, _ = check_results(a.results)
    if problems:
        print(f"\nINCOMPLETE - {len(problems)} problem(s):")
        for p in problems[:80]:
            print("  " + p)
        if len(problems) > 80:
            print(f"  ... and {len(problems) - 80} more")
        sys.exit(1)
    print("COMPLETE - every selected check has a verdict and evidence.")


def cmd_report(a):
    items, d, problems, counts = check_results(a.results)
    if problems and not a.allow_incomplete:
        print(f"\nREFUSING to report: {len(problems)} check(s) incomplete. Run `validate` to see them.")
        sys.exit(1)
    L = []
    w = L.append
    w(f"# CRO audit - {d['client']} - {d['date']}\n")
    for k, v in (d.get("pages") or {}).items():
        w(f"- {k}: {v}")
    w("")
    w("## Summary\n")
    w("| Section | Checks | PASS | PARTIAL | FAIL | MANUAL | N/A | TODO |\n|---|---|---|---|---|---|---|---|")
    tot = {s: 0 for s in STATUSES}
    for code in d["sections"]:
        c = {s: 0 for s in STATUSES}
        for cid, it in items.items():
            if it["section"] == code:
                c[d["items"].get(cid, {}).get("status", "TODO")] += 1
        for s in STATUSES:
            tot[s] += c[s]
        w(f"| {SECTIONS[code]} | {sum(c.values())} | {c['PASS']} | {c['PARTIAL']} | {c['FAIL']} | {c['MANUAL']} | {c['N/A']} | {c['TODO']} |")
    w(f"| **Total** | **{sum(tot.values())}** | {tot['PASS']} | {tot['PARTIAL']} | {tot['FAIL']} | {tot['MANUAL']} | {tot['N/A']} | {tot['TODO']} |\n")
    # priority fixes: High-priority FAIL first, then High PARTIAL, then the rest
    order = {"H": 0, "M": 1, "L": 2}
    rank = lambda cid: (0 if d["items"][cid]["status"] == "FAIL" else 1, order[items[cid]["priority"]])
    todo = sorted((c for c in d["items"] if d["items"][c]["status"] in ("FAIL", "PARTIAL")), key=rank)
    w("## Fix list (FAIL first, High priority first)\n")
    for cid in todo:
        r, it = d["items"][cid], items[cid]
        w(f"- **{cid}** [{r['status']} / {PRIO[it['priority']]}] {it['text']}\n  - Found: {r['evidence']}\n  - Fix: {r['fix']}")
    w("")
    w("## Full checklist (every point, source order)\n")
    for code in d["sections"]:
        w(f"### {SECTIONS[code]}\n")
        grp = None
        for cid, it in items.items():
            if it["section"] != code:
                continue
            if it["group"] != grp:
                grp = it["group"]
                w(f"\n**{grp}**\n\n| ID | Priority | Status | Check | Evidence | Fix |\n|---|---|---|---|---|---|")
            r = d["items"].get(cid, {})
            cell = lambda t: (t or "").replace("|", "/").replace("\n", " ")
            w(f"| {cid} | {PRIO[it['priority']]} | {r.get('status', 'TODO')} | {cell(it['text'])} | {cell(r.get('evidence'))} | {cell(r.get('fix'))} |")
        w("")
    text = "\n".join(L)
    if "\u2014" in text:
        text = text.replace("\u2014", "-")
    out = os.path.splitext(a.results)[0] + ".md"
    open(out, "w", encoding="utf-8").write(text)
    print(text)
    print(f"\n[saved {out}]")


# ---------------------------------------------------------------- capture (Playwright)
SIGNALS_JS = r"""
() => {
  const q = s => [...document.querySelectorAll(s)];
  const txt = document.body.innerText.toLowerCase();
  const has = re => re.test(txt);
  const fixed = q('*').filter(e => ['fixed','sticky'].includes(getComputedStyle(e).position) && e.getBoundingClientRect().width > 150 && e.offsetHeight > 20)
      .slice(0, 12).map(e => (e.tagName + '.' + (e.className||'').toString().slice(0, 40) + ' @' + getComputedStyle(e).position));
  const ctas = q('a,button,input[type=submit]').filter(e => e.offsetHeight > 28 && e.getBoundingClientRect().top < innerHeight)
      .slice(0, 25).map(e => (e.innerText || e.value || '').trim().slice(0, 40)).filter(Boolean);
  const forms = q('form').map(f => ({fields: f.querySelectorAll('input:not([type=hidden]),select,textarea').length,
      hidden: [...f.querySelectorAll('input[type=hidden]')].map(i => i.name).filter(Boolean).slice(0, 12),
      gclid: !!f.querySelector('input[name*=gclid i],input[id*=gclid i]'),
      action: (f.action||'').slice(0, 80)}));
  const ld = q('script[type="application/ld+json"]').map(s => { try { const j = JSON.parse(s.textContent); return [].concat(j['@graph'] || j).map(x => x['@type']).flat().join(','); } catch (e) { return 'invalid'; } });
  const nav = performance.getEntriesByType('navigation')[0] || {};
  return {
    url: location.href, title: document.title, title_len: document.title.length,
    h1: q('h1').map(h => h.innerText.trim().slice(0, 90)), meta_desc: (document.querySelector('meta[name=description]')||{}).content || null,
    viewport_meta: !!document.querySelector('meta[name=viewport]'), https: location.protocol === 'https:',
    load_ms: Math.round(nav.loadEventEnd || 0), dcl_ms: Math.round(nav.domContentLoadedEventEnd || 0),
    schema_types: ld, forms, fixed_or_sticky: fixed, above_fold_ctas: ctas,
    images: q('img').length, images_no_alt: q('img').filter(i => !i.alt).length,
    h_scroll_mobile: document.documentElement.scrollWidth > innerWidth + 2,
    search_input: q('input[type=search],input[name*=search i],input[name=s],input[placeholder*=search i],input[placeholder*=szukaj i],input[placeholder*=пошук i]').length,
    breadcrumbs: q('[class*=breadcrumb i],nav[aria-label*=breadcrumb i]').length,
    sort_select: q('select[name*=order i],select[name*=sort i],[class*=sort i]').length,
    filters: q('[class*=filter i]').length, wishlist: has(/wishlist|lista życzeń|обране|список бажань|ulubione/),
    reviews_words: has(/review|opini|відгук|rating|ocen/), stars: q('[class*=star i],[class*=rating i]').length,
    urgency_words: has(/only \d+ left|zostało|залишилось|limited|countdown|ends in|тільки \d+|ostatnie/),
    free_shipping_words: has(/free shipping|darmowa dostawa|безкоштовна доставка|bezpłatna/),
    payment_words: [...new Set((txt.match(/visa|mastercard|paypal|apple pay|google pay|blik|przelewy24|liqpay|monobank|fondy/g) || []))],
    trust_words: has(/ssl|secure|bezpiecz|безпечн|gwarancj|гарант|money.back|zwrot|повернення/),
    privacy_link: q('a').some(a => /privacy|polityka prywatno|конфіденцій/i.test(a.href + a.innerText)),
    cookie_banner: q('[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[id*=cmplz i]').filter(e => e.offsetHeight > 30).length,
    popups_visible: q('[role=dialog],[class*=popup i],[class*=modal i]').filter(e => e.offsetHeight > 100 && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden').length,
    analytics: {gtm: !!window.google_tag_manager, gtag: typeof window.gtag === 'function', dataLayer: Array.isArray(window.dataLayer) ? window.dataLayer.length : 0, fbq: typeof window.fbq === 'function'},
    top_bar: !!q('[class*=topbar i],[class*=top-bar i],[class*=announcement i],[class*=promo-bar i]').length,
    live_chat: has(/live chat|czat|чат/) || !!q('[id*=chat i],[class*=chat i],iframe[src*=tawk],iframe[src*=intercom]').length,
    tel_links: q('a[href^="tel:"]').length, mailto_links: q('a[href^="mailto:"]').length,
    nav_depth: Math.max(0, ...q('nav ul ul ul').map(() => 3), ...q('nav ul ul').map(() => 2), 1),
  };
}
"""


def cmd_capture(a):
    from playwright.sync_api import sync_playwright
    outdir = os.path.join(ROOT, "clients", a.slug, "reports", f"cro_audit_{date.today().isoformat()}", "capture")
    os.makedirs(outdir, exist_ok=True)
    pages = dict(p.split("=", 1) for p in a.page)
    if not pages:
        sys.exit("give at least one --page name=URL (e.g. --page home=https://example.com/)")
    summary = {}
    with sync_playwright() as p:
        br = p.chromium.launch()
        for name, url in pages.items():
            for dev, ctxargs in (("desktop", dict(viewport={"width": 1440, "height": 900})),
                                 ("mobile", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True))):
                ctx = br.new_context(**ctxargs)
                pg = ctx.new_page()
                try:
                    t0 = time.time()
                    pg.goto(url, wait_until="load", timeout=60000)
                    pg.wait_for_timeout(2500)
                    sig = pg.evaluate(SIGNALS_JS)
                    sig["wall_load_s"] = round(time.time() - t0, 1)
                    pg.screenshot(path=os.path.join(outdir, f"{name}_{dev}_fold.png"))
                    pg.screenshot(path=os.path.join(outdir, f"{name}_{dev}_full.png"), full_page=True)
                    summary[f"{name}_{dev}"] = sig
                    print(f"[{name}/{dev}] {url} - load {sig['wall_load_s']}s, forms={len(sig['forms'])}, cookie_banner={sig['cookie_banner']}, popups={sig['popups_visible']}")
                except Exception as e:  # keep going: a blocked page must not hide the others
                    summary[f"{name}_{dev}"] = {"error": str(e)[:200]}
                    print(f"[{name}/{dev}] ERROR {str(e)[:120]} - ask the user for a screenshot of this page")
                ctx.close()
        br.close()
    out = os.path.join(outdir, "signals.json")
    json.dump(summary, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nSignals -> {out}\nScreenshots -> {outdir}/<page>_<desktop|mobile>_<fold|full>.png (view with `sips -Z 1400`, then Read)")


# ---------------------------------------------------------------- report language
REPORT_LANGS = ("en", "uk", "pl")            # the PDF has full label sets for these three
COUNTRY_LANG = {"UA": "uk", "PL": "pl"}      # fallback when the site does not say


def _text_language(html_text):
    """Guess the language from the visible text itself (the <html lang> tag is often a CMS default, e.g. a site may say
    'en'). Returns (lang, why) or (None, ''). Needs enough letters to be confident."""
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text)
    t = re.sub(r"<[^>]+>", " ", t).lower()
    letters = re.findall(r"[a-zа-яіїєґёыэъąćęłńóśźż]", t)
    if len(letters) < 300:
        return None, ""
    n = len(letters)
    cyr = sum(1 for c in letters if "а" <= c <= "я" or c in "іїєґёыэъ")
    uk = sum(t.count(c) for c in "іїєґ")
    ru = sum(t.count(c) for c in "ыэъё")
    pl = sum(t.count(c) for c in "ąćęłńóśźż")
    if cyr / n > 0.3:
        return ("uk" if uk >= ru else "ru"), f"page text is {cyr * 100 // n}% Cyrillic ({uk} Ukrainian-only vs {ru} Russian-only letters)"
    if pl / n > 0.015:
        return "pl", f"page text has Polish letters ({pl} of {n})"
    return None, ""


def detect_language(slug):
    """Language the client's business runs in -> (lang, source). Order: the homepage's visible text, then its
    <html lang>, then the client's country in clients.json. Never retries with a disguised user agent: if the
    site refuses the request it falls back to the country. A language the PDF has no labels for becomes 'en'."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from client_registry import resolve
    c = resolve(slug)
    c["domain"] = re.sub(r"^https?://", "", c["domain"]).strip("/")   # tolerate a domain saved with its scheme
    lang, src = None, ""
    try:
        import urllib.request
        req = urllib.request.Request(f"https://{c['domain']}/", headers={"User-Agent": "cro-audit-language-check"})
        head = urllib.request.urlopen(req, timeout=15).read(400000).decode("utf-8", "ignore")
        lang, why = _text_language(head)
        if lang:
            src = f"{why}, https://{c['domain']}/"
        else:
            m = re.search(r"<html[^>]*\blang=[\"']?([A-Za-z]{2})", head, re.I)
            if m:
                lang, src = m.group(1).lower(), f"<html lang> on https://{c['domain']}/"
    except Exception as e:
        src = f"site not readable ({type(e).__name__})"
    if lang == "en" and COUNTRY_LANG.get(c.get("country")) and "<html lang>" in src:
        # the tag alone says 'en' but the text was not conclusive: that is usually a CMS default, trust the country
        lang, src = COUNTRY_LANG[c["country"]], src + f" says 'en' (often a CMS default); using country {c['country']} from clients.json - confirm with the user"
    if not lang:
        lang, src = COUNTRY_LANG.get(c.get("country"), "en"), (src + "; " if src else "") + f"country {c.get('country')} in clients.json"
    if lang not in REPORT_LANGS:
        src += f"; '{lang}' has no PDF label set, using en"
        lang = "en"
    return lang, src


def cmd_lang(a):
    lang, src = detect_language(a.slug)
    print(f"{a.slug}: report language = {lang}  (source: {src})")


# ---------------------------------------------------------------- GA4 sales funnel
# Rough ecommerce ranges per step transition (index = step -> next step). Directional only, not a sourced study.
# (low, high) share of the previous step; below low = improve, inside = ok, above high = good.
FUNNEL_BENCH = {2: (0.05, 0.10), 3: (0.50, 0.70), 4: (0.40, 0.55)}


def _verdict(pct, bench, gap):
    """gap (stage larger than the previous one) beats everything: the rate is not trustworthy. None = no benchmark."""
    if gap:
        return "gap"
    if not bench or pct is None:
        return None
    return "improve" if pct < bench[0] else ("good" if pct > bench[1] else "ok")


def bench_text(b):
    return f"{round(b[0] * 100)}-{round(b[1] * 100)}%" if b else ""


def funnel_stats(data):
    """ga4_funnel_export.py JSON -> [{name, users, pct_first, pct_prev, lost, flag, bench, devices}] in funnel order.
    The export is an OPEN funnel (a user may enter at any step), so a step can exceed the previous one: that is a
    tracking gap (event missing upstream or fired without a real previous step) and is flagged, never hidden."""
    # optional per-client override (e.g. high-ticket stores): {"bench": {"2": [lo, hi], ...}} in the funnel JSON
    BENCH = {int(k): tuple(v) for k, v in data.get("bench", {}).items()} or FUNNEL_BENCH
    rows = []
    for i, st in enumerate(data["steps"]):
        name = re.sub(r"^\d+\.\s*", "", st["name"])
        users = st["users"]
        prev = rows[-1]["users"] if rows else None
        pct_prev = (users / prev) if prev else None
        rows.append(dict(
            name=name, users=users,
            pct_first=users / data["steps"][0]["users"] if data["steps"][0]["users"] else 0,
            pct_prev=pct_prev,
            lost=(prev - users) if prev is not None and users <= prev else 0,
            flag=("more users than the previous step - tracking gap" if prev is not None and users > prev else ""),
            bench=BENCH.get(i),
            verdict=_verdict(pct_prev, BENCH.get(i), prev is not None and users > prev),
            devices={d: v["users"] for d, v in st.get("breakdown", {}).items()}))
    return rows


def cmd_funnel(a):
    """Fetch the GA4 ordered sales funnel for the audit period, save it, print start-to-end with step-to-step rates."""
    import subprocess
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from client_registry import resolve
    btype = resolve(a.slug).get("business_type")
    if btype != "ecommerce":
        sys.exit(f"{a.slug} is '{btype}', not ecommerce: the sales funnel is only for ecommerce clients. "
                 f"For lead-gen use: python3 scripts/ga4_reports.py run {a.slug} lead_funnel")
    outdir = os.path.join(ROOT, "clients", a.slug, "reports", f"cro_audit_{date.today().isoformat()}")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "ga4_funnel.json")
    cmd = [sys.executable, os.path.join(ROOT, "scripts", "ga4_funnel_export.py"), a.slug, "--out", out]
    if a.start: cmd += ["--start", a.start]
    if a.end: cmd += ["--end", a.end]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("GA4 funnel failed:\n" + r.stderr[-600:])
    data = json.load(open(out, encoding="utf-8"))
    rows = funnel_stats(data)
    print(f"GA4 sales funnel - {a.slug} - {data['date_from']} to {data['date_to']} (users per step, open funnel)\n")
    top = rows[0]["users"] or 1
    for r_ in rows:
        bar = "#" * max(1, round(40 * r_["users"] / top))
        step = "" if r_["pct_prev"] is None else f"  {r_['pct_prev']*100:5.1f}% of previous step"
        lost = f", lost {r_['lost']:,}" if r_["lost"] else ""
        bench = (f"  (typical {bench_text(r_['bench'])} -> {r_['verdict'].upper()})" if r_["bench"] and r_["verdict"] else "")
        print(f"{r_['name']:<16}{r_['users']:>7,}  {bar:<40}{step}{lost}{bench}")
        if r_["flag"]:
            print(f"{'':<16}!! {r_['flag']}")
    print(f"\nOverall: {rows[-1]['users']:,} of {rows[0]['users']:,} users purchased = {rows[-1]['pct_first']*100:.2f}%")
    print("Device split per step: " + "; ".join(f"{x['name']}: " + ", ".join(f"{d} {n:,}" for d, n in x['devices'].items()) for x in rows))
    print(f"\nSaved -> {out} (the client PDF adds this as its last page)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lang"); s.add_argument("slug"); s.set_defaults(f=cmd_lang)
    s = sub.add_parser("funnel"); s.add_argument("slug"); s.add_argument("--start"); s.add_argument("--end"); s.set_defaults(f=cmd_funnel)
    s = sub.add_parser("list"); s.add_argument("--sections"); s.set_defaults(f=cmd_list)
    s = sub.add_parser("capture"); s.add_argument("slug"); s.add_argument("--page", action="append", default=[]); s.set_defaults(f=cmd_capture)
    s = sub.add_parser("scaffold"); s.add_argument("slug"); s.add_argument("--sections", default="ALL")
    s.add_argument("--out"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_scaffold)
    s = sub.add_parser("validate"); s.add_argument("results"); s.set_defaults(f=cmd_validate)
    s = sub.add_parser("report"); s.add_argument("results"); s.add_argument("--allow-incomplete", action="store_true"); s.set_defaults(f=cmd_report)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
