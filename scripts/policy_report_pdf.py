#!/usr/bin/env python3
"""
policy_report_pdf.py - client-facing PDF for /55-merchant-policy-check (Merchant Center vs website
alignment with Google's Shopping / Misrepresentation policies).

Purpose
    Same look and the same PDF-safe rules as the /55-feed-title-optimizer report
    (scripts/feed_report_pdf.py - its CSS, page frame and real-PDF QA are imported, not copied):
    dark glass A4 pages in the CLIENT'S OWN brand colors/font/logo, no agency branding.
    Findings are always printed FAIL first, then WARN, then PASS - the script sorts them itself,
    whatever order the spec lists them in.

Usage
    .venv/bin/python scripts/policy_report_pdf.py <spec.json> [--out <file.pdf>] [--no-qa]
    Spec file lives at clients/<slug>/reports/policy_pdf/report_spec.json

Spec
    client, lang (uk|pl|en), date_label, brand {primary, primary_light, bg, bg2, secondary,
    font, heading_font (optional), logo, on_primary}, scope (one line: what was checked), account_status {label, text},
    method [[title, text] x3], sources [str], findings [{status FAIL|WARN|PASS, area, title,
    found, fix}] - PASS items need no fix. Write findings in the client's language from
    clients/<slug>/reports/policy_check_YYYY-MM-DD.json + the saved page texts; quote the site.

Changelog
    2026-10-15  Initial version, built for a client misrepresentation audit.
    2026-10-28  Optional spec.pack_scale (<1 = fewer items per page) and spec.labels override, used by cro_report_pdf.py.
    2026-10-28  Optional spec.funnel -> page 2 (right after the cover) "sales funnel" (bars per stage + step-to-step lines), built by cro_report_pdf.py.
"""
import argparse, html, json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feed_report_pdf import CSS as FEED_CSS, SWIFT_QA, hex_rgb  # noqa: E402

ORDER = {"FAIL": 0, "WARN": 1, "PASS": 2}

LABELS = {
    "uk": dict(head="Аудит Merchant Center і сайту", eyebrow="Google Merchant Center · Правила Google Shopping",
               h1_a="Відповідність", h1_b="Merchant Center і сайту", h1_c="правилам Google",
               lead="Перевірили те саме, що перевіряє співробітник Google перед зняттям блокування за «Неправдиве представлення»: чи збігаються дані в Merchant Center з сайтом і чи є на сайті все, що Google вимагає від магазину.",
               k_fail="критичних проблем - виправити до запиту перевірки", k_warn="зауважень - бажано виправити",
               k_pass="перевірок пройдено", k_acc="Статус акаунта",
               method_h="Як ми перевіряли", method_sub="Автоматична перевірка налаштувань, сторінок сайту і товарів, а потім ручне прочитання кожної сторінки з правилами.",
               src_h="На які правила Google спираємось",
               legend_h="Що означають статуси",
               fail="Критично", warn="Зауваження", pass_="Пройдено",
               legend_fail="Пряма невідповідність правилам Google або між Merchant Center і сайтом. Через такі пункти акаунт блокують.",
               legend_warn="Не порушення саме по собі, але знижує довіру перевірника або може стати невідповідністю.",
               legend_pass="Перевірено, все збігається.",
               fail_h="Критичні проблеми", fail_sub="Їх треба виправити до запиту повторної перевірки в Merchant Center.",
               warn_h="Зауваження", warn_sub="Бажано виправити разом з критичними, щоб перевірка пройшла з першого разу.",
               pass_h="Що вже в порядку", pass_sub="Ці пункти перевірені й відповідають вимогам Google.",
               found="Що знайшли", fix="Що зробити", area="Розділ", check="Перевірка", result="Результат",
               cont="(продовження)"),
    "pl": dict(head="Audyt Merchant Center i strony", eyebrow="Google Merchant Center · Zasady Google Shopping",
               h1_a="Zgodność", h1_b="Merchant Center i strony", h1_c="z zasadami Google",
               lead="Sprawdziliśmy to samo, co pracownik Google przed zdjęciem zawieszenia za „wprowadzanie w błąd”: czy dane w Merchant Center zgadzają się ze stroną i czy strona ma wszystko, czego Google wymaga od sklepu.",
               k_fail="krytycznych problemów - do poprawy przed prośbą o weryfikację", k_warn="uwag - warto poprawić",
               k_pass="sprawdzeń zaliczonych", k_acc="Status konta",
               method_h="Jak sprawdzaliśmy", method_sub="Automatyczne sprawdzenie ustawień, stron i produktów, potem ręczna lektura każdej strony z zasadami.",
               src_h="Na jakich zasadach Google się opieramy", legend_h="Co oznaczają statusy",
               fail="Krytyczne", warn="Uwaga", pass_="Zaliczone",
               legend_fail="Bezpośrednia niezgodność z zasadami Google albo między Merchant Center a stroną. Za takie punkty konta są zawieszane.",
               legend_warn="Samo w sobie nie jest naruszeniem, ale obniża zaufanie weryfikatora albo może stać się niezgodnością.",
               legend_pass="Sprawdzone, wszystko się zgadza.",
               fail_h="Problemy krytyczne", fail_sub="Do poprawy przed ponowną prośbą o weryfikację w Merchant Center.",
               warn_h="Uwagi", warn_sub="Warto poprawić razem z krytycznymi, żeby weryfikacja przeszła za pierwszym razem.",
               pass_h="Co już jest w porządku", pass_sub="Te punkty są sprawdzone i spełniają wymagania Google.",
               found="Co znaleźliśmy", fix="Co zrobić", area="Obszar", check="Sprawdzenie", result="Wynik",
               cont="(ciąg dalszy)"),
    "en": dict(head="Merchant Center & website audit", eyebrow="Google Merchant Center · Google Shopping policies",
               h1_a="Merchant Center and website", h1_b="alignment", h1_c="with Google's policies",
               lead="We checked what a Google reviewer checks before lifting a Misrepresentation suspension: does Merchant Center match the website, and does the website have everything Google expects from a store.",
               k_fail="critical issues - fix before requesting a review", k_warn="warnings - worth fixing",
               k_pass="checks passed", k_acc="Account status",
               method_h="How we checked", method_sub="Automated checks of settings, pages and products, then a manual read of every policy page.",
               src_h="Google policies this is based on", legend_h="What the statuses mean",
               fail="Critical", warn="Warning", pass_="Passed",
               legend_fail="A direct mismatch with Google's policies or between Merchant Center and the site. Accounts get suspended for these.",
               legend_warn="Not a violation on its own, but lowers reviewer trust or can turn into a mismatch.",
               legend_pass="Checked, everything matches.",
               fail_h="Critical issues", fail_sub="Fix these before requesting another review in Merchant Center.",
               warn_h="Warnings", warn_sub="Worth fixing together with the critical ones so the review passes first time.",
               pass_h="What is already fine", pass_sub="These items were checked and meet Google's requirements.",
               found="What we found", fix="What to do", area="Area", check="Check", result="Result",
               cont="(continued)"),
}

EXTRA_CSS = '''
.k-fail b{color:#ff6b6b}.k-warn b{color:#ffb020}.k-pass b{color:#4ade80}
.kpi.acc b{font-size:13pt;line-height:1.25;color:#ff6b6b}
.step i{color:__ONP__}
.pill{display:inline-block;font-size:7pt;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:1mm 2.6mm;border-radius:99px}
.pill.FAIL{background:rgba(255,107,107,.18);color:#ff8a8a;border:1px solid rgba(255,107,107,.55)}
.pill.WARN{background:rgba(255,176,32,.16);color:#ffc04d;border:1px solid rgba(255,176,32,.5)}
.pill.PASS{background:rgba(74,222,128,.14);color:#6ee7a0;border:1px solid rgba(74,222,128,.45)}
.legend{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm}
.legend .glass{padding:4.5mm;display:flex;flex-direction:column;gap:2mm;font-size:8.6pt;line-height:1.45;color:#d0d3db}
.srcs{padding:5mm 6mm}.srcs ul{padding-left:5mm;font-size:8.8pt;line-height:1.6;color:#d0d3db;display:flex;flex-direction:column;gap:1mm;margin-top:2mm}
.find{padding:4.5mm 5.5mm;display:flex;flex-direction:column;gap:2.4mm;border-left:3px solid var(--line)}
.find.FAIL{border-left-color:#ff6b6b}.find.WARN{border-left-color:#ffb020}
.find .top{display:flex;align-items:center;gap:3mm}
.find .area{font-size:7.5pt;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600}
.find h3{font-size:11.5pt;line-height:1.3}
.find .row{display:grid;grid-template-columns:24mm 1fr;gap:3mm;font-size:8.8pt;line-height:1.5}
.find .row b{font-size:7pt;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding-top:.6mm}
.find .row.fx span{color:#fff}.find .row.fx b{color:var(--pl)}
.find q{font-style:italic;color:#e6e8ee}
a{color:var(--pl);text-decoration:none;border-bottom:1px solid rgba(__PRGB__,.45)}
table.pass td{font-size:8.3pt;vertical-align:top;line-height:1.38;padding-top:1.3mm;padding-bottom:1.3mm}
table.pass td.ar{width:34mm;color:var(--muted);font-size:7.6pt;text-transform:uppercase;letter-spacing:.06em}
table.pass td.ok{width:6mm;color:#4ade80;font-weight:700}
.fun{padding:5mm 6mm;display:flex;flex-direction:column;gap:1.6mm}
.fs .fl{display:flex;justify-content:space-between;align-items:baseline;font-size:10pt;margin-bottom:1.2mm}
.fs .fl b{font-size:13pt}
.fbar{height:7mm;border-radius:2mm;background:rgba(255,255,255,.07)}
.fbar i{display:block;height:100%;border-radius:2mm;background:var(--pl)}
.fc{font-size:8.6pt;color:#d0d3db;padding:.4mm 0 .4mm 2mm}.fc .fa{color:var(--pl);margin-right:2mm;font-size:7pt}
.fc{display:flex;align-items:center;gap:2.5mm}.fc .ft{flex:1}.fc .fbn{font-size:7.8pt;color:var(--muted)}.fc .fbo{font-size:8.6pt;font-weight:700;color:#fff}.fc .pill{white-space:nowrap}
.fsum{padding:4.5mm 6mm;margin-top:3mm}.fsum p{font-size:9.4pt;line-height:1.55;color:#e6e8ee;margin-top:1.5mm}
.fc.gap{color:#ffc04d}.fc.gap .fa{color:#ffb020}
.funo{padding:4mm 6mm;display:flex;align-items:baseline;gap:4mm;margin-top:3mm}.funo b{font-size:20pt;color:var(--pl)}.funo span{font-size:9pt;color:#d0d3db}
'''


def card_height_mm(f):
    """Rough height so findings can be packed onto fixed A4 pages (QA catches misses)."""
    lines = lambda t, w: max(1, -(-len(t or "") // w))
    h = 17 + lines(f.get("title"), 70) * 5.2 + lines(f.get("found"), 95) * 4.6
    if f.get("fix"):
        h += lines(f["fix"], 95) * 4.6 + 2.4
    return h + 4  # gap


def build(spec, base):
    L = {**LABELS[spec.get("lang", "uk")], **spec.get("labels", {})}
    b = spec["brand"]
    path = lambda p: "file://" + os.path.abspath(os.path.join(base, p))
    esc = html.escape
    logo = f'<img class="logo" src="{path(b["logo"])}" alt="">'
    foot = esc(spec.get("date_label", ""))  # no agency branding in the client PDF
    pages = []

    def page(inner, cls=""):
        pages.append(f'<section class="page {cls}"><div class="head">{logo}<span>{L["head"]}</span></div>{inner}'
                     f'<div class="foot"><span>{foot}</span><span>{len(pages)+1}</span></div></section>')

    findings = sorted(spec["findings"], key=lambda f: ORDER[f["status"]])  # FAIL -> WARN -> PASS, always
    n = {s: sum(1 for f in findings if f["status"] == s) for s in ORDER}
    acc = spec.get("account_status", {})

    # 1 cover
    pages.append(f'''<section class="page cover"><div class="cover-in">{logo.replace('class="logo"', 'class="logo big"')}
<div class="eyebrow">{L["eyebrow"]}</div>
<h1>{L["h1_a"]}<br><span class="accent">{L["h1_b"]}</span> {L["h1_c"]}</h1>
<p class="lead">{L["lead"]}</p>
<div class="kpis">
<div class="glass kpi k-fail"><b>{n["FAIL"]}</b><span>{L["k_fail"]}</span></div>
<div class="glass kpi k-warn"><b>{n["WARN"]}</b><span>{L["k_warn"]}</span></div>
<div class="glass kpi k-pass"><b>{n["PASS"]}</b><span>{L["k_pass"]}</span></div>
<div class="glass kpi acc"><span>{L["k_acc"]}</span><b>{esc(acc.get("label", ""))}</b><span>{esc(acc.get("text", ""))}</span></div></div>
<p class="period">{esc(spec.get("scope", ""))}</p></div>
<div class="foot"><span>{foot}</span><span>1</span></div></section>''')

    # 1b optional page right after the cover: sales funnel (spec.funnel, pre-formatted strings; solid fills only, PDF-safe)
    fn = spec.get("funnel")
    if fn:
        parts = []
        for i, s in enumerate(fn["stages"]):
            parts.append(f'<div class="fs"><div class="fl"><span>{esc(s["name"])}</span><b>{esc(s["users"])}</b></div>'
                         f'<div class="fbar"><i style="width:{s["w"]}%"></i></div></div>')
            if s.get("next"):
                chip = (f'<span class="fbo">{esc(s["ours"])}</span><span class="fbn">{esc(s["bench"])}</span><span class="pill {s["pill"]}">{esc(s["pill_text"])}</span>'
                        if s.get("bench") else "")
                parts.append(f'<div class="fc{" gap" if s.get("gap") else ""}"><span class="fa">&#9660;</span>'
                             f'<span class="ft">{esc(s["next"])}</span>{chip}</div>')
        notes = "".join(f"<li>{esc(n)}</li>" for n in fn.get("notes", []))
        page(f'<h2>{esc(fn["title"])}</h2><p class="sub">{esc(fn["sub"])}</p>'
             f'<div class="glass fun">{"".join(parts)}</div>'
             f'<div class="glass funo"><b>{esc(fn["overall_value"])}</b><span>{esc(fn["overall_label"])}</span></div>'
             + (f'<div class="glass fsum"><div class="eyebrow">{esc(fn["summary_h"])}</div><p>{esc(fn["summary"])}</p></div>' if fn.get("summary") else "") +
             f'<div class="glass srcs"><ul>{notes}</ul></div>')

    # 2 method + legend + sources
    steps = "".join(f'<div class="glass step"><i>{i+1}</i><h3>{esc(t)}</h3><p>{esc(x)}</p></div>'
                    for i, (t, x) in enumerate(spec.get("method", [])[:3]))
    srcs = "".join(f"<li>{esc(s)}</li>" for s in spec.get("sources", []))
    page(f'''<h2>{L["method_h"]}</h2><p class="sub">{L["method_sub"]}</p><div class="steps">{steps}</div>
<h2>{L["legend_h"]}</h2><div class="legend">
<div class="glass"><span class="pill FAIL">{L["fail"]}</span>{L["legend_fail"]}</div>
<div class="glass"><span class="pill WARN">{L["warn"]}</span>{L["legend_warn"]}</div>
<div class="glass"><span class="pill PASS">{L["pass_"]}</span>{L["legend_pass"]}</div></div>
<div class="glass srcs"><div class="eyebrow">{L["src_h"]}</div><ul>{srcs}</ul></div>''')

    # 3 FAIL then WARN cards, greedily packed onto pages
    def card(f):
        st_label = L["fail"] if f["status"] == "FAIL" else L["warn"]
        fix = f'<div class="row fx"><b>{L["fix"]}</b><span>{f["fix"]}</span></div>' if f.get("fix") else ""
        return (f'<div class="glass find {f["status"]}"><div class="top"><span class="pill {f["status"]}">{st_label}</span>'
                f'<span class="area">{esc(f.get("area", ""))}</span></div><h3>{esc(f["title"])}</h3>'
                f'<div class="row"><b>{L["found"]}</b><span>{f["found"]}</span></div>{fix}</div>')

    for status, hk, sk in (("FAIL", "fail_h", "fail_sub"), ("WARN", "warn_h", "warn_sub")):
        group = [f for f in findings if f["status"] == status]
        first, cur, used = True, [], 0
        sc = spec.get("pack_scale", 1)  # <1 packs fewer cards per page (long audits, e.g. /55-cro-audit)
        budget_first, budget = 225 * sc, 245 * sc
        for f in group:
            h = card_height_mm(f)
            if cur and used + h > (budget_first if first else budget):
                head = f'<h2>{L[hk]}</h2><p class="sub">{L[sk]}</p>' if first else f'<h2>{L[hk]} <span class="sub">{L["cont"]}</span></h2>'
                page(head + "".join(cur)); first, cur, used = False, [], 0
            cur.append(card(f)); used += h
        if cur:
            head = f'<h2>{L[hk]}</h2><p class="sub">{L[sk]}</p>' if first else f'<h2>{L[hk]} <span class="sub">{L["cont"]}</span></h2>'
            page(head + "".join(cur))

    # 4 PASS as a compact table, paginated
    passed = [f for f in findings if f["status"] == "PASS"]

    def row_mm(f):  # same idea as card_height_mm: pack rows by estimated height, QA catches misses
        lines = lambda t, w: max(1, -(-len(t or "") // w))
        return 4.6 + lines(f["title"], 90) * 3.9 + (lines(f.get("found"), 105) * 3.6 if f.get("found") else 0)

    chunks, cur, used = [], [], 0
    for f in passed:
        budget = (268 if not chunks else 278) * spec.get("pack_scale", 1)
        if cur and used + row_mm(f) > budget:
            chunks.append(cur); cur, used = [], 0
        cur.append(f); used += row_mm(f)
    if cur:
        chunks.append(cur)
    for i, chunk in enumerate(chunks):
        rows = "".join(f'<tr><td class="ok">✓</td><td class="ar">{esc(f.get("area", ""))}</td><td><b>{esc(f["title"])}</b>'
                       f'{"<br><span class=small>" + f["found"] + "</span>" if f.get("found") else ""}</td></tr>'
                       for f in chunk)
        head = f'<h2>{L["pass_h"]}</h2><p class="sub">{L["pass_sub"]}</p>' if i == 0 else f'<h2>{L["pass_h"]} <span class="sub">{L["cont"]}</span></h2>'
        page(head + f'<div class="glass tbl"><table class="pass"><tbody>{rows}</tbody></table></div>')

    css = (FEED_CSS + EXTRA_CSS).replace("__P__", b["primary"]).replace("__PL__", b.get("primary_light", b["primary"])) \
        .replace("__BG__", b.get("bg", "#17171b")).replace("__BG2__", b.get("bg2", "#1d1e25")) \
        .replace("__S__", b.get("secondary", "#6b748b")).replace("__PRGB__", hex_rgb(b["primary"])) \
        .replace("__SRGB__", hex_rgb(b.get("secondary", "#6b748b"))).replace("__FONT__", b.get("font", "Inter")) \
        .replace("__ONP__", b.get("on_primary", "#fff"))
    font_q = b.get("font", "Inter").replace(" ", "+")
    if b.get("heading_font"):   # e.g. a display face the site uses for headings (e.g. a condensed display font) + readable body font
        font_q += "&family=" + b["heading_font"].replace(" ", "+") + ":wght@400;500;600;700"
        css += f'h1,h2,h3,.kpi b,.ins b{{font-family:"{b["heading_font"]}",sans-serif;letter-spacing:0}}'
    font_q = font_q.replace(":wght@400;500;600;700&family", "&family")
    doc = (f'<!doctype html><html lang="{spec.get("lang", "uk")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
           f'<title>{esc(spec.get("client", ""))} - Merchant Center</title>'
           f'<link href="https://fonts.googleapis.com/css2?family={font_q.split("&")[0]}:wght@400;500;600;700{("&" + font_q.split("&", 1)[1]) if "&" in font_q else ""}&display=swap" rel="stylesheet">'
           f'<style>{css}</style></head><body>{"".join(pages)}</body></html>')
    if "\u2014" in doc:
        sys.exit("ERROR: em dash in report text - use a hyphen (workspace rule)")
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec"); ap.add_argument("--out"); ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.spec))
    spec = json.load(open(a.spec, encoding="utf-8"))
    out = a.out or os.path.join(base, f'{spec.get("client", "client")} - Merchant Center audit.pdf')
    doc = build(spec, base)
    html_path = os.path.splitext(out)[0] + ".html"
    open(html_path, "w", encoding="utf-8").write(doc)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page()
        pg.goto("file://" + os.path.abspath(html_path), wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        over = pg.evaluate("""[...document.querySelectorAll('.page')].map((p,i)=>{const r=p.getBoundingClientRect();
          const m=Math.max(...[...p.children].filter(c=>!c.classList.contains('foot')).map(c=>c.getBoundingClientRect().bottom));
          return [i+1, Math.round(r.bottom-m)]}).filter(x=>x[1]<30)""")
        broken = pg.evaluate("[...document.images].filter(i=>!i.naturalWidth).map(i=>i.src)")
        pg.pdf(path=out, format="A4", print_background=True, prefer_css_page_size=True)
        br.close()
    if broken: print("WARNING broken images:", broken)
    if over: print("WARNING pages with content touching/over the footer (page, px left):", over)
    print("PDF:", out, f"({os.path.getsize(out)/1e6:.1f} MB)")
    if not a.no_qa:
        qa = os.path.join(os.path.dirname(out), "qa"); os.makedirs(qa, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as f: f.write(SWIFT_QA)
        r = subprocess.run(["swift", f.name, out, qa], capture_output=True, text=True)
        print(f"QA: {r.stdout.strip()} real PDF pages rendered to {qa}/pageN.png" if r.returncode == 0
              else "QA render failed (swift/PDFKit): " + r.stderr[-300:])


if __name__ == "__main__":
    main()
