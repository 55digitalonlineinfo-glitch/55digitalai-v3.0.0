#!/usr/bin/env python3
"""
feed_report_pdf.py - client-facing PDF report for /55-feed-title-optimizer (before/after titles and
descriptions, argued with Keyword Planner volumes + Google Ads search-term conversion value).

Purpose
    Renders a dark glassmorphism A4 report in the CLIENT'S OWN brand style (colors, font, logo
    taken from the client's website) from one JSON spec, then verifies the real PDF output.
    Built from a real client report whose first versions had background bugs that only showed up
    in the PDF, never in the HTML preview.

Usage
    .venv/bin/python scripts/feed_report_pdf.py <spec.json> [--out <file.pdf>] [--no-qa]
    Example spec: feed-optimization/example/report_spec.json (build it with make_example.py)
    Relative paths inside the spec (logo, product images) resolve against the spec's folder.

PDF-safe styling rules baked in (do NOT reintroduce these, each one broke a real PDF):
    - no `filter: blur()` blobs: rasterized into banded / clipped rectangles. Page glow = plain
      radial-gradient() layers on the page background instead.
    - no outer `box-shadow` on cards: Chromium prints the blurred shadow as an opaque BLACK block
      behind every card. Only a 1px inset highlight is allowed.
    - no gradient fill inside cards: left a visible horizontal seam across the card in the PDF.
      Cards use one solid rgba() fill.
    - no `backdrop-filter`: not supported in print.
    - every page is a fixed 210x297mm box; the script fails loudly if content overflows a page.

QA (on by default)
    Renders the ACTUAL PDF pages to PNG via macOS PDFKit (swift) into <out_dir>/qa/ - look at
    those, not at the HTML, before calling the report done.

Changelog
    2026-10-07  Initial version, generalized from a one-off client report builder.
    2026-10-12  Optional spec["labels"] overrides any LABELS entry (e.g. highlight color wording).
    2026-10-12  Ported into this workspace.
"""
import argparse, html, json, os, re, subprocess, sys, tempfile

LABELS = {
    "pl": dict(
        head="Optymalizacja feedu Google Shopping",
        eyebrow="Google Merchant Center · Google Shopping · Performance Max",
        h1_a="Optymalizacja tytułów i opisów", h1_b="{n} najlepiej sprzedających się", h1_c="produktów",
        lead="Nowe tytuły i opisy oparte na danych: ile osób szuka danej frazy (Google Keyword Planner) oraz które frazy faktycznie przyniosły sprzedaż na Państwa koncie Google Ads.",
        method_h="Jak powstały nowe tytuły i opisy",
        method_sub="Trzy źródła danych, a każda zmiana ma uzasadnienie w liczbach albo na stronie produktu.",
        s1_h="Keyword Planner", s1="Sprawdziliśmy, ile razy w miesiącu klienci wpisują w Google frazy opisujące produkty. To mówi, <b>jak klienci nazywają produkt</b>.",
        s2_h="Raport wyszukiwanych haseł Google Ads", s2="{terms} prawdziwych zapytań z Państwa kampanii z kosztami, konwersjami i wartością konwersji. To mówi, <b>które słowa sprzedają</b>, a nie tylko są popularne.",
        s3_h="Weryfikacja ze stroną produktu", s3="Każde zdanie w nowym opisie porównaliśmy z kartą produktu. W opisach są <b>tylko cechy potwierdzone na stronie</b>, bez dopisywania czegokolwiek.",
        formula="Nowa struktura tytułu",
        kp_h="Krok 1: jak klienci szukają produktów", kp_sub="Średnia liczba wyszukiwań miesięcznie, Google Keyword Planner.",
        kp_col="Fraza", kp_vol="Wyszukiwań / mies.",
        ads_h="Krok 2: które słowa faktycznie sprzedają",
        ads_sub="Raport wyszukiwanych haseł Google Ads, {period}. Frazy pogrupowane w tematy (odmiany z polskimi znakami i bez liczone razem). Frazy z marką wyłączone, bo te osoby już znają markę.",
        c_theme="Temat frazy", c_cost="Koszt", c_conv="Konw.", c_val="Wartość konwersji", c_roas="ROAS", c_dec="Decyzja",
        top_h="Frazy z największą wartością konwersji", top_sub="Pojedyncze zapytania bez marki, które przyniosły najwięcej sprzedaży. Te słowa trafiły do nowych tytułów i opisów.",
        c_term="Wyszukiwane hasło", c_convs="Konwersje",
        share_h="Skąd pochodzi sprzedaż z Google Ads", share_brand="Marka", share_b="z frazami zawierającymi markę", share_g="z fraz ogólnych (bez marki)",
        share_note="Nowe tytuły celują w frazy ogólne, czyli w klientów, którzy jeszcze nie znają marki. To tam jest najwięcej miejsca na wzrost.",
        changes_h="Co dodaliśmy, a co usunęliśmy",
        ba_h="Przed i po: tytuły i opisy", ba_sub="Na czerwono: frazy wybrane na podstawie danych z kroków 1 i 2. „Przed” w opisie to początek obecnego opisu ze strony produktu.",
        before="Przed", after="Po", chars="znaków", sales="sprzedaż",
        k_products="produktów z najwyższą wartością sprzedaży", k_terms="wyszukiwanych haseł przeanalizowanych z konta Google Ads",
        k_value="wartości konwersji w analizowanym okresie", k_kp="fraz sprawdzonych w Keyword Planner",
        period="Dane Google Ads: {period} · Keyword Planner: średnia miesięczna",
    ),
    "uk": dict(
        head="Оптимізація фіду Google Shopping",
        eyebrow="Google Merchant Center · Google Shopping · Performance Max",
        h1_a="Оптимізація назв і описів", h1_b="{n} найкраще продаваних", h1_c="товарів",
        lead="Нові назви та описи на основі даних: скільки людей шукає фразу (Google Keyword Planner) і які фрази реально принесли продажі у вашому акаунті Google Ads.",
        method_h="Як створені нові назви та описи",
        method_sub="Три джерела даних, і кожна зміна має обґрунтування в цифрах або на сторінці товару.",
        s1_h="Keyword Planner", s1="Перевірили, скільки разів на місяць клієнти вводять у Google фрази, що описують товари. Це показує, <b>як клієнти називають товар</b>.",
        s2_h="Звіт пошукових запитів Google Ads", s2="{terms} реальних запитів з ваших кампаній з витратами, конверсіями та цінністю конверсій. Це показує, <b>які слова продають</b>, а не лише популярні.",
        s3_h="Перевірка зі сторінкою товару", s3="Кожне речення нового опису звірили з карткою товару. В описах <b>лише характеристики, підтверджені на сторінці</b>.",
        formula="Нова структура назви",
        kp_h="Крок 1: як клієнти шукають товари", kp_sub="Середня кількість пошуків на місяць, Google Keyword Planner.",
        kp_col="Фраза", kp_vol="Пошуків / міс.",
        ads_h="Крок 2: які слова справді продають",
        ads_sub="Звіт пошукових запитів Google Ads, {period}. Фрази згруповані в теми. Брендові фрази виключені, бо ці люди вже знають бренд.",
        c_theme="Тема фрази", c_cost="Витрати", c_conv="Конв.", c_val="Цінність конверсій", c_roas="ROAS", c_dec="Рішення",
        top_h="Фрази з найбільшою цінністю конверсій", top_sub="Окремі небрендові запити, що принесли найбільше продажів. Ці слова потрапили в нові назви та описи.",
        c_term="Пошуковий запит", c_convs="Конверсії",
        share_h="Звідки продажі з Google Ads", share_brand="Бренд", share_b="з фраз із брендом", share_g="із загальних фраз (без бренду)",
        share_note="Нові назви націлені на загальні фрази, тобто на клієнтів, які ще не знають бренд. Там найбільше простору для зростання.",
        changes_h="Що додали і що прибрали",
        ba_h="До і після: назви та описи", ba_sub="Червоним: фрази, обрані на основі даних з кроків 1 і 2. «До» в описі - початок поточного опису зі сторінки товару.",
        before="До", after="Після", chars="символів", sales="продажі",
        k_products="товарів з найвищою цінністю продажів", k_terms="пошукових запитів проаналізовано з акаунту Google Ads",
        k_value="цінності конверсій за аналізований період", k_kp="фраз перевірено в Keyword Planner",
        period="Дані Google Ads: {period} · Keyword Planner: середнє на місяць",
    ),
    "en": dict(
        head="Google Shopping feed optimization",
        eyebrow="Google Merchant Center · Google Shopping · Performance Max",
        h1_a="Title and description optimization", h1_b="{n} best-selling", h1_c="products",
        lead="New titles and descriptions based on data: how many people search each phrase (Google Keyword Planner) and which phrases actually drove sales in your Google Ads account.",
        method_h="How the new titles and descriptions were built",
        method_sub="Three data sources, and every change is backed by numbers or by the product page.",
        s1_h="Keyword Planner", s1="We checked how often customers search for phrases describing the products. This shows <b>what customers call the product</b>.",
        s2_h="Google Ads search terms report", s2="{terms} real queries from your campaigns with cost, conversions and conversion value. This shows <b>which words sell</b>, not just which are popular.",
        s3_h="Checked against the product page", s3="Every sentence of the new description was checked against the product page. Descriptions contain <b>only features confirmed on the page</b>.",
        formula="New title structure",
        kp_h="Step 1: how customers search", kp_sub="Average monthly searches, Google Keyword Planner.",
        kp_col="Phrase", kp_vol="Searches / mo.",
        ads_h="Step 2: which words actually sell",
        ads_sub="Google Ads search terms report, {period}. Phrases grouped into themes. Branded phrases excluded, since those people already know the brand.",
        c_theme="Phrase theme", c_cost="Cost", c_conv="Conv.", c_val="Conversion value", c_roas="ROAS", c_dec="Decision",
        top_h="Phrases with the highest conversion value", top_sub="Individual non-branded queries that drove the most sales. These words went into the new titles and descriptions.",
        c_term="Search term", c_convs="Conversions",
        share_h="Where Google Ads sales come from", share_brand="Brand", share_b="from branded phrases", share_g="from generic phrases",
        share_note="The new titles target generic phrases, i.e. customers who don't know the brand yet. That's where the most room for growth is.",
        changes_h="What we added and removed",
        ba_h="Before and after: titles and descriptions", ba_sub="In red: phrases chosen based on steps 1 and 2. \"Before\" for the description is the start of the current product-page description.",
        before="Before", after="After", chars="characters", sales="sales",
        k_products="best-selling products", k_terms="search terms analysed from Google Ads",
        k_value="conversion value in the analysed period", k_kp="phrases checked in Keyword Planner",
        period="Google Ads data: {period} · Keyword Planner: monthly average",
    ),
}

def build(spec, base):
    L = {**LABELS[spec.get("lang", "pl")], **spec.get("labels", {})}  # spec may override any label
    cur = spec.get("currency", "zł")
    b = spec["brand"]
    def money(n): return f"{n:,.0f}".replace(",", " ") + f" {cur}"
    def num(n): return f"{n:,.0f}".replace(",", " ")
    def path(p): return "file://" + os.path.abspath(os.path.join(base, p))
    kw = sorted(spec.get("highlight", []), key=len, reverse=True)
    def hl(text):
        t = html.escape(text)
        if not kw: return t
        pat = "|".join(re.escape(html.escape(k)) for k in kw)
        return re.sub(f"({pat})", r"<mark>\1</mark>", t, flags=re.I)
    logo = f'<img class="logo" src="{path(b["logo"])}" alt="">'
    foot = html.escape(spec.get("date_label", ""))  # no agency branding in the client PDF
    pages = []
    def page(inner, cls=""):
        pages.append(f'<section class="page {cls}"><div class="head">{logo}<span>{L["head"]}</span></div>{inner}'
                     f'<div class="foot"><span>{foot}</span><span>{len(pages)+1}</span></div></section>')

    prods = spec["products"]
    k = spec["kpis"]
    # 1 cover
    pages.append(f'''<section class="page cover"><div class="cover-in">{logo.replace('class="logo"','class="logo big"')}
<div class="eyebrow">{L["eyebrow"]}</div>
<h1>{L["h1_a"]}<br><span class="accent">{L["h1_b"].format(n=len(prods))}</span> {html.escape(spec.get("product_noun", L["h1_c"]))}</h1>
<p class="lead">{L["lead"]}</p>
<div class="kpis">
<div class="glass kpi"><b>{len(prods)}</b><span>{L["k_products"]}</span></div>
<div class="glass kpi"><b>{num(k["terms"])}</b><span>{L["k_terms"]}</span></div>
<div class="glass kpi"><b>{money(k["conv_value"])}</b><span>{L["k_value"]}</span></div>
<div class="glass kpi"><b>{k["kp_terms"]}</b><span>{L["k_kp"]}</span></div></div>
<p class="period">{L["period"].format(period=html.escape(spec["period"]))}</p></div>
<div class="foot"><span>{foot}</span><span>1</span></div></section>''')

    # 2 method
    f = spec["title_formula"]
    chips = '<span class="plus">+</span>'.join(
        f'<span class="chip{" main" if i == 0 else ""}">{html.escape(c)}</span>' for i, c in enumerate(f["chips"]))
    rules = "".join(f"<li>{html.escape(r)}</li>" for r in spec.get("rules", []))
    page(f'''<h2>{L["method_h"]}</h2><p class="sub">{L["method_sub"]}</p>
<div class="steps"><div class="glass step"><i>1</i><h3>{L["s1_h"]}</h3><p>{L["s1"]}</p></div>
<div class="glass step"><i>2</i><h3>{L["s2_h"]}</h3><p>{L["s2"].format(terms=num(k["terms"]))}</p></div>
<div class="glass step"><i>3</i><h3>{L["s3_h"]}</h3><p>{L["s3"]}</p></div></div>
<div class="glass formula"><div class="eyebrow">{L["formula"]}</div><div class="f-row">{chips}</div>
<p class="ex">{hl(f["example"])}</p><ul class="rules">{rules}</ul></div>''')

    def insights(items):
        return '<div class="insights">' + "".join(
            f'<div class="glass ins"><b class="{c}">{html.escape(big)}</b><span>{html.escape(txt)}</span></div>'
            for big, txt, c in [(i[0], i[1], i[2] if len(i) > 2 else "accent") for i in items]) + "</div>"

    # 3 keyword planner
    kp = spec["keyword_planner"]; mx = max(v for _, v in kp)
    rows = "".join(f'<tr><td>{html.escape(t)}</td><td class="bar"><div style="width:{max(v/mx*100,1.5):.1f}%"></div></td><td class="n">{num(v)}</td></tr>' for t, v in kp)
    note = f'<p class="note">{html.escape(spec["kp_note"])}</p>' if spec.get("kp_note") else ""
    page(f'''<h2>{L["kp_h"]}</h2><p class="sub">{L["kp_sub"]}</p>
<div class="glass tbl"><table><thead><tr><th>{L["kp_col"]}</th><th></th><th class="n">{L["kp_vol"]}</th></tr></thead><tbody>{rows}</tbody></table></div>
{insights(spec.get("kp_insights", []))}{note}''')

    # 4 themes
    th = spec["themes"]; vmx = max(t[3] for t in th) or 1
    rows = "".join(
        f'<tr class="{t[5] if len(t) > 5 else "mid"}"><td>{html.escape(t[0])}</td><td class="n">{money(t[1])}</td><td class="n">{t[2]:.1f}</td>'
        f'<td class="vbar"><div style="width:{max(t[3]/vmx*66,0.6):.1f}%"></div><em>{money(t[3])}</em></td>'
        f'<td class="n roas">{(t[3]/t[1] if t[1] else 0):.1f}</td><td class="dec">{html.escape(t[4])}</td></tr>' for t in th)
    page(f'''<h2>{L["ads_h"]}</h2><p class="sub">{L["ads_sub"].format(period=html.escape(spec["period"]))}</p>
<div class="glass tbl"><table class="ads"><thead><tr><th>{L["c_theme"]}</th><th class="n">{L["c_cost"]}</th><th class="n">{L["c_conv"]}</th><th>{L["c_val"]}</th><th class="n">{L["c_roas"]}</th><th>{L["c_dec"]}</th></tr></thead><tbody>{rows}</tbody></table></div>
{insights(spec.get("ads_insights", []))}''')

    # 5 top terms + brand share + changes
    tt = spec["top_terms"]; tmx = max(t[2] for t in tt) or 1
    rows = "".join(f'<tr><td>{html.escape(t[0])}</td><td class="n">{t[1]:.1f}</td><td class="vbar wide"><div style="width:{t[2]/tmx*72:.1f}%"></div><em>{money(t[2])}</em></td></tr>' for t in tt)
    two = ""
    sh = spec.get("brand_share")
    if sh:
        tot = sh["brand_value"] + sh["generic_value"]; pb = sh["brand_value"] / tot * 100
        two += (f'<div class="glass box"><div class="eyebrow">{L["share_h"]}</div><div class="sbar"><div class="sb" style="width:{pb:.1f}%">'
                f'{L["share_brand"]} · {pb:.0f}%</div><div class="sg" style="width:{100-pb:.1f}%"></div></div>'
                f'<p><b>{money(sh["brand_value"])}</b> {L["share_b"]}<br><b>{money(sh["generic_value"])}</b> {L["share_g"]}</p>'
                f'<p class="small">{L["share_note"]}</p></div>')
    ch = spec.get("changes")
    if ch:
        li = "".join(f'<li class="p">{html.escape(x)}</li>' for x in ch.get("added", [])) + \
             "".join(f'<li class="m">{html.escape(x)}</li>' for x in ch.get("removed", []))
        two += f'<div class="glass box"><div class="eyebrow">{L["changes_h"]}</div><ul class="pm">{li}</ul></div>'
    page(f'''<h2>{L["top_h"]}</h2><p class="sub">{L["top_sub"]}</p>
<div class="glass tbl"><table class="ads"><thead><tr><th>{L["c_term"]}</th><th class="n">{L["c_convs"]}</th><th>{L["c_val"]}</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="two">{two}</div>''')

    # 6+ before / after, 2 per page
    def card(p):
        return f'''<div class="glass prod"><div class="p-head"><img src="{path(p["image"])}" alt=""><div>
<div class="eyebrow">ID {html.escape(str(p["id"]))}{f' · {L["sales"]} {money(p["sales"])}' if p.get("sales") else ""}</div><h3>{html.escape(p["name"])}</h3></div></div>
<div class="ba"><div class="lbl b">{L["before"]}</div><div class="lbl a">{L["after"]}</div>
<div class="bt old">{html.escape(p["old_title"])}<small>{len(p["old_title"])} {L["chars"]}</small></div>
<div class="bt new">{hl(p["new_title"])}<small>{len(p["new_title"])} {L["chars"]}</small></div>
<div class="bd old">{html.escape(p["old_desc"])}</div><div class="bd new">{hl(p["new_desc"])}</div></div></div>'''
    for i in range(0, len(prods), 2):
        t = f'<h2>{L["ba_h"]}</h2><p class="sub">{L["ba_sub"]}</p>' if i == 0 else ""
        page(t + "".join(card(p) for p in prods[i:i+2]), "prod-page")

    css = CSS.replace("__P__", b["primary"]).replace("__PL__", b.get("primary_light", b["primary"])) \
             .replace("__BG__", b.get("bg", "#17171b")).replace("__BG2__", b.get("bg2", "#1d1e25")) \
             .replace("__S__", b.get("secondary", "#6b748b")).replace("__PRGB__", hex_rgb(b["primary"])) \
             .replace("__SRGB__", hex_rgb(b.get("secondary", "#6b748b"))).replace("__FONT__", b.get("font", "Inter Tight"))
    font_q = b.get("font", "Inter Tight").replace(" ", "+")
    doc = (f'<!doctype html><html lang="{spec.get("lang","pl")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
           f'<title>{html.escape(spec.get("client",""))} - feed</title><link href="https://fonts.googleapis.com/css2?family={font_q}:wght@400;500;600;700&display=swap" rel="stylesheet">'
           f'<style>{css}</style></head><body>{"".join(pages)}</body></html>')
    if "—" in doc:
        sys.exit("ERROR: em dash in report text - use a hyphen (workspace rule)")
    return doc

def hex_rgb(h):
    h = h.lstrip("#"); return ",".join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))

CSS = '''
@page{size:A4;margin:0}
*{box-sizing:border-box;margin:0;padding:0}
:root{--p:__P__;--pl:__PL__;--ink:#f2f4f5;--muted:#a7abb8;--line:rgba(255,255,255,.14)}
body{font-family:"__FONT__",system-ui,sans-serif;color:var(--ink);background:__BG__;-webkit-print-color-adjust:exact;print-color-adjust:exact}
/* PDF-safe: glow comes ONLY from radial-gradient layers - no filter:blur, no box-shadow, no backdrop-filter */
.page{width:210mm;height:297mm;position:relative;overflow:hidden;padding:16mm 15mm 18mm;page-break-after:always;display:flex;flex-direction:column;gap:5mm;
 background:radial-gradient(120mm 120mm at 100% 0%,rgba(__PRGB__,.38),rgba(__PRGB__,0) 70%),radial-gradient(110mm 110mm at 0% 100%,rgba(__SRGB__,.35),rgba(__SRGB__,0) 70%),radial-gradient(70mm 70mm at 100% 70%,rgba(__PRGB__,.14),rgba(__PRGB__,0) 70%),linear-gradient(160deg,__BG2__ 0%,__BG__ 45%,__BG__ 100%)}
/* PDF-safe: one solid rgba fill (a gradient fill left a seam), only an inset 1px highlight (an outer shadow printed as a black block) */
.glass{background:rgba(255,255,255,.065);border:1px solid var(--line);border-radius:5mm;box-shadow:inset 0 1px 0 rgba(255,255,255,.18)}
.head{display:flex;justify-content:space-between;align-items:center;font-size:8.5pt;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.logo{height:7mm;max-width:60mm;object-fit:contain;object-position:left}
.logo.big{height:12mm;align-self:flex-start;margin-bottom:8mm}
.foot{position:absolute;left:15mm;right:15mm;bottom:8mm;display:flex;justify-content:space-between;font-size:7.5pt;color:var(--muted)}
h1{font-size:30pt;line-height:1.08;font-weight:700;letter-spacing:-.02em}
h2{font-size:20pt;font-weight:700;letter-spacing:-.015em;margin-top:2mm}
h3{font-size:12pt;font-weight:650}
.sub{color:var(--muted);font-size:9.5pt;line-height:1.45;margin-top:-2mm}
.accent{color:var(--pl)} .warn{color:#ffb020}
.eyebrow{font-size:7.5pt;letter-spacing:.12em;text-transform:uppercase;color:var(--pl);font-weight:600}
mark{background:rgba(__PRGB__,.22);color:#fff;border-bottom:1.5px solid var(--p);padding:0 .5mm;border-radius:1mm}
.cover-in{display:flex;flex-direction:column;gap:7mm;margin-top:30mm}
.lead{font-size:12pt;line-height:1.5;color:#d6d8df;max-width:160mm}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:4mm;margin-top:6mm}
.kpi{padding:6mm}.kpi b{display:block;font-size:20pt;font-weight:700}.kpi span{font-size:9pt;color:var(--muted);line-height:1.35}
.period{font-size:8pt;color:var(--muted);margin-top:4mm}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm}
.step{padding:5mm}.step p{font-size:9pt;line-height:1.5;color:#d0d3db}.step b{color:#fff}.step h3{margin-bottom:2mm}
.step i{display:inline-flex;width:8mm;height:8mm;border-radius:50%;background:var(--p);color:#fff;font-style:normal;font-weight:700;align-items:center;justify-content:center;font-size:10pt;margin-bottom:3mm}
.formula{padding:6mm;display:flex;flex-direction:column;gap:4mm}
.f-row{display:flex;align-items:center;gap:2.5mm;flex-wrap:wrap}
.chip{padding:2.5mm 4mm;border-radius:99px;border:1px solid var(--line);background:rgba(255,255,255,.06);font-size:9pt;font-weight:600}
.chip.main{background:rgba(__PRGB__,.25);border-color:rgba(__PRGB__,.6)}
.plus{color:var(--muted);font-weight:700}
.ex{font-size:10.5pt;line-height:1.6;padding:4mm;border-radius:3mm;background:rgba(0,0,0,.25)}
.rules{padding-left:5mm;font-size:9pt;line-height:1.55;color:#d0d3db;display:flex;flex-direction:column;gap:1.5mm}
.tbl{padding:3mm 5mm}
table{width:100%;border-collapse:collapse;font-size:9pt}
th{font-size:7.5pt;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);text-align:left;padding:2mm 1.5mm;font-weight:600;border-bottom:1px solid var(--line)}
td{padding:1.9mm 1.5mm;border-bottom:1px solid rgba(255,255,255,.06)}
tr:last-child td{border-bottom:none}
.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
td.bar{width:42%} td.bar div,td.vbar div{height:3mm;border-radius:2mm;background:linear-gradient(90deg,var(--p),var(--pl))}
td.vbar{width:34%;white-space:nowrap} td.vbar.wide{width:48%}
td.vbar div{display:inline-block;vertical-align:middle;height:3.6mm}
td.vbar em{display:inline-block;vertical-align:middle;margin-left:2mm;font-style:normal;font-size:8pt;font-weight:600;color:#fff}
table.ads td{font-size:8.5pt}
tr.up .roas{color:var(--pl);font-weight:700}
tr.down td.vbar div{background:linear-gradient(90deg,#b45309,#ffb020)} tr.down .roas,tr.down .dec{color:#ffb020;font-weight:700}
td.dec{font-size:8pt;color:#d0d3db}
.insights{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm}
.ins{padding:4.5mm}.ins b{display:block;font-size:17pt;font-weight:700;margin-bottom:1.5mm}.ins span{font-size:8.5pt;line-height:1.45;color:#d0d3db}
.note{font-size:8.5pt;line-height:1.5;color:var(--muted);border-left:2px solid var(--p);padding-left:3mm}
.two{display:grid;grid-template-columns:1fr 1fr;gap:4mm}
.box{padding:5mm;display:flex;flex-direction:column;gap:3mm;font-size:9pt;line-height:1.5}
.sbar{display:flex;height:7mm;border-radius:2mm;overflow:hidden;font-size:7.5pt;font-weight:600}
.sb{background:var(--muted);color:#17171b;display:flex;align-items:center;padding-left:2.5mm}.sg{background:var(--p)}
.small{font-size:8.5pt;color:#d0d3db}
.pm{list-style:none;display:flex;flex-direction:column;gap:2mm;font-size:8.8pt}
.pm li{padding-left:6mm;position:relative;line-height:1.4}.pm li::before{position:absolute;left:0;font-weight:700}
.pm .p::before{content:"+";color:#4ade80}.pm .m::before{content:"-";color:#ffb020}
.prod-page{gap:3.5mm;padding-top:13mm}
.prod{padding:4mm 5mm;display:flex;flex-direction:column;gap:2.5mm}
.p-head{display:flex;align-items:center;gap:4mm}
/* light tile so dark product photos don't vanish on the dark page; no drop-shadow (filters break in PDF) */
.p-head img{width:30mm;height:21mm;object-fit:contain;padding:1.5mm;border-radius:3mm;background:radial-gradient(circle at 50% 40%,#ffffff,#d9dce3)}
.ba{display:grid;grid-template-columns:1fr 1.45fr;gap:2mm 4mm}
.lbl{font-size:7pt;font-weight:700;letter-spacing:.12em;text-transform:uppercase}.lbl.b{color:var(--muted)}.lbl.a{color:var(--pl)}
.bt{font-size:9pt;line-height:1.45;padding:2.5mm 3mm;border-radius:2.5mm}
.bt small{display:block;font-size:7pt;color:var(--muted);margin-top:1mm}
.bt.old{background:rgba(255,255,255,.04);color:#b9bcc6}
.bt.new{background:rgba(__PRGB__,.10);border:1px solid rgba(__PRGB__,.35);font-weight:600}
.bd{font-size:7.4pt;line-height:1.45;padding:2.5mm 3mm;border-radius:2.5mm}
.bd.old{background:rgba(255,255,255,.04);color:#9ea2ad;font-style:italic}.bd.new{background:rgba(255,255,255,.06);color:#e3e5ea}
'''

SWIFT_QA = r'''
import PDFKit
import AppKit
let doc = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1]))!
let out = CommandLine.arguments[2]
for n in 0..<doc.pageCount {
  let img = doc.page(at: n)!.thumbnail(of: NSSize(width: 700, height: 990), for: .mediaBox)
  let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
  try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(out)/page\(n+1).png"))
}
print(doc.pageCount)
'''

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec"); ap.add_argument("--out"); ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.spec))
    spec = json.load(open(a.spec, encoding="utf-8"))
    out = a.out or os.path.join(base, f'{spec.get("client","client")} - feed.pdf')
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
        if r.returncode == 0:
            print(f"QA: {r.stdout.strip()} real PDF pages rendered to {qa}/pageN.png - review them (sips -Z 800) before calling it done")
        else:
            print("QA render failed (swift/PDFKit):", r.stderr[-300:])

if __name__ == "__main__":
    main()
