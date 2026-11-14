#!/usr/bin/env python3
"""
cro_report_pdf.py - client-facing PDF for /55-cro-audit.

Purpose
    Turns a COMPLETE cro_audit results.json into the same dark-glass PDF the
    /55-feed-title-optimizer and /55-merchant-policy-check reports use. It does not render anything
    itself: it builds a spec for scripts/policy_report_pdf.py (which imports feed_report_pdf.py's
    CSS + real-PDF QA) with CRO wording in `labels`, then runs it. Client's own brand, no agency
    branding, no em dashes.

    Completeness gate: refuses to build if any selected check is TODO / missing evidence, so the
    PDF can never be a silently shortened audit. Every check appears: FAIL and PARTIAL as cards
    (PARTIAL shown as "Warning"), MANUAL as cards titled "Needs a manual check", PASS and N/A in
    the compact table (N/A rows are prefixed "N/A:" so they are never mistaken for a pass).

Usage
    .venv/bin/python scripts/cro_report_pdf.py <results.json> --brand <brand.json> [--lang en|uk|pl] [--out file.pdf]
    brand.json: {"brand": {primary, primary_light, bg, bg2, secondary, font, heading_font, logo, on_primary},
                 "client": "Name", "date_label": "28 October 2026", "scope": "one line"}
    Fill the finding texts in the client's language by editing results.json evidence/fix BEFORE
    running (plain words, link every page as <a href="...">). Same brand-extraction steps as
    /55-merchant-policy-check Step 4.

Changelog
    2026-10-28  Initial version.
    2026-10-28  Page 2 (right after the cover) = GA4 sales funnel (bars + step-to-step %) when clients/<slug>/reports/cro_audit_DATE/ga4_funnel.json
                exists (written by `cro_audit.py funnel <slug>`); skipped silently otherwise.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cro_audit import load, SECTIONS, PRIO, check_results  # noqa: E402

LABELS = {
    "en": dict(head="Website conversion audit", eyebrow="Conversion rate optimization audit",
               h1_a="Conversion audit", h1_b="of your website", h1_c="check by check",
               lead="We went through every conversion check for the pages in scope - what already works, what is weak and what is missing - and listed concrete fixes, most important first.",
               k_fail="missing or broken - fix first", k_warn="partial or need a manual check", k_pass="passed or not applicable",
               k_acc="Checks in scope", method_sub="Real browser capture of each page on desktop and mobile, then a check-by-check review.",
               src_h="Pages reviewed", fail="Missing", warn="Weak", pass_="Good",
               legend_fail="The element is missing or broken. This directly costs conversions.",
               legend_warn="Present but incomplete, or it cannot be verified from outside the site and needs a manual check.",
               legend_pass="Implemented properly (or not applicable to this business).",
               fail_h="Fix first", fail_sub="Missing or broken - highest impact on conversions.",
               warn_h="Improve next", warn_sub="Partly implemented, or needs a check on your side.",
               pass_h="Already working", pass_sub="Checked and implemented properly. N/A rows do not apply to this business.",
               found="What we found", fix="What to do", cont="(continued)"),
    "uk": dict(head="Аудит конверсії сайту", eyebrow="Аудит оптимізації конверсії",
               h1_a="Аудит конверсії", h1_b="вашого сайту", h1_c="пункт за пунктом",
               lead="Ми пройшли по кожній перевірці конверсії для сторінок в обсязі аудиту: що вже працює, що слабке, чого немає - і записали конкретні виправлення, найважливіші першими.",
               k_fail="відсутнє або зламане - виправити першим", k_warn="часткове або потребує ручної перевірки", k_pass="пройдено або не застосовується",
               k_acc="Перевірок в аудиті", method_sub="Реальний знімок кожної сторінки на десктопі й мобільному, потім перевірка пункт за пунктом.",
               src_h="Які сторінки перевірили", fail="Відсутнє", warn="Слабко", pass_="Добре",
               legend_fail="Елемента немає або він зламаний. Це напряму коштує конверсій.",
               legend_warn="Є, але не повністю, або це неможливо перевірити ззовні - потрібна ручна перевірка.",
               legend_pass="Реалізовано правильно (або не стосується цього бізнесу).",
               fail_h="Виправити першим", fail_sub="Відсутнє або зламане - найбільший вплив на конверсії.",
               warn_h="Покращити далі", warn_sub="Реалізовано частково або потрібна перевірка з вашого боку.",
               pass_h="Вже працює", pass_sub="Перевірено й реалізовано правильно. Рядки N/A не стосуються цього бізнесу.",
               found="Що знайшли", fix="Що зробити", cont="(продовження)"),
    "pl": dict(head="Audyt konwersji strony", eyebrow="Audyt optymalizacji konwersji",
               h1_a="Audyt konwersji", h1_b="Twojej strony", h1_c="punkt po punkcie",
               lead="Przeszliśmy przez każde sprawdzenie konwersji dla stron objętych audytem: co już działa, co jest słabe i czego brakuje - i spisaliśmy konkretne poprawki, najważniejsze najpierw.",
               k_fail="brak lub błąd - poprawić najpierw", k_warn="częściowe lub do sprawdzenia ręcznie", k_pass="zaliczone lub nie dotyczy",
               k_acc="Sprawdzeń w audycie", method_sub="Zrzuty każdej strony w prawdziwej przeglądarce (komputer i telefon), potem sprawdzenie punkt po punkcie.",
               src_h="Sprawdzone strony", fail="Brak", warn="Słabo", pass_="Dobrze",
               legend_fail="Elementu brakuje albo nie działa. To bezpośrednio kosztuje konwersje.",
               legend_warn="Jest, ale niepełny, albo nie da się tego sprawdzić z zewnątrz i trzeba sprawdzić ręcznie.",
               legend_pass="Wdrożone poprawnie (lub nie dotyczy tego biznesu).",
               fail_h="Popraw najpierw", fail_sub="Brak lub błąd - największy wpływ na konwersje.",
               warn_h="Popraw w drugiej kolejności", warn_sub="Wdrożone częściowo albo wymaga sprawdzenia po Waszej stronie.",
               pass_h="Już działa", pass_sub="Sprawdzone i wdrożone poprawnie. Wiersze N/A nie dotyczą tego biznesu.",
               found="Co znaleźliśmy", fix="Co zrobić", cont="(ciąg dalszy)"),
}
FUN = {
    "en": dict(title="Your sales funnel, start to end", sub="How many visitors reach each step, and how many move on to the next one (Google Analytics, {a} to {b}).",
               stages={"Session start": "Visit the site", "View product": "View a product", "Add to cart": "Add to cart",
                       "Begin checkout": "Start checkout", "Purchase": "Purchase"},
               next="{p}% continue to the next step, {l} drop off", gap="more people reach \"{b}\" than \"{a}\" - a tracking gap to fix", trans="{a} to {b}",
               ov="of visitors end up buying", note1="Counts are people (users) in an open funnel: a person can enter at any step, so a step can be larger than the one before it.",
               bench="Typical", ours="Yours", v_improve="Improve", v_ok="On par", v_good="Above typical", v_gap="Fix tracking",
               sum_h="What this means", sum_improve="Biggest gap: {stage}. Only {p}% move on, against a typical {b} for online stores. This is where most sales are lost, so it is the first area to fix - see the checks below.",
               sum_ok="Every step with a benchmark is within or above the typical range. Focus on the weakest transition shown above.",
               sum_gap=" Also, the tracking around '{stage}' is incomplete (see the warning above), so fix the measurement before trusting that rate.",
               bnote="Typical ranges are rough, general online-store figures, shown as a guide, not a guarantee.",
               note2="The biggest drop is the step to fix first; the audit below lists what to change on that page."),
    "uk": dict(title="Ваша воронка продажів від початку до кінця", sub="Скільки відвідувачів доходить до кожного кроку і скільки переходить на наступний (Google Analytics, {a} - {b}).",
               stages={"Session start": "Зайшли на сайт", "View product": "Переглянули товар", "Add to cart": "Додали в кошик",
                       "Begin checkout": "Почали оформлення", "Purchase": "Купили"},
               next="{p}% переходять на наступний крок, {l} відпадають", gap="на кроці «{b}» людей більше, ніж на «{a}» - помилка відстеження, яку треба виправити", trans="від «{a}» до «{b}»",
               ov="відвідувачів зрештою купують", note1="Це кількість людей (users) у відкритій воронці: людина може зайти на будь-якому кроці, тому крок може бути більшим за попередній.",
               bench="Типово", ours="Ваш", v_improve="Покращити", v_ok="У нормі", v_good="Вище норми", v_gap="Виправити відстеження",
               sum_h="Що це означає", sum_improve="Найбільший розрив: {stage}. Далі йдуть лише {p}% проти типових {b} для інтернет-магазинів. Саме тут втрачається найбільше продажів, тому це перша зона для виправлення - див. перевірки нижче.",
               sum_ok="Усі кроки з еталоном у межах або вище типового діапазону. Працюємо зі слабшим переходом, показаним вище.",
               sum_gap=" Також відстеження навколо кроку «{stage}» неповне (див. попередження вище), тож спершу виправляємо вимірювання, а вже потім довіряємо цьому показнику.",
               bnote="Типові діапазони - це приблизні загальні цифри для інтернет-магазинів, орієнтир, а не гарантія.",
               note2="Найбільше падіння - це крок, який виправляємо першим; що змінити на цій сторінці, описано в аудиті нижче."),
    "pl": dict(title="Twój lejek sprzedaży od początku do końca", sub="Ilu odwiedzających dociera do każdego kroku i ilu przechodzi dalej (Google Analytics, {a} - {b}).",
               stages={"Session start": "Wejście na stronę", "View product": "Wyświetlenie produktu", "Add to cart": "Dodanie do koszyka",
                       "Begin checkout": "Rozpoczęcie zamówienia", "Purchase": "Zakup"},
               next="{p}% przechodzi do kolejnego kroku, {l} odpada", gap="na kroku „{b}” jest więcej osób niż na „{a}” - błąd pomiaru do poprawy", trans="od „{a}” do „{b}”",
               ov="odwiedzających kończy zakupem", note1="To liczba osób (users) w otwartym lejku: ktoś może wejść na dowolnym kroku, więc krok może być większy niż poprzedni.",
               bench="Typowo", ours="Twój", v_improve="Do poprawy", v_ok="W normie", v_good="Powyżej normy", v_gap="Popraw pomiar",
               sum_h="Co to oznacza", sum_improve="Największa luka: {stage}. Dalej przechodzi tylko {p}%, przy typowych {b} w sklepach internetowych. Tu ucieka najwięcej sprzedaży, więc to pierwszy obszar do poprawy - zobacz sprawdzenia poniżej.",
               sum_ok="Każdy krok z punktem odniesienia mieści się w typowym zakresie lub go przekracza. Skupiamy się na najsłabszym przejściu pokazanym wyżej.",
               sum_gap=" Ponadto pomiar wokół kroku „{stage}” jest niepełny (patrz ostrzeżenie wyżej), więc najpierw popraw pomiar, zanim zaufasz temu wskaźnikowi.",
               bnote="Typowe zakresy to orientacyjne, ogólne dane dla sklepów internetowych, wskazówka, nie gwarancja.",
               note2="Największy spadek to krok do poprawy w pierwszej kolejności; co zmienić na tej stronie, opisuje audyt poniżej."),
}
NA_PREFIX = {"en": "N/A: ", "uk": "Не стосується: ", "pl": "Nie dotyczy: "}
MANUAL_PREFIX = {"en": "Needs a manual check: ", "uk": "Потрібна ручна перевірка: ", "pl": "Do sprawdzenia ręcznie: "}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results"); ap.add_argument("--brand", required=True)
    ap.add_argument("--lang", default="auto", choices=["auto"] + list(LABELS), help="auto = the language the business runs in (site <html lang>, else country)"); ap.add_argument("--out")
    ap.add_argument("--texts", help="client-language overlay JSON: {sections:{code:name}, groups:{en:local}, prio:{High:..}, items:{ID:{title,evidence,fix}}, sources:[..]}")
    ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()

    items, d, problems, counts = check_results(a.results, quiet=True)
    if a.lang == "auto":
        from cro_audit import detect_language
        a.lang, why = detect_language(d["client"])
        print(f"Report language: {a.lang} ({why})")
    if problems:
        sys.exit(f"REFUSING to build PDF: {len(problems)} check(s) incomplete (run `cro_audit.py validate`). "
                 "The PDF must cover every selected check.")
    b = json.load(open(a.brand, encoding="utf-8"))
    out_dir = os.path.join(os.path.dirname(os.path.abspath(a.results)), "cro_pdf")
    os.makedirs(out_dir, exist_ok=True)

    T = json.load(open(a.texts, encoding="utf-8")) if a.texts else {}
    sec_name = lambda c: T.get("sections", {}).get(c, SECTIONS[c])
    findings = []
    for cid, it in items.items():
        r = d["items"].get(cid)
        if not r:
            continue
        tx = T.get("items", {}).get(cid, {})
        if T and not tx:
            sys.exit(f"REFUSING to build PDF: no translation for {cid} in {a.texts}")
        grp = T.get("groups", {}).get(it["group"], it["group"])
        area = f"{sec_name(it['section'])} / {grp}"
        prio = T.get("prio", {}).get(PRIO[it["priority"]], PRIO[it["priority"]])
        title = f"{tx.get('title', it['text'])} [{cid}, {prio}]"
        ev, fx = tx.get("evidence", r["evidence"]), tx.get("fix", r.get("fix") or "")
        st = r["status"]
        row = None
        if st == "FAIL":
            row = dict(status="FAIL", area=area, title=title, found=ev, fix=fx)
        elif st == "PARTIAL":
            row = dict(status="WARN", area=area, title=title, found=ev, fix=fx)
        elif st == "MANUAL":
            row = dict(status="WARN", area=area, title=MANUAL_PREFIX[a.lang] + title, found=ev, fix=fx)
        elif st == "N/A":
            row = dict(status="PASS", area=area, title=NA_PREFIX[a.lang] + title, found=ev)
        else:
            row = dict(status="PASS", area=area, title=title, found=ev)
        row["_p"] = {"High": 0, "Medium": 1, "Low": 2}.get(PRIO[it["priority"]], 3)
        findings.append(row)
    # inside each status, High priority first (policy_report_pdf keeps list order within a status)
    findings.sort(key=lambda f: f["_p"])

    funnel = None   # page 2 (after the cover): GA4 sales funnel, if `cro_audit.py funnel <slug>` was run for this audit
    fpath = os.path.join(os.path.splitext(os.path.abspath(a.results))[0], "ga4_funnel.json")
    from client_registry import resolve
    try:
        is_ecom = resolve(d["client"]).get("business_type") == "ecommerce"
    except KeyError:   # client not in clients.json: the funnel file's presence is the signal
        is_ecom = True
    if os.path.exists(fpath) and is_ecom:   # ecommerce clients only
        from cro_audit import funnel_stats
        fd = json.load(open(fpath, encoding="utf-8")); fr = funnel_stats(fd); F = FUN[a.lang]
        top = fr[0]["users"] or 1
        from cro_audit import bench_text
        stages, worst = [], None
        for i, s in enumerate(fr):
            nxt = fr[i + 1] if i + 1 < len(fr) else None
            st = dict(name=F["stages"].get(s["name"], s["name"]), users=f"{s['users']:,}", w=max(2, min(100, round(100 * s["users"] / top))))
            if nxt:
                if nxt["users"] > s["users"]:
                    st["next"], st["gap"] = F["gap"].format(a=st["name"], b=F["stages"].get(nxt["name"], nxt["name"])), True
                else:
                    st["next"] = F["next"].format(p=f"{100 * nxt['users'] / s['users']:.1f}" if s["users"] else "0", l=f"{s['users'] - nxt['users']:,}")
                v = nxt["verdict"]
                if v:
                    st["bench"] = f"{F['bench']} {bench_text(nxt['bench'])}"
                    st["ours"] = f"{F['ours']} {nxt['pct_prev'] * 100:.1f}%"
                    st["pill"] = {"improve": "FAIL", "ok": "PASS", "good": "PASS", "gap": "WARN"}[v]
                    st["pill_text"] = F["v_" + v]
                    if v == "improve":
                        gap_pts = nxt["bench"][0] - nxt["pct_prev"]
                        if worst is None or gap_pts > worst[0]:
                            worst = (gap_pts, nxt)
            stages.append(st)
        gaps = [F["stages"].get(x["name"], x["name"]) for x in fr if x["verdict"] == "gap"]
        if worst:
            w = worst[1]
            wi = fr.index(w)
            summ = F["sum_improve"].format(stage=F["trans"].format(a=F["stages"].get(fr[wi - 1]["name"], fr[wi - 1]["name"]), b=F["stages"].get(w["name"], w["name"])), p=f"{w['pct_prev'] * 100:.1f}", b=bench_text(w["bench"]))
        else:
            summ = F["sum_ok"]
        if gaps:
            summ += F["sum_gap"].format(stage=gaps[0])
        funnel = dict(title=F["title"], sub=F["sub"].format(a=fd["date_from"], b=fd["date_to"]), stages=stages,
                      overall_value=f"{fr[-1]['pct_first'] * 100:.1f}%", overall_label=F["ov"],
                      summary_h=F["sum_h"], summary=summ, notes=[F["bnote"], F["note1"]])

    pages = d.get("pages") or {}
    spec = dict(funnel=funnel,client=b.get("client", d["client"]), lang=a.lang, date_label=b.get("date_label", d["date"]),
                brand=b["brand"], scope=b.get("scope", ""),
                account_status=dict(label=str(len(findings)), text=", ".join(sec_name(c) for c in d["sections"])),
                method=b.get("method") or [
                    ["Capture", "Each page opened in a real browser on desktop and mobile; load time, forms, banners and pop-ups recorded."],
                    ["Check by check", "Every item of the conversion checklist judged against what is really on the page."],
                    ["Fix list", "Missing items first, high-impact first, each with a concrete action."]],
                sources=T.get("sources") or [f"{k}: {v}" for k, v in pages.items()] or ["See audit report"],
                labels=LABELS[a.lang], pack_scale={"uk": 0.70}.get(a.lang, 0.82), findings=findings)
    spec_path = os.path.join(out_dir, "report_spec.json")
    json.dump(spec, open(spec_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = a.out or os.path.join(out_dir, f"{spec['client']} - CRO audit.pdf")
    cmd = [sys.executable, os.path.join(HERE, "policy_report_pdf.py"), spec_path, "--out", out]
    if a.no_qa:
        cmd.append("--no-qa")
    print(f"{len(findings)} checks in PDF (results had {sum(counts.values())}).")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
