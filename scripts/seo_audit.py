#!/usr/bin/env python3
"""
seo_audit.py - backing script for /55-seo-audit (GEO + classic SEO + mobile + sitemap audit, 218 checks).

Purpose
    The audit checklist is system-prompts/frameworks/geo-audit-framework.md (15 GEO items, sections
    A-P classic technical/on-page SEO and E-E-A-T, a Mobile Audit and a Sitemap Health Check). A long
    checklist fails by silently skipping items, so this script:
      1. Parses every "- [ ]" bullet of that file and gives it a stable ID
         (C01-1 ... C15-2 for the 15 GEO items, A-01 ... P-11, MOB-01 ..., MAP-01 ...).
      2. Pins the expected count per section (EXPECTED_COUNTS). If the framework file gains or
         loses a bullet, every command stops with an error instead of auditing a shortened list.
      3. `scaffold` writes a results file with EVERY check in it: checks the script can measure from
         outside are pre-filled from the capture (status + measured value + evidence, marked auto),
         checks that need tools we do not have (Search Console, SEMrush, Grammarly, a real device...)
         are pre-filled FAIL with `needs` naming what is missing, and everything else is TODO.
      4. `validate` / `report` refuse to finish while any check is TODO. A skipped check is an error,
         never a shorter report.
    Judgement (is there an attributed expert quote? does the page open with a direct answer?) is done by
    Claude from the page text + the signals in capture.json; this script guarantees completeness,
    measures the mechanical things and formats the report in the agency's required 6-column format.

Usage
    python3 scripts/seo_audit.py list [--sections C01,A,MOB]            # menu + every check, with Impact
    python3 scripts/seo_audit.py capture <url> [--slug SLUG] [--pages 8] [--page URL ...]
    python3 scripts/seo_audit.py scaffold <url|slug> [--sections ALL|C01,C02,A,...]
    python3 scripts/seo_audit.py validate <results.json>
    python3 scripts/seo_audit.py report <results.json>                # chat text + .md, same folder
    python3 scripts/seo_audit.py pdf <results.json> --show failed|failed+passed|all   # client PDF; ALWAYS ask the user which (see /55-seo-audit Step 5)

    Output folder: clients/<slug>/reports/seo_audit_YYYY-MM-DD/ when --slug is given (client site),
    seo-audits/<host>/seo_audit_YYYY-MM-DD/ otherwise (the agency's own site). Holds capture.json,
    results.json, report.md.

Results file (results.json -> items.<ID>)
    status       PASS | FAIL | N/A | TODO. Binary on purpose (agency rule): a check that cannot be verified with
                 the tools available is FAIL with `needs` naming the missing tool, never a third bucket.
                 N/A only with a real reason in `evidence` (e.g. "no AMP on this site").
    measured     the real number/value behind a threshold check; for multi-page checks one line per failing page
                 (e.g. "/services/ - 78 chars"). Empty when the check has no natural number.
    evidence     what was actually seen/measured, on which page.
    fix          concrete fix for every FAIL.
    needs        (FAIL only) the tool/access that was missing, shown as "FAIL (needs GSC access)".
    why, consequence   optional per-item overrides of the section default texts below.

Impact (1-10) is a fixed property of the ITEM (see IMPACT_*), the same on every site, per the anchors in
the framework file's "Suggested audit output format".

Changelog
    2026-11-13  capture: de-duplicated page list (a --page equal to the target was sampled twice -> false duplicate
                title/description fails); thin-sitemap fallback also samples the homepage's links when the target is an
                inner or JS-shell page (one JS-shell site sampled only 3 pages).
    2026-11-11  Initial version.
    2026-11-11  PDF restyled to the dark A4 glass look of /55-web-guidelines-audit (cover + section list, Fix-first pages, one glass card per check).
    2026-11-11  PDF cards now show Finding / Why we need it (if done right, if not) / Proposed fix + priority tag + Fix-first summary page.
    2026-11-11  `pdf` subcommand with --show failed|failed+passed|all (user chooses what the client sees).
"""
import argparse, json, os, re, sys, time, urllib.parse
from collections import OrderedDict
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMEWORK = os.path.join(ROOT, "system-prompts", "frameworks", "geo-audit-framework.md")

SECTIONS = OrderedDict([
    ("C01", "GEO 1. Crawlability / access (BLOCKING)"), ("C02", "GEO 2. Server-side rendering"),
    ("C03", "GEO 3. Direct source citations"), ("C04", "GEO 4. Expert quotes"),
    ("C05", "GEO 5. Statistics with clear sourcing"), ("C06", "GEO 6. Fluent, readable language"),
    ("C07", "GEO 7. Answer-first structure"), ("C08", "GEO 8. Content matched to real questions"),
    ("C09", "GEO 9. Structured data / schema"), ("C10", "GEO 10. Content freshness"),
    ("C11", "GEO 11. Entity consistency"), ("C12", "GEO 12. One idea per paragraph"),
    ("C13", "GEO 13. SEO fundamentals underneath"), ("C14", "GEO 14. Domain / brand authority"),
    ("C15", "GEO 15. Multi-platform presence"),
    ("A", "A. Technical / site architecture"), ("B", "B. On-page keyword placement"), ("C", "C. Internal linking"),
    ("D", "D. Competitor benchmarking"), ("E", "E. Content quality & E-E-A-T"), ("F", "F. Images & video"),
    ("G", "G. UX & conversion"), ("H", "H. Local SEO tactics"), ("I", "I. Ongoing workflow"),
    ("J", "J. Search Console / indexing health"), ("K", "K. Benchmarks & competitive metrics"),
    ("L", "L. Site architecture - URLs, silos, multi-location"), ("M", "M. Technical infrastructure"),
    ("N", "N. Schema - additional tactical notes"), ("O", "O. Legal & trust pages"), ("P", "P. Content audit additions"),
    ("MOB", "Mobile Audit"), ("MAP", "Sitemap Health Check"),
])
# Bullet counts taken from the framework file on 2026-11-11 (218). If the file changes, update the file AND
# this table together - the point is that a shortened list can never be audited by accident.
EXPECTED_COUNTS = {"C01": 3, "C02": 3, "C03": 2, "C04": 2, "C05": 2, "C06": 2, "C07": 2, "C08": 2, "C09": 7, "C10": 4,
                   "C11": 3, "C12": 2, "C13": 1, "C14": 2, "C15": 2, "A": 3, "B": 12, "C": 5, "D": 8, "E": 15, "F": 9,
                   "G": 8, "H": 7, "I": 4, "J": 15, "K": 5, "L": 21, "M": 19, "N": 13, "O": 3, "P": 11, "MOB": 12, "MAP": 9}
STATUSES = ("PASS", "FAIL", "N/A", "TODO")

# ---- Impact 1-10: section default, then keyword overrides (first match wins). Anchors: see the framework file. ----
IMPACT_SECTION = {"C01": 10, "C02": 9, "C03": 9, "C04": 9, "C05": 9, "C06": 7, "C07": 8, "C08": 8, "C09": 8, "C10": 7,
                  "C11": 5, "C12": 6, "C13": 7, "C14": 5, "C15": 6, "A": 6, "B": 7, "C": 6, "D": 5, "E": 5, "F": 5,
                  "G": 4, "H": 5, "I": 4, "J": 6, "K": 3, "L": 5, "M": 7, "N": 4, "O": 2, "P": 5, "MOB": 8, "MAP": 6}
IMPACT_RULES = [
    ("fully on https", 10), ("core web vitals", 9), ("fully responsive", 9), ("no intrusive pop-ups", 7),
    ("legacy `meta keywords`", 2), ("print-friendly", 2), ("mega menu", 2), ("domain age", 2), ("award", 1),
    ("privacy policy and terms", 1), ("open graph", 3), ("favicon", 3), ("domain's history", 3), ("same server/ip", 2),
    ("subdomains vs. subfolders", 3), ("amp", 3), ("robots.txt` and the page-level meta robots", 7),
    ("sitemap.xml` exists", 7), ("exactly one `<title>`", 8), ("title tag is roughly", 7), ("meta description is roughly", 6),
    ("hreflang", 6), ("canonical", 7), ("render-blocking", 7), ("lcp", 8), ("forced reflow", 5),
    ("5xx", 8), ("redirect chains", 6), ("malware", 9), ("javascript disabled", 6),
]

# ---- why it matters / what happens if not fixed: section defaults; core GEO items get specific texts ----
WHY = {
    "C01": ("AI and search crawlers can only cite what they are allowed to fetch.", "The site is invisible to AI answer engines and possibly to search: no citations, no traffic from them, whatever else is done."),
    "C02": ("Crawlers read the raw HTML response; most do not run JavaScript.", "Content injected by JS is never seen, so the page cannot be quoted or ranked for what it says."),
    "C03": ("Sourced claims were measured to lift AI-answer visibility by about 25%.", "Unsourced claims look like opinion, so engines prefer competitors who cite their sources."),
    "C04": ("A named, attributed expert quote was the strongest single factor tested (about 28% lift).", "The page has no checkable human authority, so it is cited less often than pages that do."),
    "C05": ("Concrete, sourced numbers are quoted far more often than vague claims (about 26% lift).", "Vague claims like 'many clients see growth' give an AI nothing to lift into an answer."),
    "C06": ("Natural, well-edited prose is easier for models to quote and for people to trust.", "Robotic or stuffed copy is skipped by AI engines and loses reader trust."),
    "C07": ("Engines lift the opening answer of a section verbatim.", "The answer is buried, so a competitor's cleaner opening gets quoted instead."),
    "C08": ("AI engines answer natural-language prompts, not keywords.", "Headings that do not match real questions never get matched to the prompts people type."),
    "C09": ("Schema tells machines exactly what the page and the business are.", "Engines guess instead of knowing, which costs rich results, entity clarity and citations."),
    "C10": ("Engines and Google favour recently reviewed content; prices and stats decay fastest.", "Old numbers get flagged as stale and the page slowly drops behind fresher competitors."),
    "C11": ("Identical names across site, profiles and schema let engines merge them into one entity.", "Name drift splits the brand into several weak entities and wrong facts get cited."),
    "C12": ("Short single-idea paragraphs can be lifted out whole.", "Multi-idea blocks are hard to quote cleanly, so they are quoted less."),
    "C13": ("Clean headings, URLs and speed are the base every GEO tactic sits on.", "GEO work on top of broken SEO fundamentals does not pay off."),
    "C14": ("Real contact details, policies and people are the trust signals engines weigh.", "Anonymous-looking sites are cited less and rank lower on trust."),
    "C15": ("Each AI platform cites differently, one check is not representative.", "Fixes are guessed instead of aimed at the platform that is not citing the site."),
    "A": ("Basic page hygiene decides how cleanly Google reads each page.", "Missing or duplicate titles/H1s and broken links confuse crawlers and waste crawl budget."),
    "B": ("Title, meta description and keyword placement are what Google and searchers read first.", "Truncated or vague snippets get fewer clicks and the page matches fewer queries."),
    "C": ("Internal links pass authority and show Google how pages relate.", "Weakly linked pages look unimportant and rank lower or stay unindexed."),
    "D": ("Competitors in the SERP set the realistic bar for depth and shape.", "Pages are built too thin or in the wrong format for what Google is rewarding."),
    "E": ("Helpful, expert, first-hand content is what quality systems reward.", "Thin or anonymous content is demoted by quality updates and not trusted by AI engines."),
    "F": ("Light, descriptive, properly sized images load fast and carry search signals.", "Heavy images slow the page and mobile users leave; missing alt text loses image search."),
    "G": ("Usability problems drive visitors away and send negative engagement signals.", "Visitors bounce before converting and accessibility rules are broken."),
    "H": ("Local signals decide map-pack and 'near me' visibility.", "Competitors with a complete local footprint take the local results."),
    "I": ("SEO is a loop of measure, update and re-measure.", "One-off optimisation decays and rankings drift down unnoticed."),
    "J": ("Indexing health decides whether pages can rank at all.", "Pages stay out of Google or errors go unnoticed for months."),
    "K": ("Benchmarks show whether the work moves the numbers.", "There is no way to prove progress or spot the cheapest opportunities."),
    "L": ("URL and site structure decide how authority flows and what each page is for.", "Authority is diluted, pages compete with each other and important pages are buried."),
    "M": ("Speed, security and clean infrastructure are direct ranking and trust factors.", "Slow or insecure pages rank lower and lose visitors before they read anything."),
    "N": ("Correct, consistent schema lifts rich results and entity understanding.", "Wrong or misplaced schema is ignored or flagged and can trigger rich-result penalties."),
    "O": ("Legal and trust pages are baseline trust and compliance signals.", "Missing policies hurt trust and can breach GDPR-type rules."),
    "P": ("Thin, duplicate or cannibalising content wastes crawl budget and splits rankings.", "Pages compete with each other or are judged low-value and demoted."),
    "MOB": ("Google indexes the mobile version first and most visitors are on phones.", "A page that works on desktop but fails on mobile loses rankings and visitors."),
    "MAP": ("A correct sitemap is how Google discovers and prioritises pages.", "Missing, broken or contradicting sitemaps leave pages undiscovered or send mixed signals."),
}

# Checks that cannot be verified from outside: pre-filled FAIL with `needs` (agency rule: binary, with the gap named).
NEEDS = {
    "C15-1": "ChatGPT / Gemini / Perplexity / AI Overviews citation tests", "C15-2": "citation tracking per AI platform",
    "D-01": "competitor SERP data (top 3-10 results)", "D-02": "competitor SERP data", "D-03": "competitor SERP data",
    "D-04": "NLP / TF-IDF tool and competitor pages", "D-05": "competitor SERP data", "D-06": "live SERP for the target query",
    "D-07": "Domain Authority tool (Ahrefs/Moz/SEMrush)", "D-08": "SEO backlink tool (Ahrefs/SEMrush)",
    "C-04": "competitor SERP data (internal link counts)",
    "E-01": "Grammarly (or equivalent grammar scorer)", "E-04": "analytics / engagement data", "E-14": "documented competitor content-gap analysis",
    "E-15": "W3C HTML validator + accessibility scanner",
    "H-04": "Google Business Profile access", "H-03": "YouTube / video ranking data",
    "I-01": "Google Search Console + SEMrush", "I-02": "Google Search Console", "I-03": "Search Console / content calendar", "I-04": "GSC / SEMrush research",
    "J-01": "Search Console and Bing Webmaster access", "J-02": "Search Console access", "J-05": "Search Console URL Inspection",
    "J-06": "Search Console URL Inspection", "J-07": "Search Console", "J-08": "Search Console (manual actions)",
    "J-11": "Google cache / URL Inspection", "J-13": "live Google search (site: and sitelinks)", "J-14": "live Google search and Autosuggest",
    "J-15": "Google Analytics / Search Console engagement data",
    "K-01": "Google index data (GSC)", "K-02": "backlink tool (Ahrefs/SEMrush)", "K-03": "rank tracker / SEMrush", "K-04": "WHOIS / domain-history tool",
    "K-05": "competitor tools (SEMrush/Ahrefs)",
    "M-18": "hosting / reverse-IP lookup", "M-19": "Wayback Machine / domain-history review",
    "MOB-05": "Search Console mobile usability report", "MOB-12": "a real device",
}

TYPE_BLOCK = ("Article", "BlogPosting", "NewsArticle")


# ----------------------------------------------------------------------------------------------------------
# Checklist loading (single source of truth = the framework markdown)
# ----------------------------------------------------------------------------------------------------------
def load():
    """Parse the framework file -> OrderedDict ID -> {id, sec, group, text, impact}. Stops if counts drifted."""
    if not os.path.exists(FRAMEWORK):
        sys.exit(f"Checklist not found: {FRAMEWORK}")
    items = OrderedDict(); sec = None; n = {}
    in_core = False
    for line in open(FRAMEWORK, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("## "):
            in_core = line.startswith("## Audit Checklist")
            sec = "MOB" if line.startswith("## Mobile Audit") else "MAP" if line.startswith("## Sitemap Health") else None
            continue
        m = re.match(r"### (\d+)\. ", line)
        if m and in_core:
            sec = f"C{int(m.group(1)):02d}"; continue
        m = re.match(r"### ([A-P])\. ", line)
        if m and not in_core:
            sec = m.group(1); continue
        if sec and line.startswith("- [ ] "):
            n[sec] = n.get(sec, 0) + 1
            iid = f"{sec}-{n[sec]}" if sec.startswith("C") and len(sec) == 3 else f"{sec}-{n[sec]:02d}"
            text = re.sub(r"\s+", " ", line[6:]).strip()
            items[iid] = dict(id=iid, sec=sec, group=SECTIONS[sec], text=text, impact=impact_of(sec, text))
    bad = [f"{k}: file has {n.get(k, 0)}, expected {v}" for k, v in EXPECTED_COUNTS.items() if n.get(k, 0) != v]
    if bad:
        sys.exit("Framework file drifted from seo_audit.py EXPECTED_COUNTS - refusing to audit a changed list:\n  " + "\n  ".join(bad))
    return items


def impact_of(sec, text):
    t = text.lower()
    for key, val in IMPACT_RULES:
        if key in t: return val
    return IMPACT_SECTION[sec]


def stars(n):
    return "★" * n + "☆" * (10 - n)


def pick_sections(arg):
    if not arg or arg.upper() == "ALL": return list(SECTIONS)
    out = []
    for s in arg.split(","):
        s = s.strip()
        s = s.upper() if s.upper() in SECTIONS else s
        if s in SECTIONS: out.append(s)
        elif re.fullmatch(r"\d+", s) and f"C{int(s):02d}" in SECTIONS: out.append(f"C{int(s):02d}")
        else: sys.exit(f"Unknown section '{s}'. Valid: {', '.join(SECTIONS)} (or a GEO item number 1-15)")
    return out


def cmd_list(a):
    items = load(); secs = pick_sections(a.sections)
    total = 0
    for s in secs:
        rows = [i for i in items.values() if i["sec"] == s]; total += len(rows)
        print(f"\n== {s}  {SECTIONS[s]}  ({len(rows)}) ==")
        for i in rows: print(f"  {i['id']:7} {i['impact']:2}/10  {i['text']}")
    print(f"\nTOTAL {total} checks in {len(secs)} sections")


# ----------------------------------------------------------------------------------------------------------
# Capture: fetch the site and collect mechanical signals
# ----------------------------------------------------------------------------------------------------------
AI_BOTS = ["GPTBot", "ChatGPT-User", "PerplexityBot", "Google-Extended", "Applebot-Extended", "ClaudeBot", "anthropic-ai"]
UA_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def _get(url, ua=UA_BROWSER, timeout=20, allow_redirects=True, method="GET"):
    import requests
    t = time.time()
    try:
        r = requests.request(method, url, headers={"User-Agent": ua, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"},
                             timeout=timeout, allow_redirects=allow_redirects)
        return r, round(time.time() - t, 3)
    except Exception as e:
        return None, str(e)[:120]


def parse_page(url, html, headers):
    """Pull the on-page signals from raw HTML."""
    import lxml.html
    try: doc = lxml.html.fromstring(html)
    except Exception: return dict(url=url, error="html parse failed")
    host = urllib.parse.urlparse(url).netloc
    txt = lambda e: re.sub(r"\s+", " ", e.text_content()).strip()
    q = lambda xp: doc.xpath(xp)
    title = [txt(t) for t in q("//title")]
    metas = {m.get("name", m.get("property", "")).lower(): m.get("content", "") for m in q("//meta[@name or @property]")}
    heads = [(int(h.tag[1]), txt(h)) for h in q("//h1|//h2|//h3|//h4|//h5|//h6")]
    # JSON-LD must be read BEFORE scripts are dropped (fix 2026-11-11: schema used to read as absent)
    ld = []
    for s in q("//script[@type='application/ld+json']"):
        raw = s.text_content() if s.text_content() else ""  # ld+json scripts are kept in the tree on purpose (fix 2026-11-11: were dropped, so schema read as absent)
        try: ld.append(dict(ok=True, data=json.loads(raw)))
        except Exception: ld.append(dict(ok=False, raw=raw[:80]))
    for bad in q("//script|//style|//noscript"): bad.drop_tree()
    body = doc.find("body"); bodytext = txt(body) if body is not None else ""
    paras = [txt(p) for p in q("//p")]; paras = [p for p in paras if len(p.split()) >= 3]
    links = []
    for a in q("//a[@href]"):
        href = urllib.parse.urljoin(url, a.get("href", "")); u = urllib.parse.urlparse(href)
        if u.scheme not in ("http", "https"): continue
        inchrome = bool(a.xpath("ancestor::nav|ancestor::header|ancestor::footer"))
        links.append(dict(href=href.split("#")[0], text=txt(a)[:60], internal=u.netloc.replace("www.", "") == host.replace("www.", ""),
                          chrome=inchrome, rel=(a.get("rel") or "")))
    imgs = []
    for i in q("//img"):
        imgs.append(dict(src=urllib.parse.urljoin(url, i.get("src") or i.get("data-src") or ""), alt=i.get("alt"), w=i.get("width"), h=i.get("height"),
                         lazy=(i.get("loading") == "lazy"), fp=i.get("fetchpriority")))
    def types(d):
        out = []
        if isinstance(d, dict):
            t = d.get("@type"); out += (t if isinstance(t, list) else [t]) if t else []
            for v in d.values(): out += types(v)
        elif isinstance(d, list):
            for v in d: out += types(v)
        return out
    schema_types = sorted({t for x in ld if x["ok"] for t in types(x["data"]) if isinstance(t, str)})
    return dict(
        url=url, title=title, desc=metas.get("description", ""), titles_n=len(title), h1=[t for l, t in heads if l == 1], heads=heads,
        canonical=(q("//link[@rel='canonical']/@href") or [""])[0], robots=metas.get("robots", ""), lang=doc.get("lang", ""),
        hreflang=[(l.get("hreflang"), l.get("href")) for l in q("//link[@rel='alternate'][@hreflang]")],
        og={k: v for k, v in metas.items() if k.startswith("og:")}, viewport=metas.get("viewport", ""), keywords_meta=bool(metas.get("keywords")),
        words=len(bodytext.split()), paras=len(paras), para_words=[len(p.split()) for p in paras][:200], first_para=(paras[0] if paras else ""),
        first_para_words=(len(paras[0].split()) if paras else 0),
        links=links, imgs=imgs, ld_ok=[x["ok"] for x in ld], schema_types=schema_types, ld_raw=[x["data"] for x in ld if x["ok"]][:6],
        has_faq_markup=bool(q("//details|//*[contains(translate(@class,'FAQ','faq'),'faq')]|//*[contains(translate(@id,'FAQ','faq'),'faq')]")),
        blockquotes=len(q("//blockquote")), videos=len(q("//video|//iframe[contains(@src,'youtube') or contains(@src,'vimeo')]")),
        autoplay=bool(q("//video[@autoplay]|//iframe[contains(@src,'autoplay=1')]")),
        ga=len(re.findall(r"googletagmanager\.com/gtag/js|google-analytics\.com/analytics\.js|gtag\('config'", html)),
        gtm=len(re.findall(r"googletagmanager\.com/gtm\.js", html)), amp=bool(q("//link[@rel='amphtml']")),
        fonts_blocking=len(q("//link[@rel='stylesheet'][contains(@href,'fonts.googleapis.com')][not(@media='print')]")),
        css_files=[urllib.parse.urljoin(url, c) for c in q("//link[@rel='stylesheet']/@href")][:6],
        favicon=bool(q("//link[contains(@rel,'icon')]")), social=sorted({l["href"] for l in links if re.search(r"(facebook|instagram|linkedin|tiktok|youtube|twitter|x)\.com", l["href"])})[:8],
        numbers=len(re.findall(r"\b\d[\d.,%]*\s?(?:%|\+|x|k|m)\b|\b\d{2,}\b", bodytext)), sourced=len(re.findall(r"\b(source|according to|study|report|survey)\b", bodytext, re.I)),
        updated=bool(re.search(r"(updated|last modified|оновлено|zaktualizowano)\W{0,3}[:\-]?\s*\w+", bodytext, re.I)),
        date_modified=bool(re.search(r"dateModified", html)), question_heads=sum(1 for l, t in heads if "?" in t or re.match(r"(how|what|why|when|where|which|who|can|do|does|is|are|як|що|чому|jak|co|czy|dlaczego)\b", t, re.I)),
    )


def fetch_sitemap_urls(sm_url, limit=400, depth=0):
    r, _ = _get(sm_url)
    if r is None or r.status_code != 200: return [], dict(url=sm_url, status=(r.status_code if r is not None else "error"))
    try:
        import lxml.etree as ET
        root = ET.fromstring(r.content)
    except Exception as e:
        return [], dict(url=sm_url, status=200, xml_error=str(e)[:100])
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text.strip() for e in root.xpath("//s:url/s:loc", namespaces=ns)]
    subs = [e.text.strip() for e in root.xpath("//s:sitemap/s:loc", namespaces=ns)]
    meta = dict(url=sm_url, status=200, index=bool(subs), valid_xml=True, bytes=len(r.content))
    if subs and depth < 2:
        for s in subs[:20]:
            u, m = fetch_sitemap_urls(s, limit, depth + 1); locs += u; meta.setdefault("subs", []).append(m)
    return locs[:limit * 5], meta


def robots_blocked(rules, ua, path):
    """Tiny robots.txt evaluator: longest matching Allow/Disallow for the UA group (or *)."""
    best = None
    for group_uas, rs in rules:
        if any(g.lower() == ua.lower() for g in group_uas): best = rs; break
    if best is None:
        for group_uas, rs in rules:
            if "*" in group_uas: best = rs; break
    if not best: return False
    verdict, ln = False, -1
    for kind, pat in best:
        p = re.escape(pat).replace(r"\*", ".*").replace(r"\$", "$")
        if pat and re.match(p, path) and len(pat) > ln:
            verdict, ln = (kind == "disallow"), len(pat)
    return verdict


def parse_robots(text):
    rules, cur_uas, cur_rs, sitemaps = [], [], [], []
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if ":" not in line: continue
        k, v = [x.strip() for x in line.split(":", 1)]
        k = k.lower()
        if k == "user-agent":
            if cur_rs: rules.append((cur_uas, cur_rs)); cur_uas, cur_rs = [], []
            cur_uas.append(v)
        elif k in ("allow", "disallow"): cur_rs.append((k, v))
        elif k == "sitemap": sitemaps.append(v)
    if cur_uas: rules.append((cur_uas, cur_rs))
    return rules, sitemaps


def outdir_for(url, slug):
    if slug: base = os.path.join(ROOT, "clients", slug, "reports")
    else: base = os.path.join(ROOT, "seo-audits", urllib.parse.urlparse(url).netloc.replace("www.", ""))
    d = os.path.join(base, f"seo_audit_{date.today().isoformat()}"); os.makedirs(d, exist_ok=True); return d


def cmd_capture(a):
    url = a.url if a.url.startswith("http") else "https://" + a.url
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    out = outdir_for(url, a.slug); cap = dict(url=url, origin=origin, date=date.today().isoformat())
    print("Homepage + response headers...")
    r, ttfb = _get(url)
    if r is None: sys.exit(f"Cannot fetch {url}: {ttfb}")
    cap["home"] = dict(status=r.status_code, final=r.url, redirects=[(h.status_code, h.headers.get("location")) for h in r.history], ttfb=ttfb,
                       bytes=len(r.content), headers={k.lower(): v for k, v in r.headers.items() if k.lower() in
                       ("strict-transport-security", "last-modified", "server", "x-robots-tag", "content-encoding", "cache-control", "cf-ray", "via", "content-security-policy")})
    print("robots.txt, sitemap, AI crawler fetches, HTTP->HTTPS...")
    rr, _ = _get(origin + "/robots.txt"); robots_txt = rr.text if (rr is not None and rr.status_code == 200) else ""
    rules, sm_lines = parse_robots(robots_txt)
    cap["robots"] = dict(status=(rr.status_code if rr is not None else None), text=robots_txt[:6000], sitemaps=sm_lines,
                         ai_blocked={b: robots_blocked(rules, b, "/") for b in AI_BOTS}, star_blocks_all=robots_blocked(rules, "*", "/"))
    cap["ai_fetch"] = {}
    for b in AI_BOTS[:5]:   # diagnostic only: shows whether the edge serves 200 to these user-agent strings (never used to bypass a block)
        rb, _ = _get(url, ua=f"Mozilla/5.0 (compatible; {b}/1.0)", timeout=15)
        cap["ai_fetch"][b] = rb.status_code if rb is not None else "error"
    http = "http://" + urllib.parse.urlparse(url).netloc
    rh, _ = _get(http, allow_redirects=False)
    cap["http_redirect"] = dict(status=(rh.status_code if rh is not None else None), location=(rh.headers.get("location") if rh is not None else None))
    mobile_r, _ = _get(url, ua=UA_MOBILE)
    cap["mobile_raw"] = parse_page(url, mobile_r.text, {}) if mobile_r is not None and mobile_r.status_code == 200 else None
    print("Sitemap...")
    sm_urls, sm_meta = [], []
    for s in (sm_lines or [origin + "/sitemap.xml"])[:3]:
        u, m = fetch_sitemap_urls(s); sm_urls += u; sm_meta.append(m)
    cap["sitemap"] = dict(meta=sm_meta, url_count=len(sm_urls), urls=sm_urls[:1500], declared_in_robots=bool(sm_lines))
    pages = []
    for p in [url] + list(a.page):   # fix 2026-11-13: a --page equal to the target URL was sampled twice (false duplicate-title/description fails)
        if p.rstrip("/") not in {q.rstrip("/") for q in pages}: pages.append(p)
    if len(pages) < a.pages:
        host = urllib.parse.urlparse(url).netloc
        seen = {u.rstrip("/") for u in pages}   # '/' and bare host are the same page (fix 2026-11-11: homepage was sampled twice)
        def key(u): return (urllib.parse.urlparse(u).path.count("/"), u)
        for u in sorted(sm_urls, key=key):
            if u.rstrip("/") not in seen and urllib.parse.urlparse(u).netloc == host and len(pages) < a.pages: pages.append(u); seen.add(u.rstrip("/"))
    if len(pages) < a.pages:   # thin or missing sitemap: fall back to the internal links of the first page (nav first, then content)
        host = urllib.parse.urlparse(url).netloc.replace("www.", ""); first = parse_page(url, r.text, {}); seen = {u.rstrip("/") for u in pages}
        links = list(first.get("links", []))
        if urllib.parse.urlparse(url).path.strip("/"):   # fix 2026-11-13: an inner (or JS-shell) target has few links - also use the homepage's
            hr, ht = _get(origin + "/")
            if hr is not None and hr.status_code == 200: links += parse_page(origin + "/", ht, {}).get("links", [])
        for l in sorted(links, key=lambda l: not l["chrome"]):
            if l["href"].rstrip("/") in seen: continue
            h = l["href"]
            if l["internal"] and h not in seen and not re.search(r"\.(pdf|jpg|jpeg|png|webp|svg|zip|xml)(\?|$)", h, re.I) and len(pages) < a.pages: pages.append(h); seen.add(h.rstrip("/"))
    print(f"Pages ({len(pages)}): fetching + parsing...")
    cap["pages"] = []
    for u in pages:
        pr, t = _get(u)
        if pr is None or pr.status_code != 200: cap["pages"].append(dict(url=u, status=(pr.status_code if pr is not None else "error"))); continue
        p = parse_page(pr.url, pr.text, pr.headers); p.update(status=200, ttfb=t, bytes=len(pr.content), last_modified=pr.headers.get("last-modified"),
                                                          disallowed=robots_blocked(rules, "*", urllib.parse.urlparse(u).path or "/"))
        cap["pages"].append(p)
    print("Rendered (Playwright) comparison + mobile checks on the homepage...")
    cap["rendered"] = render_checks(url)
    rh_ = cap["rendered"].pop("rendered_html", None)
    if rh_ and cap["pages"] and cap["pages"][0].get("status") == 200 and cap["rendered"].get("rendered_words", 0) > 3 * max(cap["pages"][0].get("words", 0), 1):
        old = cap["pages"][0]; new = parse_page(url, rh_, {})   # raw HTML is a JS shell: crawlers that do not render see nothing, so keep both views
        new.update(status=200, ttfb=old.get("ttfb"), bytes=old.get("bytes"), last_modified=old.get("last_modified"), disallowed=old.get("disallowed"),
                   from_rendered=True, raw_words=old.get("words"), raw_title=old.get("title"), raw_h1=old.get("h1"), raw_robots=old.get("robots"))
        cap["pages"][0] = new
    print("Link, image and sitemap-entry status checks...")
    home = next((p for p in cap["pages"] if p.get("url") == url), cap["pages"][0])
    ilinks = list({l["href"] for p in cap["pages"] if p.get("links") for l in p["links"] if l["internal"]})[:80]
    def head(u):
        rr_, _ = _get(u, method="HEAD", timeout=12, allow_redirects=False)
        if rr_ is None or rr_.status_code in (405, 403): rr_, _ = _get(u, timeout=12, allow_redirects=False)
        return u, (rr_.status_code if rr_ is not None else "error"), (rr_.headers.get("location") if rr_ is not None else None)
    with ThreadPoolExecutor(8) as ex: cap["link_status"] = list(ex.map(head, ilinks))
    imgs = list({i["src"] for p in cap["pages"] if p.get("imgs") for i in p["imgs"] if i["src"].startswith("http")})[:60]
    def img_info(u):
        rr_, _ = _get(u, method="HEAD", timeout=12)
        return u, (rr_.status_code if rr_ is not None else "error"), int(rr_.headers.get("content-length", 0)) if rr_ is not None else 0
    with ThreadPoolExecutor(8) as ex: cap["img_status"] = list(ex.map(img_info, imgs))
    def sm_check(u):
        rr_, _ = _get(u, allow_redirects=False, timeout=12)
        if rr_ is None: return dict(url=u, status="error")
        d = dict(url=u, status=rr_.status_code, location=rr_.headers.get("location"))
        if rr_.status_code == 200:
            m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', rr_.text[:80000], re.I) or re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']canonical', rr_.text[:80000], re.I)
            d["canonical"] = m.group(1) if m else None
        return d
    with ThreadPoolExecutor(8) as ex: cap["sitemap_entries"] = list(ex.map(sm_check, sm_urls[:40]))
    cap["sitemap_disallowed"] = [u for u in sm_urls[:1500] if robots_blocked(rules, "*", urllib.parse.urlparse(u).path or "/")][:30]
    cap["psi"] = psi(url)
    json.dump(cap, open(os.path.join(out, "capture.json"), "w"), ensure_ascii=False, indent=1)
    print(f"Capture saved: {os.path.join(out, 'capture.json')}  ({len(cap['pages'])} pages, {len(sm_urls)} sitemap URLs)")


def render_checks(url):
    out = {}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); pg.goto(url, timeout=45000); pg.wait_for_timeout(1500)
            out["rendered_words"] = len(pg.evaluate("document.body.innerText").split())
            out["rendered_html"] = pg.content()
            ctx.close()
            ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, user_agent=UA_MOBILE)
            pg = ctx.new_page(); pg.goto(url, timeout=45000); pg.wait_for_timeout(1500)
            out["mobile"] = pg.evaluate("""() => { const vw = innerWidth; const small = [...document.querySelectorAll('a[href],button,input,select,textarea,summary')].filter(e => {
                  if (e.closest('footer')) return false; const r = e.getBoundingClientRect(); return r.width && r.height && (r.width < 44 || r.height < 44); }).length;
                return { scrollW: document.documentElement.scrollWidth, vw, small_taps: small, burger: !!document.querySelector('[class*=burger],[class*=menu-toggle],[aria-label*=menu i]'),
                  fixed_overlays: [...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return s.position==='fixed' && r.width>vw*.8 && r.height>innerHeight*.5; }).length,
                  bodyFont: getComputedStyle(document.body).fontSize,
                  lcp_img: (() => { const i=[...document.images].sort((a,b)=>b.width*b.height-a.width*a.height)[0]; return i ? { src: i.currentSrc || i.src, lazy: i.loading==='lazy', fp: i.fetchPriority, w: i.naturalWidth, shown: Math.round(i.getBoundingClientRect().width), y: Math.round(i.getBoundingClientRect().top) } : null; })() }; }""")
            ctx.close()
            ctx = b.new_context(java_script_enabled=False); pg = ctx.new_page(); pg.goto(url, timeout=45000)
            out["nojs_words"] = len(pg.evaluate("document.body.innerText").split()); ctx.close(); b.close()
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def psi(url):
    """PageSpeed Insights (public endpoint, may be rate limited). Returns {} if unavailable."""
    out = {}
    for strat in ("mobile",):
        r, _ = _get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + urllib.parse.urlencode({"url": url, "strategy": strat, "category": "performance"}), timeout=90)
        if r is None or r.status_code != 200: out[strat] = None; continue
        j = r.json(); lh = j.get("lighthouseResult", {}); au = lh.get("audits", {})
        out[strat] = dict(score=round((lh.get("categories", {}).get("performance", {}).get("score") or 0) * 100),
                          lcp=au.get("largest-contentful-paint", {}).get("displayValue"), cls=au.get("cumulative-layout-shift", {}).get("displayValue"),
                          tbt=au.get("total-blocking-time", {}).get("displayValue"),
                          render_blocking=au.get("render-blocking-resources", {}).get("score"), forced_reflow=au.get("forced-reflow-insight", {}).get("score"))
    return out


# ----------------------------------------------------------------------------------------------------------
# Auto-judging: mechanical checks measured from capture.json. Everything not here is TODO (Claude judges) or in NEEDS.
# Each returns (status, measured, evidence, fix).
# ----------------------------------------------------------------------------------------------------------
def pth(u):
    p = urllib.parse.urlparse(u); return (p.path or "/") + (("?" + p.query) if p.query else "")


def auto_results(cap):
    P = [p for p in cap["pages"] if p.get("status") == 200]; home = P[0] if P else {}
    R = {}; ok = lambda m, e: ("PASS", m, e, ""); no = lambda m, e, f: ("FAIL", m, e, f)
    rob = cap["robots"]; blocked = [b for b, v in rob["ai_blocked"].items() if v]
    # --- 1 crawlability
    R["C01-1"] = no("blocked: " + ", ".join(blocked), "robots.txt blocks AI user-agents", "Remove the Disallow rules for these bots in robots.txt.") if blocked or rob["star_blocks_all"] else ok("", f"robots.txt ({rob['status']}) allows {', '.join(AI_BOTS)}")
    bad = {b: s for b, s in cap["ai_fetch"].items() if s != 200}
    R["C01-2"] = no("; ".join(f"{b}: {s}" for b, s in bad.items()), "Edge/CDN does not return 200 to AI bot user-agents", "In Cloudflare > Security > Bots, allow AI crawlers (AI Bots / Bot Fight Mode).") if bad else ok("", "All AI bot user-agent fetches returned 200 (diagnostic UA test, nothing bypassed). Server header: " + str(cap["home"]["headers"].get("server")))
    R["C01-3"] = R["C01-2"]
    # --- 2 SSR
    rw, nj = cap["rendered"].get("rendered_words"), cap["rendered"].get("nojs_words")
    raw = home.get("words", 0)
    if rw:
        ratio = raw / rw if rw else 1
        st = ratio >= 0.8
        e = f"homepage raw HTML text {raw} words vs rendered {rw} words ({round(ratio*100)}%); JS-disabled render {nj} words"
        for k in ("C02-1", "C02-2", "C02-3"): R[k] = ok(f"{raw}/{rw} words", e) if st else no(f"{raw}/{rw} words", e, "Enable SSR / static export so the answer text is in the raw HTML.")
    # --- 9 schema
    types = {p["url"]: p.get("schema_types", []) for p in P}
    faq_pages = [p for p in P if p.get("has_faq_markup")]
    if faq_pages:
        miss = [pth(p["url"]) for p in faq_pages if "FAQPage" not in p["schema_types"]]
        R["C09-1"] = no("no FAQPage on: " + ", ".join(miss), "Pages with visible FAQ content lack FAQPage JSON-LD", "Generate FAQPage JSON-LD from the visible Q&A markup (see framework item 9).") if miss else ok("", "FAQPage present on every page with FAQ markup")
    else: R["C09-1"] = ("N/A", "", "No visible FAQ content on the sampled pages", "")
    art = [p for p in P if re.search(r"/(blog|news|articles?|posts?)/", p["url"])]
    R["C09-2"] = (no("no Article schema on: " + ", ".join(pth(p["url"]) for p in art if not set(p["schema_types"]) & set(TYPE_BLOCK)), "Blog pages without Article/BlogPosting schema", "Add BlogPosting JSON-LD with author, datePublished, dateModified.") if any(not set(p["schema_types"]) & set(TYPE_BLOCK) for p in art) else ok("", "Article schema on all sampled blog pages")) if art else ("N/A", "", "No blog/editorial pages in the sample (add with --page)", "")
    badld = [pth(p["url"]) for p in P if False in p.get("ld_ok", [])]
    anyld = any(p.get("ld_ok") for p in P)
    R["C09-3"] = (no("invalid JSON-LD on: " + ", ".join(badld), "JSON-LD that does not parse", "Fix the JSON syntax; re-test in Google Rich Results Test.") if badld else ok("", "All JSON-LD blocks parse. Google Rich Results Test itself not run.")) if anyld else no("0 pages with JSON-LD", "No structured data found on any sampled page", "Add Organization, WebSite, BreadcrumbList and page-type schema.")
    cov = {pth(p["url"]): len(p["schema_types"]) for p in P}
    zero = [k for k, v in cov.items() if v == 0]
    R["C09-4"] = no("zero schema: " + ", ".join(zero[:10]), f"Schema coverage differs across pages: {cov}", "Add schema to the pages with none (static pages and CMS pages separately).") if zero else ok("", f"Every sampled page has schema: {cov}")
    R["C09-7"] = ("FAIL" if any(p.get("disallowed") for p in P) else "PASS", ", ".join(pth(p["url"]) for p in P if p.get("disallowed")), "Sampled pages blocked by robots.txt are out of scope for schema work" if any(p.get("disallowed") for p in P) else "All sampled pages are crawlable", "Unblock or retire the blocked pages." if any(p.get("disallowed") for p in P) else "")
    # --- 12 paragraphs
    pw = [w for p in P for w in p.get("para_words", [])]
    if pw:
        avg = sum(pw) / len(pw); long_ = sum(1 for w in pw if w > 80)
        R["C12-1"] = ok(f"avg {avg:.0f} words, {long_} paragraphs over 80", "Paragraph length across sampled pages") if avg <= 60 and long_ <= max(2, len(pw) // 15) else no(f"avg {avg:.0f} words, {long_} paragraphs over 80", "Paragraphs are long / multi-idea", "Split into one-idea paragraphs of 2-4 sentences.")
    # --- 13 headings
    probs = []
    for p in P:
        lv = [l for l, _ in p["heads"]]; pr = []
        if len(p["h1"]) != 1: pr.append(f"{len(p['h1'])} H1")
        if any(b - a > 1 for a, b in zip(lv, lv[1:])): pr.append("skipped level")
        if pr: probs.append(f"{pth(p['url'])} - {', '.join(pr)}")
    R["C13-1"] = no("; ".join(probs), "Heading hierarchy problems", "Exactly one H1, then H2/H3 in order without skipping levels.") if probs else ok("", "Single H1 and ordered headings on every sampled page")
    # --- A
    bt = [f"{pth(p['url'])} - {p['titles_n']} title, {len(p['h1'])} H1" for p in P if p["titles_n"] != 1 or len(p["h1"]) != 1]
    R["A-01"] = no("; ".join(bt), "Pages without exactly one title and one H1", "One <title> and one <h1> per page.") if bt else ok("", "One title and one H1 on every sampled page")
    ls = cap.get("link_status", []); br = [f"{pth(u)} - {s}" for u, s, _ in ls if s in (404, 410) or (isinstance(s, int) and s >= 500) or s == "error"]
    R["A-02"] = no("; ".join(br[:20]), f"{len(br)} of {len(ls)} sampled internal links broken", "Fix or remove the broken links, or 301 them to the right page.") if br else ok(f"0 of {len(ls)} sampled links broken", "Internal link sample")
    tt = {}
    for p in P: tt.setdefault((p["title"] or [""])[0], []).append(pth(p["url"]))
    dup = {t: u for t, u in tt.items() if len(u) > 1 and t}
    R["A-03"] = no("; ".join(f"'{t[:40]}' on {', '.join(u)}" for t, u in dup.items()), "Duplicate titles across pages (external copy check not run: needs Copyscape)", "Give each page a unique title and body copy.") if dup else ok("", "No duplicate titles in the sample; web-wide duplicate check (Copyscape) not run")
    # --- B
    tl = [f"{pth(p['url'])} - {len((p['title'] or [''])[0])} chars" for p in P if not 30 <= len((p["title"] or [""])[0]) <= 65]
    R["B-03"] = no("; ".join(tl), "Titles outside 30-65 characters", "Rewrite to 30-65 characters, main keyword first.") if tl else ok("", "All sampled titles are 30-65 characters")
    dl = [f"{pth(p['url'])} - {len(p['desc'])} chars" for p in P if not 70 <= len(p["desc"]) <= 160]
    R["B-04"] = no("; ".join(dl), "Meta descriptions missing or outside 70-160 characters", "Write 70-155 character descriptions with a call to action.") if dl else ok("", "All sampled meta descriptions are 70-160 characters")
    dd = {}
    for p in P: dd.setdefault(p["desc"], []).append(pth(p["url"]))
    dupd = {d: u for d, u in dd.items() if d and len(u) > 1}
    R["B-05"] = no("; ".join(f"{', '.join(u)}" for u in dupd.values()), "Duplicate meta descriptions or titles", "Unique title and description per page, or canonical where legitimate.") if (dupd or dup) else ok("", "No duplicated titles or descriptions in the sample")
    multi = len({l for p in P for l, _ in p.get("hreflang", [])}) > 0
    if multi:
        bad = [pth(p["url"]) for p in P if not p.get("hreflang") or "x-default" not in [l for l, _ in p["hreflang"]]]
        R["B-11"] = no("missing hreflang/x-default: " + ", ".join(bad), "Multilingual site with incomplete hreflang", "Add hreflang for every language version plus x-default.") if bad else ok("", "hreflang with x-default on all sampled pages")
    else: R["B-11"] = ("N/A", "", "No hreflang found; single-language site", "")
    R["B-12"] = ok("", "meta keywords tag present: " + str(any(p.get("keywords_meta") for p in P)) + " (no ranking value, informational)")
    # --- C
    ic = [f"{pth(p['url'])} - {len({l['href'] for l in p['links'] if l['internal'] and not l['chrome']})} unique" for p in P if len({l["href"] for l in p["links"] if l["internal"] and not l["chrome"]}) < 5]
    R["C-01"] = no("; ".join(ic), "Pages with fewer than 5 unique in-content internal links (nav/header/footer excluded)", "Add contextual internal links to related pages.") if ic else ok("", "5+ unique in-content internal links on every sampled page")
    # --- F
    im = cap.get("img_status", []); big = [f"{pth(u)} - {round(b/1024)}KB" for u, s, b in im if b > 100 * 1024]
    R["F-02"] = no("; ".join(big[:20]), f"{len(big)} of {len(im)} sampled images over 100KB", "Compress / resize to under ~100KB (WebP/AVIF).") if big else ok(f"0 of {len(im)} over 100KB", "Image weight sample")
    noalt = [f"{pth(p['url'])} - {sum(1 for i in p['imgs'] if i['alt'] is None)} without alt" for p in P if any(i["alt"] is None for i in p["imgs"])]
    R["F-04"] = no("; ".join(noalt), "Images without an alt attribute", "Add descriptive alt (alt=\"\" only for decoration).") if noalt else ok("", "Every sampled image has an alt attribute")
    gen = [pth(i["src"]) for p in P for i in p["imgs"] if re.search(r"/(img|image|dsc|screenshot|photo)[-_ ]?\d{2,}", i["src"], re.I)][:10]
    deadi = [f"{pth(u)} - {s}" for u, s, _ in im if s in (404, 410, "error")]
    R["F-07"] = no("; ".join(gen + deadi), "Non-descriptive image filenames and/or dead images", "Rename files descriptively; fix dead image links.") if (gen or deadi) else ok("", "No generic filenames or dead images in the sample")
    # --- G
    R["G-06"] = ("FAIL", "autoplay media on: " + ", ".join(pth(p["url"]) for p in P if p["autoplay"]), "Auto-playing video/iframe", "Remove autoplay or mute+controls.") if any(p["autoplay"] for p in P) else ok("", "No autoplaying media found")
    # --- J
    smm = cap["sitemap"]["meta"]; cnt = cap["sitemap"]["url_count"]
    R["J-03"] = ok(f"{cnt} URLs", f"sitemap(s) fetched OK: {[m.get('url') for m in smm]}; compare with Search Console's indexed count (not available)") if cnt and all(m.get("status") == 200 for m in smm) else no("", "sitemap missing or not 200", "Create sitemap.xml and list it in robots.txt.")
    gas = [f"{pth(p['url'])} - {p['ga']} GA tags" for p in P if p["ga"] > 1]
    R["J-09"] = no("; ".join(gas), "Google Analytics tag appears more than once", "Keep exactly one GA4 tag per page.") if gas else ok("", f"GA tag count per page: {[p['ga'] for p in P]}; GTM containers: {[p['gtm'] for p in P]}")
    soc = home.get("social", [])
    R["J-10"] = ok("", "Social profiles linked: " + ", ".join(soc)) if soc else no("", "No social profile links found on the homepage", "Link the real brand profiles and add them to Organization sameAs.")
    R["J-12"] = ("N/A", "", "No news-style publishing detected in the sample", "")
    # --- L
    deep = [f"{pth(p['url'])} - depth {pth(p['url']).strip('/').count('/') + 1}" for p in P if pth(p["url"]).strip("/").count("/") >= 4]
    R["L-09"] = no("; ".join(deep), "Pages deeper than 4 path levels (proxy for click depth)", "Link important pages within 3-4 clicks of the homepage.") if deep else ok("", "No sampled page is deeper than 4 path levels")
    bc = [pth(p["url"]) for p in P if pth(p["url"]) != "/" and "BreadcrumbList" not in p["schema_types"]]
    R["L-11"] = no("no BreadcrumbList on: " + ", ".join(bc[:10]), "Inner pages without breadcrumb schema", "Add breadcrumbs + BreadcrumbList JSON-LD.") if bc else ok("", "BreadcrumbList on every inner sampled page")
    # --- M
    h = cap["home"]; hdr = h["headers"]
    R["M-01"] = ok("", f"HTTPS final URL {h['final']}; http->{cap['http_redirect']['status']} {cap['http_redirect']['location']}; HSTS: {hdr.get('strict-transport-security', 'absent')}") if h["final"].startswith("https") and cap["http_redirect"]["status"] in (301, 308) and "strict-transport-security" in hdr else no(f"http redirect {cap['http_redirect']['status']}, HSTS {'present' if 'strict-transport-security' in hdr else 'missing'}", "HTTPS / redirect / HSTS not fully in place", "301 all http to https and send a Strict-Transport-Security header.")
    chains = [(u, l) for u, s, l in ls if s in (301, 302, 307, 308)]
    R["M-02"] = no("; ".join(f"{pth(u)} -> {l}" for u, l in chains[:10]), f"{len(chains)} internal links go through a redirect; homepage redirect hops: {len(h['redirects'])}", "Point internal links at the final URLs.") if chains or len(h["redirects"]) > 1 else ok("", "No redirect chains in the link sample")
    tt_ = [f"{pth(p['url'])} - {p['ttfb']}s" for p in P if p["ttfb"] > 0.5]; heavy = [f"{pth(p['url'])} - {round(p['bytes']/1048576, 2)}MB" for p in P if p["bytes"] > 3 * 1048576]
    R["M-04"] = no("; ".join(tt_ + heavy), "Server response over 0.5s or page over 3MB (HTML only; includes network from the machine running the audit)", "Enable caching/CDN, compress the HTML, trim page weight.") if (tt_ or heavy) else ok("", "Response times: " + ", ".join(f"{pth(p['url'])} {p['ttfb']}s" for p in P))
    ps = (cap.get("psi") or {}).get("mobile")
    if ps:
        R["M-03"] = ok(f"PSI mobile {ps['score']}", f"LCP {ps['lcp']}, CLS {ps['cls']}, TBT {ps['tbt']}") if ps["score"] >= 90 else no(f"PSI mobile {ps['score']}", f"LCP {ps['lcp']}, CLS {ps['cls']}, TBT {ps['tbt']}", "Fix the Lighthouse opportunities (images, render-blocking, JS).")
    else: R["M-03"] = ("FAIL", "", "PageSpeed Insights API unavailable (rate limit/offline)", "Run PageSpeed Insights manually.")
    if R["M-03"][0] == "FAIL" and not ps: R["M-03"] = ("FAIL", "", R["M-03"][2], R["M-03"][3])
    fb = home.get("fonts_blocking", 0)
    R["M-05"] = no(f"{fb} blocking font stylesheet(s)", "Google Fonts <link rel=stylesheet> without the async preload pattern", "Use rel=preload as=style + media=print onload swap with a <noscript> fallback.") if fb else ok("", "No render-blocking Google Fonts stylesheet on the homepage" + (f"; PSI render-blocking score {ps['render_blocking']}" if ps else ""))
    li = cap["rendered"].get("mobile", {}).get("lcp_img")
    if li:
        bad = li["lazy"] or li["fp"] != "high"
        R["M-06"] = no(f"lazy={li['lazy']}, fetchpriority={li['fp']}", f"Largest image {pth(li['src'])} ({li['w']}px wide, shown at {li['shown']}px)", "Remove loading=lazy, add fetchpriority=high, keep it as a plain <img> in raw HTML.") if (bad and li["y"] < 900) else ok("", f"Largest image {pth(li['src'])}: lazy={li['lazy']}, fetchpriority={li['fp']}")
    if ps and ps.get("forced_reflow") is not None: R["M-07"] = ok("", f"PSI forced-reflow score {ps['forced_reflow']}") if ps["forced_reflow"] == 1 else no("", f"PSI forced-reflow score {ps['forced_reflow']}", "Defer geometry reads after DOM writes into requestAnimationFrame.")
    R["M-08"] = ok(f"{nj} words with JS off", "Homepage text renders with JavaScript disabled") if (nj or 0) >= 100 else no(f"{nj} words with JS off", "Little or no content without JavaScript", "Server-render the content.")
    R["M-09"] = ok("", f"favicon link: {home.get('favicon')}; server: {hdr.get('server')}; content-encoding: {hdr.get('content-encoding')}; CDN hints: {hdr.get('cf-ray') or hdr.get('via') or 'none seen'}") if home.get("favicon") else no("", "No favicon link on the homepage", "Add a favicon.")
    err = [f"{pth(p['url'])} - {p['status']}" for p in cap["pages"] if p.get("status") != 200]
    cn = [f"{pth(p['url'])} -> {p['canonical']}" for p in P if p["canonical"] and urllib.parse.urljoin(p["url"], p["canonical"]).rstrip("/") != p["url"].rstrip("/")]; nocan = [pth(p["url"]) for p in P if not p["canonical"]]
    R["M-12"] = no("; ".join(err + cn[:5] + ["no canonical: " + ", ".join(nocan)] if nocan else err + cn[:5]), "Error responses or canonical problems", "Fix 5xx; give every page a self-referencing canonical.") if (err or cn or nocan) else ok("", "No error pages in the sample; canonical self-referencing everywhere")
    og = [pth(p["url"]) for p in P if not all(k in p["og"] for k in ("og:title", "og:description", "og:image"))]
    R["M-15"] = no("missing og:title/description/image on: " + ", ".join(og[:10]), "Open Graph tags incomplete", "Add og:title, og:description, og:image (and og:url).") if og else ok("", "Open Graph tags complete on every sampled page")
    ext = [f"{pth(p['url'])} - {sum(1 for l in p['links'] if not l['internal'])} external" for p in P if sum(1 for l in p["links"] if not l["internal"]) >= 100]
    R["M-17"] = no("; ".join(ext), "Pages with 100+ outbound links", "Trim outbound links.") if ext else ok("", "Outbound links per page: " + ", ".join(str(sum(1 for l in p["links"] if not l["internal"])) for p in P))
    # --- O
    allhrefs = " ".join(l["href"].lower() + " " + l["text"].lower() for p in P for l in p["links"])
    priv = bool(re.search(r"privacy|polityka|конфіденц", allhrefs)); terms = bool(re.search(r"terms|regulamin|umow|умов", allhrefs))
    R["O-01"] = ok("", "Privacy and terms links found") if priv and terms else no(f"privacy: {priv}, terms: {terms}", "Policy links missing from sampled pages", "Publish and link Privacy Policy and Terms.")
    R["O-03"] = ok("", "Contact link found") if re.search(r"contact|kontakt|контакт", allhrefs) else no("", "No contact link found", "Add an easy-to-find Contact page.")
    # --- P
    thin = [f"{pth(p['url'])} - {p['words']} words" for p in P if p["words"] < 200]; thin2 = [f"{pth(p['url'])} - {p['words']} words, 0 images" for p in P if p["words"] < 600 and not p["imgs"]]
    R["P-01"] = no("; ".join(thin + thin2), "Thin pages (under 200 words, or under 600 words with no images)", "Expand with real substance and supporting visuals, or merge/redirect.") if (thin or thin2) else ok("", "Word counts: " + ", ".join(f"{pth(p['url'])} {p['words']}" for p in P))
    # --- MOB
    mo = cap["rendered"].get("mobile", {}); vp = home.get("viewport", "")
    R["MOB-01"] = ok(f"scrollWidth {mo.get('scrollW')} / viewport {mo.get('vw')}", f"viewport meta '{vp}', no horizontal scroll at 390px") if "width=device-width" in vp and mo.get("scrollW", 0) <= mo.get("vw", 390) + 1 else no(f"scrollWidth {mo.get('scrollW')} / viewport {mo.get('vw')}", f"viewport meta '{vp}'", "Add width=device-width and remove horizontal overflow.")
    R["MOB-02"] = no(f"{mo.get('fixed_overlays')} large fixed overlay(s) at load", "Possible intrusive interstitial on mobile", "Remove or shrink the overlay.") if mo.get("fixed_overlays") else ok("", "No large fixed overlay on first load at 390px (cookie banners may appear only on first visit)")
    R["MOB-04"] = ("PASS" if li and li["w"] <= li["shown"] * 3 else "FAIL", f"largest image {li['w']}px natural vs {li['shown']}px shown" if li else "", "Compare natural to displayed image width (2x is the target)", "Serve srcset/resized images for mobile.") if li else None
    R["MOB-04"] = R["MOB-04"] if R["MOB-04"] else None
    R["MOB-06"] = ("N/A", "", "No amphtml link found", "") if not any(p["amp"] for p in P) else ("FAIL", "amp link present", "AMP in use: verify it still serves and reconsider", "Confirm AMP validity or retire it.")
    R["MOB-07"] = ok(f"burger menu: {mo.get('burger')}", "Mobile nav present") if mo.get("burger") else no("", "No mobile menu toggle detected", "Add a thumb-reachable mobile menu.")
    R["MOB-08"] = ok(f"{mo.get('small_taps')} under 44px (footer excluded)", "Touch targets on the homepage at 390px") if mo.get("small_taps", 99) == 0 else no(f"{mo.get('small_taps')} under 44px (footer excluded)", "Small touch targets at 390px", "Enlarge to 44x44px with padding/min-height.")
    mm = cap.get("mobile_raw") or {}
    if mm:
        diff = [k for k in ("title", "canonical", "robots", "desc") if mm.get(k) != home.get(k)]
        R["MOB-11"] = no("differs: " + ", ".join(diff), "Mobile and desktop raw HTML differ in head tags", "Serve identical title/canonical/robots/meta on mobile and desktop.") if diff else ok("", "Title, description, canonical and robots identical for a desktop and an iPhone user-agent")
    R["MOB-09"] = ("N/A", "", "No video elements on the homepage", "") if not home.get("videos") else None
    R["MOB-10"] = ok("", "favicon link present in the head") if home.get("favicon") else no("", "No favicon link", "Add a favicon (48px multiples) so it shows in mobile SERPs.")
    # --- robots vs meta robots, language signals
    ni = [f"{pth(p['url'])} - meta robots '{p['robots']}'" for p in P if "noindex" in (p.get("robots") or "").lower()]
    R["L-13"] = no("; ".join(ni), "Pages carry a meta noindex (robots.txt allows crawling). Confirm this is intended (an ads-only landing page may be) - an accidental noindex removes the page from Google", "Remove the noindex if the page should rank; keep it only for ads-only pages.") if ni else ok("", "robots.txt and meta robots agree: no noindex on the sampled pages")
    shell = [p for p in P if p.get("from_rendered")]
    if shell:
        R["C02-1"] = R["C02-2"] = R["C02-3"] = no(f"raw {shell[0]['raw_words']} words vs rendered {cap['rendered'].get('rendered_words')}", f"{pth(shell[0]['url'])} is a JavaScript shell: raw HTML has {shell[0]['raw_words']} words, the rendered page {cap['rendered'].get('rendered_words')}; JS-off render {nj} words. Other checks below were measured on the RENDERED page for this URL", "Server-render or pre-render the page so the text is in the raw HTML (Wix: use a native page, not a JS-injected one).")
    langs_ = {p.get("lang") for p in P if p.get("lang")}
    # --- MAP
    sm = cap["sitemap"]; first = sm["meta"][0] if sm["meta"] else {}
    R["MAP-01"] = ok("", f"{first.get('url')} -> {first.get('status')}, valid XML, listed in robots.txt: {sm['declared_in_robots']}") if first.get("status") == 200 and first.get("valid_xml") and sm["declared_in_robots"] else no(f"status {first.get('status')}, valid XML {first.get('valid_xml')}, in robots.txt {sm['declared_in_robots']}", "Sitemap not reachable/valid/declared", "Fix the sitemap URL, XML and the Sitemap: line in robots.txt.")
    R["MAP-02"] = no("; ".join(pth(u) for u in cap["sitemap_disallowed"][:15]), "Sitemap URLs that robots.txt disallows", "Remove them from the sitemap or unblock them.") if cap["sitemap_disallowed"] else ok("", "No sitemap URL is disallowed in robots.txt")
    se = cap["sitemap_entries"]; badse = [f"{pth(e['url'])} - {e['status']}" for e in se if e["status"] != 200]
    R["MAP-03"] = no("; ".join(badse[:15]), f"{len(badse)} of {len(se)} checked sitemap entries are not 200", "List only final 200 URLs.") if badse else ok(f"0 of {len(se)} checked", "Sitemap entries return 200 without redirect")
    bc2 = [f"{pth(e['url'])} -> {e.get('canonical')}" for e in se if e["status"] == 200 and e.get("canonical") and e["canonical"].rstrip("/") != e["url"].rstrip("/")]
    R["MAP-04"] = no("; ".join(bc2[:15]), "Sitemap entry whose canonical points elsewhere", "List only canonical URLs.") if bc2 else ok("", f"Canonical matches the sitemap URL for the {len(se)} checked entries")
    R["MAP-07"] = ok(f"{cnt} URLs", "Count recorded; compare with the number of pages the site intends to have indexed (ask the owner)") if cnt else no("0 URLs", "Empty sitemap", "Generate the sitemap.")
    langs = {u.split("/")[3] for u in sm["urls"] if len(u.split("/")) > 4 and re.fullmatch(r"[a-z]{2}", u.split("/")[3])}
    R["MAP-08"] = ok("", f"Language folders present in sitemap: {sorted(langs)}") if langs else ("N/A", "", "No language-prefixed URLs in the sitemap", "")
    return {k: v for k, v in R.items() if v}


# ----------------------------------------------------------------------------------------------------------
# Results file: scaffold / validate / report
# ----------------------------------------------------------------------------------------------------------
def find_capture(arg):
    if os.path.isfile(arg): return arg
    cands = []
    for base in (os.path.join(ROOT, "clients", arg, "reports"), os.path.join(ROOT, "seo-audits", arg.replace("https://", "").replace("www.", "").strip("/"))):
        if os.path.isdir(base):
            cands += [os.path.join(base, d, "capture.json") for d in sorted(os.listdir(base)) if d.startswith("seo_audit_")]
    cands = [c for c in cands if os.path.exists(c)]
    if not cands: sys.exit("No capture.json found. Run: python3 scripts/seo_audit.py capture <url> [--slug SLUG]")
    return cands[-1]


def cmd_scaffold(a):
    items = load(); secs = pick_sections(a.sections)
    cp = find_capture(a.target); cap = json.load(open(cp)); d = os.path.dirname(cp)
    auto = auto_results(cap); res = OrderedDict()
    for iid, it in items.items():
        if it["sec"] not in secs: continue
        r = dict(status="TODO", measured="", evidence="", fix="", needs="", auto=False)
        if iid in auto:
            st, m, e, f = auto[iid]; r.update(status=st, measured=m, evidence=e, fix=f, auto=True)
            if st == "FAIL" and "unavailable" in e: r["needs"] = "PageSpeed Insights API"   # tooling gap, not a confirmed problem
        elif iid in NEEDS:
            r.update(status="FAIL", evidence="Cannot be verified with the tools available.", needs=NEEDS[iid], fix=f"Needs: {NEEDS[iid]}.", auto=True)
        res[iid] = r
    out = dict(url=cap["url"], date=cap["date"], sections=secs, pages=[p.get("url") for p in cap["pages"]], items=res)
    path = os.path.join(d, "results.json")
    if os.path.exists(path) and not a.force: sys.exit(f"{path} exists - refusing to overwrite your judgements (use --force to rebuild).")
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    todo = [k for k, v in res.items() if v["status"] == "TODO"]; autod = [k for k, v in res.items() if v["auto"]]
    print(f"Wrote {path}: {len(res)} checks - {len(autod)} pre-filled from the capture / tooling gaps, {len(todo)} TODO for judgement:")
    for k in todo: print(f"  {k:7} {items[k]['text'][:120]}")


def check_results(path, quiet=False):
    items = load(); data = json.load(open(path)); res = data["items"]; errs = []
    for iid, it in items.items():
        if it["sec"] not in data["sections"]: continue
        r = res.get(iid)
        if not r: errs.append(f"{iid}: missing from results"); continue
        if r["status"] not in STATUSES: errs.append(f"{iid}: bad status {r['status']}")
        elif r["status"] == "TODO": errs.append(f"{iid}: still TODO")
        elif r["status"] == "N/A" and not r.get("evidence"): errs.append(f"{iid}: N/A needs a reason in evidence")
        elif r["status"] == "FAIL" and not (r.get("evidence") or r.get("needs")): errs.append(f"{iid}: FAIL needs evidence")
        elif r["status"] == "FAIL" and not (r.get("fix") or r.get("needs")): errs.append(f"{iid}: FAIL needs a fix")
        elif r["status"] == "PASS" and not r.get("evidence"): errs.append(f"{iid}: PASS needs evidence")
    return data, items, errs


def cmd_validate(a):
    data, items, errs = check_results(a.results)
    n = sum(1 for i in items.values() if i["sec"] in data["sections"])
    if errs:
        print(f"INCOMPLETE: {len(errs)} problem(s) in {n} checks"); [print("  " + e) for e in errs]; sys.exit(1)
    print(f"COMPLETE: all {n} checks have a verdict + evidence")


def prio(impact): return "High" if impact >= 8 else "Medium" if impact >= 5 else "Low"


def cmd_report(a):
    data, items, errs = check_results(a.results)
    if errs and not a.allow_incomplete:
        print("Refusing to report: results incomplete"); [print("  " + e) for e in errs]; sys.exit(1)
    res = data["items"]; L = []
    rows = [(items[k], res[k]) for k in res]
    fails = [(i, r) for i, r in rows if r["status"] == "FAIL"]
    nfail_real = [(i, r) for i, r in fails if not r.get("needs")]
    L.append(f"# SEO / GEO audit - {data['url']}\n\nDate: {data['date']}. Pages sampled: " + ", ".join(data["pages"]) + "\n")
    L.append("## What to fix (summary)\n")
    for p in ("High", "Medium", "Low"):
        g = [(i, r) for i, r in nfail_real if prio(i["impact"]) == p]
        L.append(f"**{p} priority** ({len(g)})")
        for i, r in sorted(g, key=lambda x: -x[0]["impact"]): L.append(f"- {i['id']} ({i['impact']}/10) {i['text'][:110]} -> {r.get('fix') or ''}")
        L.append("")
    block = [(i, r) for i, r in fails if i["sec"] in ("C01", "C02")]
    L.append("## Blocking issues (GEO items 1-2)\n" + ("\n".join(f"- {i['id']}: {r.get('measured') or r.get('evidence')}" for i, r in block) if block else "None - crawlability and server-side rendering pass.") + "\n")
    L.append("## Top fixes by impact\n")
    for n_, (i, r) in enumerate(sorted(nfail_real, key=lambda x: (-x[0]["impact"], x[0]["id"]))[:5], 1): L.append(f"{n_}. {i['id']} {i['text'][:120]} - {r.get('fix')}")
    L.append(f"\n## Re-check\nRe-audit freshness on {(date.fromisoformat(data['date']) + timedelta(days=120)).isoformat()} (about 4 months).\n")
    pas = sum(1 for _, r in rows if r["status"] == "PASS"); na = sum(1 for _, r in rows if r["status"] == "N/A")
    L.append(f"## Totals\nPASS {pas} | FAIL {len(fails)} (of which {len(fails) - len(nfail_real)} are tooling gaps) | N/A {na} | total {len(rows)}\n")
    L.append("## Full audit (every check)\n")
    for s in data["sections"]:
        sr = [(items[k], res[k]) for k in res if items[k]["sec"] == s]
        if not sr: continue
        w, h = WHY[s]
        L.append(f"### {SECTIONS[s]} ({len(sr)})\n\n| ID | Item | Result | Impact | Measured value | Why it matters | What happens if it's not fixed |\n|---|---|---|---|---|---|---|")
        for i, r in sr:
            st = r["status"] + (f" (needs {r['needs']})" if r.get("needs") and r["status"] == "FAIL" else "")
            mv = (r.get("measured") or "").replace("|", "/").replace("\n", " ")
            ev = (r.get("evidence") or "").replace("|", "/").replace("\n", " ")
            L.append(f"| {i['id']} | {i['text'].replace('|', '/')[:200]} | {st} | {stars(i['impact'])} {i['impact']}/10 | {mv or '-'} | {r.get('why') or w} {('Seen: ' + ev) if ev else ''} | {r.get('consequence') or h} |")
        L.append("")
    txt = "\n".join(L); out = os.path.join(os.path.dirname(a.results), "report.md"); open(out, "w", encoding="utf-8").write(txt)
    print(txt); print(f"\nSaved {out}")


SHOW = {"failed": "Failed checks only (confirmed problems; checks that need a tool or manual review are left out)",
        "failed+passed": "Failed and passed checks (checks that need a tool or manual review, and N/A, are left out)",
        "all": "All checks, including those that need manual review and N/A"}


SEO_CSS = """
h1{font-size:23pt}
.cover-in{margin-top:6mm;gap:5mm}
.kpis4{display:grid;grid-template-columns:repeat(4,1fr);gap:3mm}
.k{padding:4mm}.k b{display:block;font-size:17pt;font-weight:700;color:#fff;margin-bottom:1mm}.k b em{font-style:normal;color:#4ade80}.k b em.r{color:#ff6b9a}.k b em.a{color:#f5c26b}.k b em.n{color:#a7abb8}
.k span{font-size:7.8pt;line-height:1.4;color:#d0d3db}
.list{display:grid;grid-template-columns:1fr 1fr;gap:1.6mm 6mm;padding:5mm}
.li{display:flex;align-items:center;gap:2.5mm;font-size:8.2pt;color:#e6e8ec}
.li span{flex:1}
.chip2{flex:0 0 auto;padding:.8mm 2.4mm;border-radius:99px;font-size:7pt;font-weight:700;white-space:nowrap}
.chip2.ok{background:rgba(34,197,94,.18);color:#86efac}.chip2.gap{background:rgba(240,180,76,.18);color:#f5c26b}
.chip2.fail{background:rgba(255,45,135,.2);color:#ff8fb8}.chip2.na{background:rgba(255,255,255,.1);color:#a7abb8}
.chip2.hi{background:rgba(255,45,135,.2);color:#ff8fb8}.chip2.me{background:rgba(240,180,76,.18);color:#f5c26b}.chip2.lo{background:rgba(96,165,250,.18);color:#9fc5ff}
.unit{display:flex;flex-direction:column;gap:5mm}
.sec-h{display:flex;align-items:baseline;gap:3mm;margin-top:1mm}.sec-h h2{font-size:15pt}.sec-h span{font-size:8pt;color:var(--muted)}
.pt{padding:4.5mm 5mm;display:flex;flex-direction:column;gap:2.2mm}
.pt-h{display:flex;justify-content:space-between;align-items:baseline;gap:4mm}
.pt-h h3{font-size:11pt;color:#fff}
.chips{display:flex;gap:1.5mm;align-items:center;flex:0 0 auto}
.pt p{font-size:8.8pt;line-height:1.45;color:#d6d9e0}
.lbl2{font-size:7pt;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:.4mm}
.plus2{color:#9be7b2}.minus2{color:#ff9bb8}.plus2 em,.minus2 em{font-style:normal;font-weight:700}
.fixb{font-size:8.6pt;line-height:1.45;color:#ffd0e2;background:rgba(255,45,135,.12);border-left:1.2mm solid #ff2d87;border-radius:1.5mm;padding:2mm 3mm}
.fixb.ok{color:#d3f5de;background:rgba(34,197,94,.10);border-left-color:#22c55e}.fixb.gap{color:#fbe3b6;background:rgba(240,180,76,.12);border-left-color:#f0b44c}
.fixb b{color:#fff}
.chk{font-size:7.4pt;line-height:1.4;color:var(--muted)}
.hero{display:grid;grid-template-columns:52mm 1fr;gap:4mm;align-items:stretch}
.gauge{padding:4mm;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1mm}
.gauge svg{width:40mm;height:40mm}.gauge .gl{font-size:7.6pt;color:var(--muted);text-align:center;line-height:1.35}
.sw{display:flex;flex-direction:column;gap:3mm}
.sw .glass{padding:3.2mm 4mm;flex:1;display:flex;flex-direction:column;gap:1mm}
.sw .t{font-size:7pt;font-weight:700;letter-spacing:.1em;text-transform:uppercase}.sw .t.g{color:#86efac}.sw .t.r{color:#ff8fb8}
.sw b{font-size:10.5pt;color:#fff}.sw .sc{font-size:15pt;font-weight:700}.sw .sc.g{color:#4ade80}.sw .sc.r{color:#ff6b9a}.sw span.d{font-size:7.6pt;line-height:1.4;color:#d0d3db}
.bars{padding:4mm 5mm;display:grid;grid-template-columns:1fr 1fr;gap:1.3mm 7mm}
.br{display:grid;grid-template-columns:44mm 1fr 8mm;align-items:center;gap:2mm;font-size:7.4pt;color:#e6e8ec}
.br span.n{text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.br .tr{height:2.6mm;border-radius:2mm;background:rgba(255,255,255,.09);overflow:hidden}.br .tr i{display:block;height:100%;border-radius:2mm}
.br em{font-style:normal;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.br.best .n,.br.best em{color:#86efac}.br.worst .n,.br.worst em{color:#ff8fb8}
.fx{display:flex;gap:3mm;font-size:8.4pt;line-height:1.42;color:#e6e8ec;padding:2.4mm 4mm}
.fx i{flex:0 0 11mm;font-style:normal;color:var(--muted);font-weight:700}
.fx b{color:#fff;font-weight:600}
"""


def _title(text):
    """Short card title: first sentence of the check, parentheticals dropped, cut at a word boundary."""
    t = re.sub(r"[*`]", "", text or "").replace("—", " - ").replace("–", "-")
    t = re.sub(r"\s*\([^)]*\)", "", t)
    t = re.split(r"\. | - |: ", t)[0].strip()
    return t if len(t) <= 80 else t[:80].rsplit(" ", 1)[0] + "..."


def cmd_pdf(a):
    """Client PDF (dark A4 glass look, same as /55-web-guidelines-audit and scripts/feed_report_pdf.py) built from a COMPLETE results.json.
    --show decides which checks get a card (summary counts always cover all). Every card: Finding, Why we need it (+/-), Proposed fix."""
    import html as H, tempfile, subprocess, pathlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from brand import AGENCY_NAME, LOGO_PATH
    from feed_report_pdf import CSS as BASE_CSS, SWIFT_QA, hex_rgb
    data, items, errs = check_results(a.results)
    if errs: print("Refusing to build the PDF: results incomplete"); [print("  " + e) for e in errs]; sys.exit(1)
    res = data["items"]; e = lambda x: H.escape(str(x or "").replace("—", "-").replace("–", "-"))
    def klass(r): return "ok" if r["status"] == "PASS" else "na" if r["status"] == "N/A" else "gap" if r.get("needs") else "fail"
    def keep(r): return {"failed": klass(r) == "fail", "failed+passed": klass(r) in ("fail", "ok"), "all": True}[a.show]
    allrows = [(items[k], res[k]) for k in res]
    cnt = {c: sum(1 for _, r in allrows if klass(r) == c) for c in ("ok", "fail", "gap", "na")}
    prio = lambda i: "hi" if i["impact"] >= 8 else "me" if i["impact"] >= 6 else "lo"
    PN = dict(hi="High priority", me="Medium priority", lo="Low priority")
    CH = dict(ok="PASS", fail="FIX", gap="NEEDS TOOL", na="N/A")
    primary = "#3E5CE7"
    pl = "#" + "".join(f"{round(int(primary[i:i+2], 16) * .65 + 255 * .35):02x}" for i in (1, 3, 5))
    css = (BASE_CSS + SEO_CSS).replace("__P__", primary).replace("__PL__", pl).replace("__BG__", "#0b1020").replace("__BG2__", "#141a2e").replace("__S__", "#2e8bff") \
        .replace("__PRGB__", hex_rgb(primary)).replace("__SRGB__", hex_rgb("#2e8bff")).replace("__FONT__", "Inter")
    logo = pathlib.Path(LOGO_PATH).resolve()
    logo_html = f'<img class="logo" src="file://{logo}" alt="">' if logo.exists() else f"<b>{AGENCY_NAME}</b>"
    host = urllib.parse.urlparse(data["url"]).netloc or data["url"]

    def card(i, r):
        c = klass(r); w, h = WHY[i["sec"]]
        ev = urllib.parse.unquote(r.get("evidence") or ""); mv = urllib.parse.unquote(r.get("measured") or "")
        if c == "gap": ev = f"Could not be verified with the tools used for this audit: {r.get('needs')}."
        finding = e(ev or "-") + (f" <b>Measured:</b> {e(mv)}" if mv else "")
        plus, minus = r.get("why") or w, r.get("consequence") or h
        if c == "fail": fx = r.get("fix") or "See report.md"
        elif c == "gap": fx = f"Get the data from {r.get('needs')}, then re-judge this point."
        elif c == "na": fx = "Nothing to do for this site."
        else: fx = "No action needed. Keep it this way."
        pchip = f'<b class="chip2 {prio(i)}">{PN[prio(i)]}</b>' if c == "fail" else ""
        return (f'<div class="glass pt"><div class="pt-h"><h3>{e(i["id"])}. {e(_title(i["text"]))}</h3><span class="chips">{pchip}<b class="chip2 {c}">{CH[c]}</b></span></div>'
                f'<div><div class="lbl2">Finding</div><p>{finding}</p></div>'
                f'<div><div class="lbl2">Why we need it</div><p class="plus2"><em>If done right:</em> {e(plus)}</p><p class="minus2"><em>If not:</em> {e(minus)}</p></div>'
                f'<div class="fixb {"" if c == "fail" else c}"><b>Proposed fix.</b> {e(fx)}</div>'
                f'<div class="chk">Check ({i["impact"]}/10 impact): {e(re.sub(r"[*`]", "", i["text"])[:230])}</div></div>')

    units = []   # (html, kind)
    fails = [(i, r) for i, r in allrows if klass(r) == "fail"]
    for pk in ("hi", "me", "lo"):
        rows = sorted([(i, r) for i, r in fails if prio(i) == pk], key=lambda x: -x[0]["impact"])
        for n, (i, r) in enumerate(rows):
            head = f'<div class="sec-h"><h2>{PN[pk]} <span>{len(rows)} fixes</span></h2></div>' if n == 0 else ""
            units.append(("fix", f'<div class="unit">{head}<div class="glass fx"><i>{e(i["id"])}</i><span><b>{e(_title(i["text"]))}.</b> {e(r.get("fix"))}</span></div></div>'))
    for sec in data["sections"]:
        rows = sorted([(i, r) for i, r in allrows if i["sec"] == sec and keep(r)], key=lambda x: -x[0]["impact"])
        for n, (i, r) in enumerate(rows):
            head = f'<div class="sec-h"><h2>{e(SECTIONS[sec])}</h2><span>{len(rows)} shown</span></div>' if n == 0 else ""
            units.append(("card", f'<div class="unit">{head}{card(i, r)}</div>'))

    foot = date.today().isoformat(); pages = []
    def page(inner, title="SEO and AI-search audit"):
        pages.append(f'<section class="page"><div class="head">{logo_html}<span>{e(title)}</span></div>{inner}<div class="foot"><span>{foot}</span><span>{len(pages) + 1}</span></div></section>')
    # SEO health score: impact-weighted share of passed checks among the verifiable ones (N/A and tool-gap checks are left out of the maths)
    sw = {}
    for k, r in res.items():
        c = klass(r)
        if c in ("na", "gap"): continue
        w = items[k]["impact"]; t = sw.setdefault(items[k]["sec"], [0, 0, 0]); t[0] += w; t[1] += w * (c == "ok"); t[2] += 1
    tw, ow = sum(v[0] for v in sw.values()), sum(v[1] for v in sw.values())
    score = round(100 * ow / tw) if tw else 0
    verd = "Strong" if score >= 80 else "Fair" if score >= 60 else "Weak" if score >= 40 else "Poor"
    col = "#4ade80" if score >= 75 else "#f5c26b" if score >= 50 else "#ff6b9a"
    sp = {k: round(100 * v[1] / v[0]) for k, v in sw.items()}
    pool = [k for k in sw if sw[k][2] >= 3] or list(sw)   # sections with at least 3 verifiable checks are ranked best/worst
    best = max(pool, key=lambda k: (sp[k], sw[k][2])); worst = min(pool, key=lambda k: (sp[k], -sw[k][0]))
    also0 = [k for k in sw if sp[k] == 0 and k != worst]
    circ = 2 * 3.14159 * 40
    gauge = (f'<div class="glass gauge"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="9"/>'
             f'<circle cx="50" cy="50" r="40" fill="none" stroke="{col}" stroke-width="9" stroke-linecap="round" stroke-dasharray="{circ * score / 100:.1f} {circ:.1f}" transform="rotate(-90 50 50)"/>'
             f'<text x="50" y="52" text-anchor="middle" font-size="26" font-weight="700" fill="#fff" font-family="Inter,sans-serif">{score}</text>'
             f'<text x="50" y="66" text-anchor="middle" font-size="8" fill="#a7abb8" font-family="Inter,sans-serif">out of 100</text></svg>'
             f'<b style="color:{col};font-size:11pt">{verd}</b><div class="gl">SEO health score</div></div>')
    def sname(k): return re.sub(r"^GEO \d+\. ", "", SECTIONS[k]) if k.startswith("C") and k[1:].isdigit() else SECTIONS[k]
    def sw_card(k, cls, label, text): return (f'<div class="glass"><div class="t {cls}">{label}</div><b>{e(SECTIONS[k])}</b><div><span class="sc {cls}">{sp[k]}</span> <span class="d">/ 100 ({sw[k][2]} checks verified)</span></div><span class="d">{text}</span></div>')
    wtxt = "Biggest drag on the score." + (f" Also at 0: {e(', '.join(sname(k) for k in also0))}." if also0 else "")
    sw_html = '<div class="sw">' + sw_card(best, "g", "Strongest section", "Everything we could verify here passes. Protect it.") + sw_card(worst, "r", "Weakest section", wtxt) + '</div>'
    bars = ""
    for k in sorted(sw, key=lambda k: (sp[k], -sw[k][0])):
        cl = "best" if k == best else "worst" if k == worst else ""
        bc = "#4ade80" if sp[k] >= 75 else "#f5c26b" if sp[k] >= 50 else "#ff6b9a"
        bars += f'<div class="br {cl}"><span class="n">{e(sname(k))}</span><div class="tr"><i style="width:{max(sp[k], 2)}%;background:{bc}"></i></div><em>{sp[k]}</em></div>'
    done = cnt["ok"]
    page(f'''<div class="cover-in" style="display:flex;flex-direction:column"><div class="eyebrow">SEO and AI-search audit</div>
<h1><span class="accent">{e(host)}</span><br>SEO health score {score} / 100</h1>
<p class="lead" style="font-size:9.5pt">All {len(allrows)} checks of the SEO and GEO (AI answer engine) framework were run on {e(data["date"])}. The score is the impact-weighted share of passed checks among the {sum(v[2] for v in sw.values())} that could be verified (not applicable and tool-dependent checks are left out). Re-check after {e((date.fromisoformat(data["date"]) + timedelta(days=120)).isoformat())}.</p>
<div class="hero">{gauge}{sw_html}</div>
<div class="kpis4"><div class="glass k"><b><em>{cnt["ok"]}</em></b><span>checks pass</span></div><div class="glass k"><b><em class="r">{cnt["fail"]}</em></b><span>need fixing</span></div>
<div class="glass k"><b><em class="a">{cnt["gap"]}</em></b><span>need a tool we did not have (Search Console, SEMrush, PageSpeed)</span></div><div class="glass k"><b><em class="n">{cnt["na"]}</em></b><span>not applicable to this site</span></div></div>
<div class="eyebrow" style="margin-top:1mm">Score by section (0-100, worst first)</div><div class="glass bars">{bars}</div><p class="chk">Shown in this report: {e(SHOW[a.show])}.</p></div>''')

    def doc(body): return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SEO audit {e(host)}</title>'
                           '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
                           f'<style>{css}</style></head><body>{body}</body></html>')
    out = pathlib.Path(a.out or os.path.join(os.path.dirname(a.results), f"seo_audit_{a.show}.pdf")).resolve(); html_path = out.with_suffix(".html")
    from playwright.sync_api import sync_playwright
    BUDGET = 256.0
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page()
        mp = out.parent / "_measure.html"
        mp.write_text(doc('<div style="width:180mm;display:flex;flex-direction:column;gap:5mm">' + "".join(h for _, h in units) + "</div>"), encoding="utf-8")
        pg.goto("file://" + str(mp), wait_until="networkidle"); pg.evaluate("document.fonts.ready")
        hs = pg.evaluate("[...document.querySelectorAll('.unit')].map(e=>e.getBoundingClientRect().height/3.7795)"); mp.unlink()
        base = len(pages); cur, used, lastkind = [], 0.0, None
        for (kind, h), hh in zip(units, hs):
            gap = 5 if cur else 0
            if cur and (used + gap + hh > BUDGET or kind != lastkind):
                page("".join(f'{x}' for x in cur) if lastkind != "fix" else "".join(cur)); cur, used, gap = [], 0.0, 0
            cur.append(h); used += gap + hh; lastkind = kind
        if cur: page("".join(cur))
        html_path.write_text(doc("".join(pages)), encoding="utf-8")
        pg.goto("file://" + str(html_path), wait_until="networkidle"); pg.evaluate("document.fonts.ready")
        over = pg.evaluate("""[...document.querySelectorAll('.page')].map((p,i)=>{const r=p.getBoundingClientRect();
          const m=Math.max(...[...p.children].filter(c=>!c.classList.contains('foot')).map(c=>c.getBoundingClientRect().bottom));
          return [i+1, Math.round(r.bottom-m)]}).filter(x=>x[1]<30)""")
        pg.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True); br.close()
    if over: print("WARNING pages with content touching the footer (page, px left):", over)
    print(f"PDF: {out}  ({out.stat().st_size / 1e6:.1f} MB, {len(pages)} pages; showing: {SHOW[a.show]})")
    qd = out.parent / "qa"; qd.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as f: f.write(SWIFT_QA)
    r = subprocess.run(["swift", f.name, str(out), str(qd)], capture_output=True, text=True)
    print(f"QA: {r.stdout.strip()} pages rendered to {qd}/pageN.png" if r.returncode == 0 else "QA render failed: " + r.stderr[-300:])


def main():
    ap = argparse.ArgumentParser(description="SEO / GEO audit helper (see header)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("--sections"); s.set_defaults(f=cmd_list)
    s = sub.add_parser("capture"); s.add_argument("url"); s.add_argument("--slug"); s.add_argument("--pages", type=int, default=8); s.add_argument("--page", action="append", default=[]); s.set_defaults(f=cmd_capture)
    s = sub.add_parser("scaffold"); s.add_argument("target"); s.add_argument("--sections", default="ALL"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_scaffold)
    s = sub.add_parser("validate"); s.add_argument("results"); s.set_defaults(f=cmd_validate)
    s = sub.add_parser("report"); s.add_argument("results"); s.add_argument("--allow-incomplete", action="store_true"); s.set_defaults(f=cmd_report)
    s = sub.add_parser("pdf"); s.add_argument("results"); s.add_argument("--show", choices=list(SHOW), required=True, help="which checks to list: failed | failed+passed | all"); s.add_argument("--out"); s.set_defaults(f=cmd_pdf)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
