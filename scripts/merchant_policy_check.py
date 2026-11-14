#!/usr/bin/env python3
"""
55DigitalAI - Merchant Center Policy & Website Alignment Check
=================================================================
Purpose  : Read-only "misrepresentation pre-flight". Checks whether a client's
           Merchant Center settings and their live website line up with each
           other and with Google's Shopping policies - the same things a
           Google reviewer checks before lifting (or imposing) a
           Misrepresentation suspension:

             1. Account status   - account-level issues (suspensions/warnings),
                                   website claimed, product status totals.
             2. Business identity - MC business info (address / phone / email /
                                   customer-service URL) found on the website?
             3. Required pages   - contact, about, privacy, terms, shipping,
                                   returns: linked from the homepage, live,
                                   not empty, no placeholder text.
             4. Policy match     - MC shipping (handling/transit days, cost) and
                                   MC return policy (type, days, URL, fees) vs
                                   what the website's own policy pages say.
             5. Technical/trust  - HTTPS, claimed domain = site domain, free-mail
                                   support address, placeholder strings.
             6. Feed vs site     - sampled products: landing page live and on the
                                   claimed domain, price + availability on page
                                   match the feed; feed size vs site sitemap.

           Every check prints PASS / WARN / FAIL with the concrete evidence.
           Semantic judgement (does the returns page actually *say* what MC
           says?) still needs a human/Claude read - the script saves each
           policy page's extracted text next to the log for exactly that.

Sources  : Google Misrepresentation policy (support.google.com/merchants/answer/6150127),
           Merchant Center website requirements (answer/6363310), Building trust
           with your customers (answer/13693865), third-party Merchant Center approval checklists and misrepresentation-recovery walkthroughs (2025).

Setup    : Uses the same OAuth refresh token as everything else (google-ads.yaml,
           `content` scope already granted). Client must have `domain` in
           clients.json; `merchant_center_id` is optional - without it only
           the website-side checks (3, 5) run.

Usage    : python3 scripts/merchant_policy_check.py <client_slug> [--sample 10] [--seed 1]
           Writes clients/<slug>/reports/policy_check_YYYY-MM-DD.log (+ .json, results
           ordered FAIL -> WARN -> PASS, input for scripts/policy_report_pdf.py) and
           clients/<slug>/reports/policy_check_YYYY-MM-DD/<page>.txt

Makes changes: Never - read-only (Content API GETs + public website fetches).

Changelog: 2026-10-15  Initial version - built from Google's policy pages + the
                       checklists above, tested live on a client account that was
                       under a Misrepresentation suspension at the time.
           2026-10-15  Summary + JSON always ordered FAIL, WARN, PASS; JSON output
                       feeds the client PDF (scripts/policy_report_pdf.py).
           2026-10-24  ~35 new checks from three misrepresentation-fix videos and the
                       a third-party "GMC compliance guide 2026": FAQ / track-order
                       pages, policy links on every page + product pages, header menu,
                       footer business details as text + payment methods, hours/response
                       time, separate shipping/returns pages, tracking/business days/no-ship
                       zones/customs, return routes/refund timing+method/who pays/problem
                       scenarios/cancellation, unfair liability disclaimers, terms + privacy
                       content, generic-AI About text, ChatGPT residue, free-shipping claim
                       consistency, sold-out share, feed promo titles/thin descriptions/
                       deep discounts/sale dates/condition, product-page reviews, active
                       feed, disapprovals. All heuristics are WARN (read before reporting).
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[1]
CONTENT_API = "https://shoppingcontent.googleapis.com/content/v2.1"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

# Page-type detection: keywords matched against link text AND url path, in the
# languages our clients use (uk / ru / pl / en / de). Order matters - first hit wins.
PAGE_TYPES = {
    "privacy":  ["privacy", "konfidents", "конфіденц", "конфиденц", "prywatno", "datenschutz",
                 "персональн", "cookie"],
    "returns":  ["return", "refund", "povernen", "повернен", "возврат", "обмін", "obmin",
                 "zwrot", "reklamac", "widerruf", "rückgabe"],
    "shipping": ["shipping", "delivery", "dostav", "доставк", "oplata", "оплата", "wysyłk",
                 "wysylk", "dostaw", "versand", "lieferung"],
    "terms":    ["terms", "oferty", "оферт", "regulamin", "agb", "umov", "умови", "условия",
                 "conditions"],
    "contact":  ["contact", "kontakt", "контакт"],
    "about":    ["about", "pro-nas", "про нас", "о нас", "o nas", "über uns", "uber-uns", "o-nas"],
    # recommended, not required (videos + compliance guide 2026-10-24): reviewers look for them in the menus
    "faq":      ["faq", "часті питання", "поширені питання", "частые вопросы", "pytania", "häufige fragen", "fragen"],
    "track":    ["track", "відстеж", "отслеж", "śledzenie", "sledzenie", "sendungsverfolgung"],
}
REQUIRED_PAGES = ["contact", "privacy", "returns", "shipping", "terms"]   # "about" = recommended
RECOMMENDED_PAGES = ["about", "faq", "track"]

PLACEHOLDERS = [r"lorem ipsum", r"\{\$[A-Za-z_]+\}", r"_{6,}", r"\{\{\s*[a-z_]+\s*\}\}", r"under construction",
                r"coming soon", r"example\.com", r"sample page", r"hello world!",
                r"\[your (?:company|store|business)[^\]]*\]", r"YOUR_[A-Z_]+"]
FREE_MAIL = ("gmail.", "ukr.net", "i.ua", "yahoo.", "hotmail.", "outlook.", "wp.pl", "o2.pl",
             "onet.pl", "interia.pl", "gmx.", "mail.ru", "icloud.")

# Domains that legitimately appear in policy text (carriers, payment, social, gov).
NEUTRAL_DOMAINS = ("google.", "facebook.", "instagram.", "youtube.", "tiktok.", "t.me", "telegram.",
                   "novaposhta.", "nova-poshta", "ukrposhta.", "meest", "justin.", "liqpay.", "wayforpay.",
                   "monobank.", "privatbank.", "fondy.", "stripe.", "paypal.", "inpost.", "dpd.", "dhl.",
                   "gov.", "zakon.rada", "uodo.gov", "w3.org", "schema.org", "wordpress.", "woocommerce.")

CARRIERS = ("нова пошта", "новою поштою", "нової пошти", "nova poshta", "укрпошт", "ukrposhta", "meest", "міст експрес",
            "justin", "inpost", "paczkomat", "dpd", "dhl", "ups", "fedex", "gls", "poczta polska", "orlen paczka",
            "hermes", "kurier", "courier", "кур'єр", "курʼєр", "кур’єр", "таксі", "самовивіз", "pickup", "odbiór osobisty")
DESTINATIONS = ("україн", "ukrain", "polsk", "poland", "deutschland", "germany", "europe", "європ", "worldwide",
                "за кордон", "international", "по місту", "по всій", "cały kraj", "całej polsce", "eu ")
URGENCY = (r"countdown", r"data-timer", r"залишилось (?:лише|всього)\s*\d+", r"лише\s*\d+\s*шт",
           r"only\s*\d+\s*left", r"zostało tylko", r"tylko\s*\d+\s*szt", r"nur noch\s*\d+", r"осталось\s*\d+",
           r"hurry", r"поспішайте", r"pośpiesz", r"\d+\s*(?:people|осіб|людей)\s*(?:are viewing|переглядають)")
FAKE_BADGES = (r"mcafee", r"norton\s*secured", r"trustedsite", r"guaranteed safe checkout", r"100%\s*secure checkout",
               r"verified\s*store", r"trust[-_ ]?badge")

# ---- content keyword groups (2026-10-24, from practitioner misrepresentation walkthroughs and a GMC compliance guide).
# Stems, matched case-insensitively as substrings of the page text. A miss is a WARN to read, never a FAIL.
TRACKING = ("ттн", "трек", "track", "відстеж", "отслеж", "номер відправлення", "номер накладн", "numer przesyłki",
            "śledz", "sledz", "sendungsnummer", "sendungsverfolgung")
CANCEL = ("скасув", "відмін", "отмен", "cancel", "anulow", "rezygn", "storn", "widerruf")
BUSINESS_DAYS = ("робоч", "рабоч", "business day", "working day", "dni robocz", "dzień robocz", "werktag", "arbeitstag")
NO_SHIP = ("не доставляє", "не доставляем", "не здійснюємо доставк", "не осуществляем доставк", "тимчасово окупован",
           "лише по україн", "тільки по україн", "только по украин", "do not ship", "don't ship", "only within",
           "only ship to", "nie wysyłamy", "tylko na terenie", "wyłącznie na terenie", "keine lieferung", "nur innerhalb")
CUSTOMS = ("мит", "пошлин", "customs", "import tax", "duties", "cło", "cła", "zoll", "einfuhr")
INTERNATIONAL = ("international", "worldwide", "за кордон", "міжнарод", "международ", "zagranic", "ausland", "europe", "європ")
RETURN_SHIP_PAYER = ("за рахунок", "за счет", "за счёт", "оплачує", "оплачивает", "return shipping", "koszt odesłania",
                     "koszt zwrotu", "koszty zwrotu", "koszt przesyłki zwrotnej", "rücksendekosten", "kosten der rücksendung",
                     "free return", "безкоштовне повернення", "darmowy zwrot")
REFUND_WORDS = ("кошт", "грош", "денег", "деньги", "refund", "money", "zwrot pieniędzy", "zwrot środków", "środk",
                "erstatt", "rückzahl")
REFUND_METHOD = ("той самий спосіб", "тим самим способом", "тем же способом", "на картк", "на карту", "на рахунок",
                 "на счет", "original payment", "same payment method", "store credit", "tą samą metodą", "na konto",
                 "na rachunek", "zahlungsmethode", "zahlungsmittel", "gutschrift")
RETURN_SCENARIOS = {
    "damaged": ("пошкодж", "поврежд", "брак", "дефект", "damaged", "defect", "uszkodz", "wadliw", "beschädig", "mangel"),
    "wrong item": ("не той товар", "не тот товар", "невідповідн", "несоответств", "wrong item", "incorrect item",
                   "pomyłk", "niezgodn", "falsche", "falscher artikel"),
    "not arrived / lost": ("не отрим", "не дійш", "втрач", "не получ", "утер", "lost", "not arrive", "never arrived",
                           "nie dotar", "zaginię", "nicht angekommen", "verloren"),
    "incomplete": ("некомплект", "неповн", "не всі товари", "incomplete", "missing item", "niekompletn", "brakując",
                   "unvollständig"),
}
# "we are not responsible once it's with the courier" - shifts delivery risk to the shopper, which consumer law
# doesn't allow and a reviewer reads as dishonest terms (live example in the Sunder Avenue audit video).
UNFAIR_LIABILITY = (r"не несе(?:мо)? (?:жодної )?відповідальн\w* за (?:втрат|пошкодж|доставк|дії перевізник|роботу перевізник|затримк)",
                    r"не несет\w* (?:никакой )?ответственн\w* за (?:утер|потер|поврежд|доставк|действия перевозчик|задержк)",
                    r"not (?:be )?(?:held )?responsible for (?:any )?(?:lost|stolen|damaged|delayed|packages|parcels|shipping|carrier)",
                    r"nie ponosi\w* odpowiedzialności za (?:zagubi|uszkodz|opóźni|działania przewoźnik|przesyłk)",
                    r"(?:keine|übernehmen keine) haftung für (?:verlor|verlust|beschädig|verzöger|versand)")
PRIVACY_GROUPS = {
    "what data is collected": ("email", "e-mail", "телефон", "phone", "telefon", "ім'я", "імʼя", "имя", "imię", "name",
                               "ip", "cookie"),
    "why (purpose)": ("мета", "метою", "цел", "purpose", "w celu", "cel ", "zweck"),
    "who it is shared with": ("третім особам", "третіх осіб", "третьим лицам", "третьих лиц", "third part", "podmiot",
                              "odbiorc", "dritte", "partner"),
    "how long it is kept": ("строк", "термін зберігання", "зберіга", "хран", "retention", "retain", "przechowyw",
                            "speicherdauer", "aufbewahr"),
    "how to delete / opt out": ("видален", "видалит", "удален", "delete", "deletion", "erase", "opt out", "opt-out",
                                "usunię", "usunąć", "sprzeciw", "löschung", "widerspruch"),
    "ads / analytics use": ("google analytics", "реклам", "advertis", "reklam", "werbung", "pixel", "remarketing",
                            "ремаркет", "analytics", "аналітик", "аналитик"),
}
PRIVACY_LAW = {"UA": ("захист персональних даних", "2297", "про захист персональних", "gdpr"),
               "PL": ("rodo", "gdpr", "2016/679"), "DE": ("dsgvo", "gdpr", "2016/679")}
PRIVACY_LAW_EU = ("gdpr", "2016/679", "rodo", "dsgvo", "rgpd")
TERMS_GROUPS = {
    "acceptance by using the site / ordering": ("акцепт", "приймає", "прийняття", "приним", "accept", "akcept", "akzept",
                                                 "zgadza", "agree"),
    "intellectual property": ("інтелектуальн", "интеллектуальн", "авторськ", "авторск", "intellectual property",
                              "copyright", "własności intelektualnej", "praw autorskich", "prawa autorskie", "urheberrecht"),
    "termination": ("розірв", "припинен", "расторж", "прекращен", "terminat", "rozwiąz", "wypowiedz", "kündig"),
    "how changes are announced": ("зміни", "змін", "изменен", "changes to", "modif", "zmian", "änderung"),
}
NO_RETURNS_WORDS = ("не підлягає", "не подлежит", "no returns", "not accept returns", "all sales are final", "final sale",
                    "nie podlega zwrotowi", "nie przyjmujemy zwrot", "vom umtausch ausgeschlossen", "keine rückgabe")
# generic payment wording - counts on a policy page, but not in the footer (a "Оплата і доставка" link is not a logo)
PAYMENT_PAGE_WORDS = ("на карту", "на картку", "карткою", "картой", "готівк", "наличн", "на рахунок", "by card",
                      "credit card", "bank transfer", "gotówk", "przelew", "kartą", "überweisung", "kreditkarte")
PAYMENT_WORDS = ("visa", "mastercard", "apple pay", "google pay", "liqpay", "wayforpay", "monobank", "privat24",
                 "приват24", "fondy", "portmone", "paypal", "stripe", "klarna", "blik", "przelewy24", "payu", "sofort",
                 "накладен", "післяплат", "наложенн", "оплата при отриманні", "cash on delivery", "za pobraniem",
                 "nachnahme", "pobranie")
BUSINESS_HOURS = re.compile(r"\b\d{1,2}[:.]\d{2}\s*[-\u2013\u2014до]+\s*\d{1,2}[:.]\d{2}|\b(?:пн|пон|mon|pon|mo)\.?\s*[-\u2013\u2014]\s*"
                            r"(?:пт|п'ят|fri|pt|pią|fr|нд|sun|nd|so)\b|щодня|ежедневно|daily|codziennie|täglich", re.I)
RESPONSE_TIME = re.compile(r"(?:протягом|впродовж|в течени\w|within|w ciągu|innerhalb)\s+(?:\d+|одн\w+|24|кількох|нескольк\w+|few)?"
                           r"\s*(?:годин|год\.?|час\w*|хвилин|минут|hour|godzin|stund|робоч\w+ дн|business day|dni)", re.I)
FREE_SHIP_CLAIM = re.compile(r"(?:безкоштовн\w+ доставк\w*|бесплатн\w+ доставк\w*|free (?:shipping|delivery)|darmow\w+ "
                             r"(?:dostaw\w*|wysyłk\w*)|kostenlose[nr]? (?:versand|lieferung)|gratis versand)"
                             r"[^.\n]{0,40}?(?:від|от|from|od|ab)\s*(\d[\d\s]{1,6})", re.I)
VAGUE_NAV = re.compile(r"^(?:all products|shop all|collection|collections|products|всі товари|все товары|колекці\w*|"
                       r"коллекци\w*|wszystkie produkty|kolekcj\w*|alle produkte|kollektion\w*)$", re.I)
SOLD_OUT = re.compile(r"немає в наявності|нема в наявності|нет в наличии|out of stock|sold out|brak w magazynie|"
                      r"wyprzedan|niedostępn|ausverkauft|nicht verfügbar|розпродано|class=\"[^\"]*\boutofstock\b", re.I)
# Text pasted straight out of the ChatGPT UI, or ChatGPT citation residue (seen in real feed descriptions).
CHATGPT_ARTIFACTS = (r'data-testid="conversation-turn', r"data-message-author-role", r"data-message-id",
                     r"contentReference\[oaicite", r"oaicite:\d", r"\bturn\d+(?:search|view)\d+", r"utm_source=chatgpt\.com",
                     r"as an ai language model", r"як мовна модель", r"как языковая модель", r"jako model językowy")
# Generic filler a reviewer reads as "nobody real wrote this About page".
GENERIC_ABOUT = (r"passionate about (?:bringing|providing|delivering)", r"one-stop (?:shop|destination)",
                 r"in today'?s fast-paced world", r"we strive to (?:provide|bring|offer)", r"your satisfaction is our (?:top )?priority",
                 r"у сучасному світі", r"прагнемо надати (?:вам )?найкращ", r"ваше задоволення[^.]{0,20}пріоритет",
                 r"в современном мире", r"стремимся (?:предоставить|предложить) (?:вам )?лучш",
                 r"w dzisiejszym (?:szybko zmieniającym|dynamicznym) świecie", r"naszym priorytetem jest (?:twoja|pełna) satysfakcja")
PROMO_TITLE = re.compile(r"free shipping|free delivery|безкоштовн\w+ доставк|бесплатн\w+ доставк|darmow\w+ dostaw|"
                         r"kostenlos\w* versand|buy now|купи(?:ти|ть) зараз|купить сейчас|kup teraz|jetzt kaufen|"
                         r"\bакці[яї]\b|\bакция\b|знижк|скидк|розпродаж|распродаж|promocj|wyprzedaż|\bsale\b|"
                         r"-\s?\d{1,2}\s?%|\bхіт\b|\bхит\b|\bbestseller\b|\bnew!", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕]")

RESULTS = []      # (section, status, check, evidence)
STATUS_ORDER = {"FAIL": 0, "WARN": 1, "PASS": 2}
LOG_LINES = []


# ---------------------------------------------------------------- output utils
def out(line=""):
    print(line)
    LOG_LINES.append(line)


def record(section, status, check, evidence=""):
    RESULTS.append((section, status, check, evidence))
    out(f"  {status:<4}  {check}" + (f"\n        {evidence}" if evidence else ""))


def section(title):
    out("")
    out("=" * 78)
    out(title)
    out("=" * 78)


# ---------------------------------------------------------------- web helpers
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "uk,en;q=0.8,pl;q=0.6"})


def fetch(url, timeout=30):
    """GET a page. Returns (status, final_url, html). Never raises."""
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        return r.status_code, r.url, r.text
    except requests.RequestException as e:
        return None, url, f"__ERROR__ {e}"


def looks_bot_blocked(html):
    h = html.lower()
    return len(html) < 3000 and any(k in h for k in ("protected section", "captcha", "cf-chl",
                                                     "checking your browser", "challenge"))


def html_to_text(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    text = unescape(re.sub(r"(?s)<[^>]+>", " ", html))
    return re.sub(r"\s+", " ", text).strip()


def links_from(html, base):
    """[(absolute_url, link_text)] for same-site links."""
    host = urlparse(base).netloc.replace("www.", "")
    found = []
    for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html):
        href, inner = m.group(1).strip(), html_to_text(m.group(2))
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absu = urljoin(base, href)
        if urlparse(absu).netloc.replace("www.", "") == host:
            found.append((absu.split("?")[0], inner))
    return found


SKIP_PATHS = ("/blog/", "/category/", "/tag/", "/product/", "/products/", "/shop/", "/author/", "/feed")


def classify(url, text):
    """Page type by keyword PREFIX match on words of the link text + url path.
    Prefix (not substring) matching on purpose: 'rodo' once matched inside
    'prodovzhuye' and classified a blog post as the privacy page."""
    path = unquote(urlparse(url).path).lower()
    if any(sp in path for sp in SKIP_PATHS):
        return None
    words = re.findall(r"[^\W_]+", (path + " " + text).lower())
    for ptype, keys in PAGE_TYPES.items():
        for k in keys:
            if " " in k:
                if k in (path + " " + text).lower():
                    return ptype
            elif any(w.startswith(k) for w in words):
                return ptype
    return None


def emails_in(html):
    return {e.lower() for e in re.findall(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b", html)
            if not e.lower().endswith((".png", ".jpg", ".webp", ".svg", ".gif"))}


STREET_RE = re.compile(
    r"[^\W\d_]{3,}\s+(?:шосе|бульвар|проспект|street|straße|strasse)\s+\d+[а-яa-z]?\b"      # "Бериславське шосе 2"
    r"|(?:\bвул\.?|вулиця|\bпросп\.?|\bul\.|ulica|\bal\.|\bstr\.)\s*[^\W\d_][^,;|\n\d]{1,28}?\s\d+[а-яa-z]?\b",  # "вул. Грецька 33"
    re.I)


def digits(s):
    return re.sub(r"\D", "", s or "")


def phones_in(html, text):
    found = set()
    for m in re.finditer(r'tel:([+\d\s\-()]+)', html):
        found.add(digits(m.group(1))[-9:])
    for m in re.finditer(r"\+?\d[\d\s\-()]{7,18}\d", text):
        d = digits(m.group(0))
        before = text[max(0, m.start() - 25):m.start()].lower()
        # tax / company / bank numbers look like phones (e.g. "TIN: 332406726592") - skip them
        if any(k in before for k in ("іпн", "інн", "инн", "єдрпоу", "едрпоу", "iban", "nip", "regon", "krs",
                                     "код", "мфо", "рахун", "account", "ust-id", "vat")):
            continue
        if 9 <= len(d) <= 13:
            found.add(d[-9:])
    return found


def address_tokens(addr):
    """Meaningful words of an address (street name / city), lower-cased."""
    words = re.findall(r"[^\W\d_]{4,}", (addr or "").lower())
    stop = {"street", "вулиця", "вул", "шосе", "ulica", "straße", "strasse", "avenue", "проспект"}
    return [w for w in words if w not in stop]


def footer_html(html):
    """The page's last <footer> block (themes nest several), or the last 15% of the HTML as a fallback."""
    blocks = re.findall(r"(?is)<footer\b.*?</footer>", html or "")
    return blocks[-1] if blocks else (html or "")[int(len(html or "") * 0.85):]


def header_html(html):
    """<header> + first <nav> - where the main menu lives."""
    m = re.search(r"(?is)<header\b.*?</header>", html or "")
    n = re.search(r"(?is)<nav\b.*?</nav>", html or "")
    return (m.group(0) if m else "") + (n.group(0) if n else "")


def main_content(html):
    """Page HTML without header/footer/nav - what's on the product page itself, not sitewide chrome."""
    return re.sub(r"(?is)<(header|footer|nav)\b.*?</\1>", " ", html or "")


def stems_in(text, stems):
    low = (text or "").lower()
    return [s for s in stems if s in low]


def snippet(text, pattern, width=70):
    m = re.search(pattern, text or "", re.I)
    if not m:
        return ""
    return text[max(0, m.start() - width):m.end() + width].strip()


# ---------------------------------------------------------------- Content API
def api_get(path, headers, params=None, tries=6):
    """GET with retry - the Content API throws transient 410/409 'was sunset' errors that
    clear on retry within seconds (see CLAUDE.md; 409 variant seen 2026-10-15)."""
    for i in range(tries):
        r = requests.get(f"{CONTENT_API}/{path}", headers=headers, params=params, timeout=60)
        if r.status_code in (409, 410, 429, 500, 503) and i < tries - 1:
            time.sleep(2 * (i + 1))
            continue
        return r
    return r


def list_products(mid, headers):
    items, token = [], None
    while True:
        params = {"maxResults": 250}
        if token:
            params["pageToken"] = token
        r = api_get(f"{mid}/products", headers, params)
        if r.status_code != 200:
            break
        data = r.json()
        items += data.get("resources", [])
        token = data.get("nextPageToken")
        if not token:
            break
    return items


# ---------------------------------------------------------------- page facts
def extract_day_ranges(text):
    """'1-2 дні', '3\u20135 business days', '14 днів' -> list of (min, max, snippet)."""
    out_ = []
    pat = re.compile(r"(\d{1,2})\s*(?:[-\u2013\u2014]|до|to|do|bis)?\s*(\d{1,2})?\s*"
                     r"(?:робоч\w*\s*|business\s*|working\s*|roboc\w*\s*|werk\w*\s*)?"
                     r"(дн\w*|діб|доб\w*|day\w*|dni|dzie\w*|tag\w*|тиж\w*|week\w*)", re.I)
    for m in pat.finditer(text):
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        unit = m.group(3).lower()
        if unit.startswith(("тиж", "week")):
            a, b = a * 7, b * 7
        s = max(0, m.start() - 60)
        out_.append((a, b, text[s:m.end() + 40].strip()))
    return out_


def extract_prices(text):
    pat = re.compile(r"(\d[\d\s]{0,6}(?:[.,]\d{1,2})?)\s*(грн|uah|₴|zł|pln|€|eur|usd|\$)", re.I)
    vals = []
    for m in pat.finditer(text):
        try:
            vals.append(float(m.group(1).replace(" ", "").replace(",", ".")))
        except ValueError:
            pass
    return vals


def jsonld_offer(html):
    """(price, availability) from schema.org Product JSON-LD if present."""
    for block in re.findall(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "@graph" in node:
                    stack += node["@graph"]
                offers = node.get("offers")
                if offers:
                    offers = offers if isinstance(offers, list) else [offers]
                    for o in offers:
                        price = o.get("price") or o.get("lowPrice")
                        if price is None and isinstance(o.get("priceSpecification"), list):
                            price = (o["priceSpecification"][0] or {}).get("price")
                        if price is not None:
                            return float(str(price).replace(",", ".")), str(o.get("availability", ""))
            elif isinstance(node, list):
                stack += node
    m = re.search(r'(?:product:price:amount|itemprop=["\']price["\'])[^>]*content=["\']([\d.,]+)', html)
    if m:
        return float(m.group(1).replace(",", ".")), ""
    return None, ""


def woo_variation_offer(html, link):
    """WooCommerce variable product: the feed link carries ?attribute_pa_x=value and the
    variant's price lives in the form's data-product_variations JSON (rendered by JS),
    not in the static price text (e.g. a 0.5 l variant priced 480 vs a default of 399).
    Returns (price, in_stock) for the variation matching the link's attributes, or (None, None)."""
    from urllib.parse import parse_qs
    want = {k: v[0] for k, v in parse_qs(urlparse(link).query).items() if k.startswith("attribute_")}
    m = re.search(r'data-product_variations="([^"]*)"', html) or re.search(r"data-product_variations='([^']*)'", html)
    if not want or not m:
        return None, None
    try:
        variations = json.loads(unescape(m.group(1)))
    except (json.JSONDecodeError, TypeError):
        return None, None
    for v in variations if isinstance(variations, list) else []:
        attrs = v.get("attributes", {})
        if all(attrs.get(k) in (val, "") for k, val in want.items()):
            return float(v.get("display_price")), bool(v.get("is_in_stock"))
    return None, None


def sitemap_product_count(base):
    status, _, xml = fetch(urljoin(base, "/sitemap_index.xml"))
    if status != 200 or "<sitemap" not in xml:
        status, _, xml = fetch(urljoin(base, "/sitemap.xml"))
    if status != 200:
        return None
    subs = re.findall(r"<loc>([^<]*product[^<]*\.xml)</loc>", xml)
    if not subs:
        return None
    total = 0
    for s in subs:
        st, _, sx = fetch(s)
        if st == 200:
            total += len(re.findall(r"<url>", sx))
    return total


# ---------------------------------------------------------------- main checks
def run(args):
    meta = resolve(args.client)
    domain = re.sub(r"^https?://", "", meta.get("domain") or "").strip("/")   # tolerate a domain saved with its scheme
    mid = meta.get("merchant_center_id")
    if not domain:
        sys.exit(f"No 'domain' for '{args.client}' in clients.json")

    today = date.today().isoformat()
    report_dir = WORKSPACE / "clients" / meta["slug"] / "reports"
    page_dir = report_dir / f"policy_check_{today}"
    page_dir.mkdir(parents=True, exist_ok=True)

    out(f"Merchant Center policy & website alignment check - {meta['name']} ({meta['slug']})")
    out(f"Date: {today}   Merchant Center: {mid or 'not configured - website-only checks'}")

    headers, account, shipping, returns = None, {}, {}, []
    if mid:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from ga4_reports import get_credentials
        headers = {"Authorization": f"Bearer {get_credentials().token}"}

    # ---------------- 1. account status
    if mid:
        section("1. Account status (Merchant Center)")
        st = api_get(f"{mid}/accountstatuses/{mid}", headers)
        if st.status_code == 200:
            sj = st.json()
            record("account", "PASS" if sj.get("websiteClaimed") else "FAIL",
                   "Website claimed in Merchant Center", f"websiteClaimed={sj.get('websiteClaimed')}")
            issues = sj.get("accountLevelIssues", [])
            grouped = {}
            for i in issues:
                grouped.setdefault((i.get("severity"), i.get("title")), []).append(i.get("destination"))
            if not grouped:
                record("account", "PASS", "No account-level issues")
            for (sev, title), dests in sorted(grouped.items()):
                record("account", "FAIL" if sev == "critical" else "WARN",
                       f"Account issue ({sev}): {title}", "destinations: " + ", ".join(sorted(filter(None, dests))))
            disapproved = 0
            for p in sj.get("products", []):
                s = p.get("statistics", {})
                if p.get("destination") in ("Shopping", "SurfacesAcrossGoogle"):
                    out(f"        products {p['destination']}/{p.get('country')}: active {s.get('active')}, "
                        f"pending {s.get('pending')}, disapproved {s.get('disapproved')}, expiring {s.get('expiring')}")
                    disapproved = max(disapproved, int(s.get("disapproved") or 0))
            # under an account suspension every item shows disapproved - the item-level reasons are what matter
            record("account", "WARN" if disapproved else "PASS", "No disapproved products (Needs attention)",
                   f"{disapproved} disapproved - fix item-level issues before requesting a review; "
                   "/merchant-review lists the concrete reasons" if disapproved else "")
        else:
            record("account", "WARN", "Could not read account status", f"HTTP {st.status_code}")

        r = api_get(f"{mid}/accounts/{mid}", headers)
        account = r.json() if r.status_code == 200 else {}
        r = api_get(f"{mid}/shippingsettings/{mid}", headers)
        shipping = r.json() if r.status_code == 200 else None
        r = api_get(f"{mid}/returnpolicyonline", headers)
        returns = r.json().get("returnPolicies", []) if r.status_code == 200 else None
        for what, val in (("business info", account or None), ("shipping settings", shipping), ("return policies", returns)):
            if val is None:
                record("account", "WARN", f"Could not read MC {what} after retries",
                       "Content API error - checks that depend on it are skipped, re-run later")

    # ---------------- crawl the site
    base = account.get("websiteUrl") or f"https://www.{domain}/"
    status, home_url, home_html = fetch(base)
    if status != 200 or looks_bot_blocked(home_html):
        out(f"\nHomepage fetch: HTTP {status} - {'bot-check page' if looks_bot_blocked(home_html) else 'not 200'}."
            " Website checks below may be incomplete - verify manually in a browser.")
    pages = {"home": (home_url, home_html)}
    candidates = {}
    for url, text in links_from(home_html, home_url):
        ptype = classify(url, text)
        if ptype and ptype not in candidates:
            candidates[ptype] = url
    # registry override for pages whose name doesn't say what they are (e.g. a page called "Our story" = about)
    if meta.get("about_url"):
        candidates["about"] = meta["about_url"]
    # MC-declared URLs count as candidates too (returns URI / customer service URL)
    for rp in returns or []:
        if rp.get("returnPolicyUri") and "returns" not in candidates:
            candidates["returns"] = rp["returnPolicyUri"]
    for ptype, url in candidates.items():
        st, final, html = fetch(url)
        pages[ptype] = (final, html if st == 200 else "")
        (page_dir / f"{ptype}.txt").write_text(f"URL: {final}\nHTTP: {st}\n\n{html_to_text(html)}", encoding="utf-8")
    (page_dir / "home.txt").write_text(f"URL: {home_url}\n\n{html_to_text(home_html)}", encoding="utf-8")
    site_text = " ".join(html_to_text(h) for _, h in pages.values())
    site_html = " ".join(h for _, h in pages.values())

    # ---------------- 2. business identity
    if mid:
        section("2. Business identity - Merchant Center business info vs website")
        bi = account.get("businessInformation", {})
        cs = bi.get("customerService", {})
        addr = bi.get("address", {})
        out(f"  MC business info: name={account.get('name')!r} address={addr} customerService={cs}")

        if cs.get("phoneNumber"):
            want = digits(cs["phoneNumber"])[-9:]
            have = phones_in(site_html, site_text)
            record("identity", "PASS" if want in have else "FAIL",
                   f"MC phone {cs['phoneNumber']} shown on website",
                   "found" if want in have else f"site phones (last 9 digits): {sorted(have) or 'none found'}")
        else:
            record("identity", "WARN", "No customer-service phone in MC business info")

        if cs.get("email"):
            em = cs["email"].lower()
            on_site = em in site_html.lower()
            record("identity", "PASS" if on_site else "FAIL", f"MC email {em} shown on website",
                   "" if on_site else "not found on home/contact/policy pages (also check for JS/Cloudflare email obfuscation)")
            if em.split("@")[-1].startswith(FREE_MAIL):
                record("identity", "WARN", "Support email is a free-mail address, not on the store domain",
                       f"{em} - checklists flag this as a trust signal; prefer info@{domain}")
        else:
            record("identity", "WARN", "No customer-service email in MC business info")

        if addr:
            toks = address_tokens(addr.get("streetAddress", "")) + address_tokens(addr.get("locality", ""))
            low = site_text.lower()
            hits = [t for t in toks if t in low]
            ok = toks and len(hits) == len(toks)
            record("identity", "PASS" if ok else "FAIL",
                   f"MC address shown on website ({addr.get('streetAddress','').strip()}, {addr.get('locality','')})",
                   f"matched words: {hits} of {toks}" + ("" if ok else " - reviewers copy the MC address and look for it on the site"))
            num = re.search(r"\d+", addr.get("streetAddress", ""))
            if ok and num and num.group(0) not in low:
                record("identity", "WARN", "Street matched but house number not found next to it", num.group(0))
        else:
            record("identity", "FAIL", "No business address in MC business info")

        if not cs.get("url"):
            record("identity", "WARN", "No customer-service URL in MC business info",
                   "fill every business-info field - point it at the contact page")
        if cs.get("url"):
            cu = cs["url"]
            st, _, _ = fetch(cu)
            generic = urlparse(cu).path in ("", "/")
            record("identity", "WARN" if generic or st != 200 else "PASS",
                   f"MC customer-service URL {cu}",
                   f"HTTP {st}" + (" - points at the homepage, better to point at the contact page" if generic else ""))

        # every phone / email / street address on the key pages, not just the MC one -
        # several different contact details across pages reads as inconsistent identity
        where_ph, where_em, where_st = {}, {}, {}
        for ptype, (url, html) in pages.items():
            t = html_to_text(html)
            for ph in phones_in(html, t):
                where_ph.setdefault(ph, set()).add(ptype)
            for em in emails_in(html):
                where_em.setdefault(em, set()).add(ptype)
            for m in STREET_RE.finditer(t):
                where_st.setdefault(re.sub(r"\s+", " ", m.group(0)).strip(), set()).add(ptype)
        mc_ph = digits(cs.get("phoneNumber", ""))[-9:]
        other_ph = {k: v for k, v in where_ph.items() if k != mc_ph}
        record("identity", "WARN" if other_ph else "PASS", "Only the MC phone is used across key pages",
               "; ".join(f"...{k} on {sorted(v)}" for k, v in other_ph.items()) +
               (" - several numbers are fine if they are clearly labelled (shop/office), but each must be reachable" if other_ph else ""))
        other_em = {k: v for k, v in where_em.items() if k != cs.get("email", "").lower()}
        record("identity", "WARN" if other_em else "PASS", "Only the MC email is used across key pages",
               "; ".join(f"{k} on {sorted(v)}" for k, v in other_em.items()))
        # another business's website / email named in the policy texts = copy-pasted template,
        # Google's "false identity or contact information" (egregious, suspension without warning).
        # Seen live: an offer contract carrying another shop's domain and company details.
        store = domain.replace("www.", "")
        foreign = {}
        for ptype in ("terms", "privacy", "returns", "shipping", "contact"):
            t = html_to_text(pages.get(ptype, ("", ""))[1])
            for m in re.finditer(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+(?:com\.ua|ua|pl|com|net|org|de|eu|shop|store))\b",
                                 t, re.I):
                d = m.group(1).lower()
                if store in d or d.endswith(FREE_MAIL) or any(n in d for n in NEUTRAL_DOMAINS) or "@" in t[max(0, m.start() - 1):m.start()]:
                    continue
                s0 = max(0, m.start() - 90)
                foreign.setdefault(d, (ptype, t[s0:m.end() + 40]))
            for em in emails_in(pages.get(ptype, ("", ""))[1]):
                d = em.split("@")[1]
                if store not in d and not d.startswith(FREE_MAIL) and not any(n in d for n in NEUTRAL_DOMAINS):
                    foreign.setdefault(d, (ptype, em))
        record("identity", "FAIL" if foreign else "PASS",
               "Policy pages name only this store (no other company's website/email)",
               " | ".join(f"{d} on {pt}: '...{sn}...'" for d, (pt, sn) in foreign.items()) +
               (" - looks like a copied template; Google treats false identity/contact info as egregious misrepresentation" if foreign else ""))
        if len(where_st) > 1:
            record("identity", "WARN", "More than one street address on key pages - make sure MC's address is the main one",
                   "; ".join(f"'{k}' on {sorted(v)}" for k, v in where_st.items()))

        # footer = what a reviewer sees on every page; business name/address/phone/email as crawlable TEXT
        # (a name baked into the logo image doesn't count) - videos + compliance guide 2026-10-24
        ft_html = footer_html(home_html)
        ft_text = html_to_text(ft_html).lower()
        want = {"business name": (account.get("name") or "").lower(),
                "phone": digits(cs.get("phoneNumber", ""))[-9:],
                "email": (cs.get("email") or "").lower()}
        missing = []
        if want["business name"] and want["business name"] not in ft_text:
            missing.append("business name")
        if want["phone"] and want["phone"] not in phones_in(ft_html, html_to_text(ft_html)):
            missing.append("phone")
        if want["email"] and want["email"] not in ft_html.lower():
            missing.append("email")
        toks = address_tokens(addr.get("streetAddress", "")) if addr else []
        if toks and not all(t in ft_text for t in toks):
            missing.append("address")
        record("identity", "WARN" if missing else "PASS", "Footer shows the MC business details as text",
               f"missing in the homepage footer: {missing} - the footer is on every page, reviewers check it first; "
               "use real text, not an image" if missing else "name, phone, email, address found in the footer")

        # company details repeated on each policy page (the videos copy the footer block onto every policy page;
        # with a sitewide footer that holds them this passes automatically)
        lacking = []
        for ptype in ("shipping", "returns", "privacy", "terms"):
            h = pages.get(ptype, ("", ""))[1]
            if not h:
                continue
            t = html_to_text(h).lower()
            has = (want["phone"] and want["phone"] in phones_in(h, html_to_text(h))) or \
                  (want["email"] and want["email"] in h.lower()) or (toks and all(x in t for x in toks))
            if not has:
                lacking.append(ptype)
        record("identity", "WARN" if lacking else "PASS", "Business contact details on every policy page",
               f"no MC phone/email/address on: {lacking}" if lacking else "")

    # ---------------- 3. required pages
    section("3. Required pages - linked from the homepage, live, real content")
    for ptype in REQUIRED_PAGES + RECOMMENDED_PAGES:
        url, html = pages.get(ptype, (candidates.get(ptype), ""))
        linked = ptype in candidates and not (ptype == "returns" and candidates["returns"] not in
                                             [u for u, _ in links_from(home_html, home_url)])
        if not url:
            note = "no link found on the homepage (header/footer) - reviewers do not go hunting"
            if ptype == "track":
                note = ("no 'Track your order' page linked - recommended by every approval checklist; at minimum "
                        "explain tracking on the shipping page (checked below)")
            elif ptype == "faq":
                note = "no FAQ page linked - recommended; if added, its numbers must match the policies"
            if ptype == "privacy":
                terms_t = html_to_text(pages.get("terms", ("", ""))[1]).lower()
                if "персональн" in terms_t or "personal data" in terms_t or "dane osobowe" in terms_t:
                    note = ("no standalone privacy policy - personal data is only covered inside the terms/offer page; "
                            "Google's trust guide and every approval checklist expect a separate, linked privacy policy")
            record("pages", "FAIL" if ptype in REQUIRED_PAGES else "WARN", f"{ptype} page", note)
            continue
        words = len(html_to_text(html).split()) - len(html_to_text(home_html).split()) if html else 0
        body_words = len(html_to_text(html).split()) if html else 0
        if not html:
            record("pages", "FAIL", f"{ptype} page", f"{url} - not reachable (non-200)")
        elif not linked:
            record("pages", "WARN", f"{ptype} page", f"{unquote(url)} exists (from MC settings) but is not linked from the homepage")
        else:
            record("pages", "PASS", f"{ptype} page", f"{unquote(url)} - {body_words} words on page")
        _ = words

    # one combined "shipping & returns" page (Sunder Avenue audit video): Google wants each findable on its own
    if candidates.get("shipping") and candidates.get("shipping") == candidates.get("returns"):
        record("pages", "WARN", "Shipping and returns have separate pages",
               f"both resolve to {unquote(candidates['shipping'])} - split into a dedicated shipping page and a dedicated returns page")

    # policy links on EVERY page, not only the homepage footer (compliance guide; videos: footer is sitewide)
    gaps = {}
    for ptype, (url, html) in pages.items():
        if ptype == "home" or not html:
            continue
        have = {classify(u, t) for u, t in links_from(html, url)} | {ptype}
        miss = [r for r in REQUIRED_PAGES if r in candidates and r not in have]
        if miss:
            gaps[ptype] = miss
    record("pages", "WARN" if gaps else "PASS", "Policy links present on every key page (sitewide footer)",
           "; ".join(f"{p} page lacks links to {m}" for p, m in gaps.items()) if gaps else
           f"checked {len(pages) - 1} pages")

    # main menu: about + contact reachable from the header; no vague "All products" / "Collection" item
    hdr = header_html(home_html)
    if hdr:
        hl = links_from(hdr, home_url)
        in_menu = {classify(u, t) for u, t in hl}
        miss = [p for p in ("about", "contact") if p in candidates and p not in in_menu]
        vague = sorted({t for _, t in hl if VAGUE_NAV.match(t.strip())})
        record("pages", "WARN" if miss or vague else "PASS", "Header menu: about + contact, specific category names",
               (f"not in the header menu: {miss}. " if miss else "") +
               (f"vague menu items {vague} - name what you sell (e.g. 'Пиво', 'Men', 'Lamps')" if vague else ""))
    else:
        out("  (no <header>/<nav> block found - check the main menu manually)")

    # payment methods: icons/names in the footer + explained on a page (compliance guide§7, video 2's payment policy)
    pay_ft = stems_in(html_to_text(footer_html(home_html)) + " " + " ".join(
        re.findall(r'(?:alt|src|class)=["\']([^"\']+)', footer_html(home_html))), PAYMENT_WORDS)
    record("pages", "PASS" if pay_ft else "WARN", "Payment methods shown in the footer",
           ", ".join(sorted(set(pay_ft))) if pay_ft else "no payment logos/names in the homepage footer")
    pay_pages = [p for p in ("shipping", "terms", "returns", "faq") if stems_in(html_to_text(pages.get(p, ("", ""))[1]), PAYMENT_WORDS + PAYMENT_PAGE_WORDS)]
    record("pages", "PASS" if pay_pages else "WARN", "Payment methods explained on a policy page",
           f"on: {pay_pages}" if pay_pages else "no page explains how to pay - add a payment section/page")

    # contact page: business hours + expected response time (compliance guide)
    c_text = html_to_text(pages.get("contact", ("", ""))[1]) + " " + html_to_text(footer_html(home_html))
    if pages.get("contact", ("", ""))[1]:
        hrs = BUSINESS_HOURS.search(c_text)
        record("pages", "PASS" if hrs else "WARN", "Business hours on the contact page / footer",
               f"'{hrs.group(0)}'" if hrs else "no opening/support hours found")
        rt = RESPONSE_TIME.search(c_text)
        record("pages", "PASS" if rt else "WARN", "Expected response time stated on the contact page",
               f"'{rt.group(0)}'" if rt else "e.g. 'відповідаємо протягом 24 годин' - optional but recommended")

    # page CONTENT, not just existence (Misrepresentation recovery checklists, 2025-26)
    home_words = set(html_to_text(home_html).lower().split())

    def unique_text(ptype):
        html = pages.get(ptype, ("", ""))[1]
        return " ".join(w for w in html_to_text(html).lower().split() if w not in home_words), html

    about_t, about_h = unique_text("about")
    if about_h:
        imgs = set(re.findall(r'<img[^>]+src=["\']([^"\']+)', about_h)) - set(re.findall(r'<img[^>]+src=["\']([^"\']+)', home_html))
        record("pages", "PASS" if len(about_t.split()) >= 80 and imgs else "WARN", "About page has a real story + own photos",
               f"{len(about_t.split())} page-specific words, {len(imgs)} page-specific images (story, mission, team/workspace photos)")
        generic = [snippet(about_t, p, 40) for p in GENERIC_ABOUT if re.search(p, about_t, re.I)]
        record("pages", "WARN" if generic else "PASS", "About page doesn't read like generic AI filler",
               " | ".join(f"'...{g}...'" for g in generic[:3]) +
               " - reviewers flag About pages nobody real wrote; replace with the owner's own story (when, where, why)"
               if generic else "no stock filler phrases found - still read it (Step 2)")
    ship_t, ship_h = unique_text("shipping")
    if ship_h:
        car = [c for c in CARRIERS if c in ship_t]
        dst = [d for d in DESTINATIONS if d in ship_t]
        record("pages", "PASS" if car else "WARN", "Shipping page names the carriers", ", ".join(car) or "no carrier named")
        record("pages", "PASS" if dst else "WARN", "Shipping page states delivery destinations", ", ".join(dst) or "no country/area named")
        trk = stems_in(ship_t, TRACKING)
        record("pages", "PASS" if trk else "WARN", "Shipping page explains how to track the order",
               ", ".join(trk) if trk else "nothing about tracking numbers / how to check status")
        bd = stems_in(ship_t, BUSINESS_DAYS)
        record("pages", "PASS" if bd else "WARN", "Shipping times stated in business days",
               ", ".join(bd) if bd else "no 'робочих днів / business days' - say which days count, consistently with MC")
        ns = stems_in(ship_t, NO_SHIP)
        record("pages", "PASS" if ns else "WARN", "Shipping page says where you do NOT ship",
               ", ".join(ns) if ns else "e.g. 'доставка лише по Україні, крім тимчасово окупованих територій' / 'we do not ship outside PL'")
        services_c = {s.get("deliveryCountry") for s in (shipping or {}).get("services", []) if s.get("active")}
        if len(services_c) > 1 or stems_in(ship_t, INTERNATIONAL):
            cu = stems_in(ship_t, CUSTOMS)
            record("pages", "PASS" if cu else "WARN", "International shipping: customs / import taxes mentioned",
                   ", ".join(cu) if cu else "the site ships abroad but says nothing about who pays duties/import VAT")
    ret_t, ret_h = unique_text("returns")
    if ret_h:
        routes = [n for n, p in (("email", r"[\w.+-]+@[\w-]+\.[\w.]+"), ("phone", r"\+?\d[\d\s()-]{8,}\d"),
                                 ("form/portal", r"форм|form\b|formularz|formular|кабінет|кабинет|account|konto|portal|заявк"))
                  if re.search(p, ret_t, re.I)]
        record("pages", "PASS" if len(routes) >= 2 else "WARN", "Returns page gives at least two ways to start a return",
               f"found: {routes or 'none'}" + ("" if len(routes) >= 2 else
               " - e.g. email + phone, and say what to include (order number, photo)"))
        nr = stems_in(html_to_text(ret_h), NO_RETURNS_WORDS)   # full text: unique_text drops words also on the homepage
        mc_no_returns = any((rp.get("policy") or {}).get("type") == "NO_RETURNS" for rp in returns or [])
        if nr or mc_no_returns:
            # no-returns is a valid policy if stated plainly; refund timing/method/payer don't apply
            record("pages", "PASS" if nr else "WARN", "No-returns policy stated plainly on the returns page",
                   f"'...{snippet(html_to_text(ret_h), re.escape(nr[0]), 60)}...'" if nr else
                   "MC says NO_RETURNS but the page has no clear 'returns not accepted' sentence")
        else:
            refund_t = [s for a, b, s in extract_day_ranges(ret_t) if stems_in(s, REFUND_WORDS)]
            record("pages", "PASS" if refund_t else "WARN", "Refund timing stated (days until the money is back)",
                   f"'...{refund_t[0]}...'" if refund_t else "no 'N days' next to the refund wording")
            rm = stems_in(ret_t, REFUND_METHOD)
            record("pages", "PASS" if rm else "WARN", "Refund method stated (original payment method / store credit)",
                   ", ".join(rm) if rm else "say where the money goes back")
            pay = stems_in(ret_t, RETURN_SHIP_PAYER)
            record("pages", "PASS" if pay else "WARN", "Returns page says who pays return shipping",
                   ", ".join(pay) + " (compare with MC returnShippingFee above)" if pay else "not stated - must match MC's return shipping fee")
    # problem scenarios can sit on returns, shipping or terms pages - any of them counts
    probs_t = " ".join(html_to_text(pages.get(p, ("", ""))[1]) for p in ("returns", "shipping", "terms", "faq"))
    if probs_t.strip():
        miss = [k for k, stems in RETURN_SCENARIOS.items() if not stems_in(probs_t, stems)]
        record("pages", "WARN" if miss else "PASS", "Policies cover damaged / wrong / lost / incomplete orders",
               f"no wording found for: {miss}" if miss else "all four scenarios mentioned")
        cn = stems_in(probs_t, CANCEL)
        record("pages", "PASS" if cn else "WARN", "Order cancellation terms stated",
               ", ".join(cn) if cn else "nothing on how/until when an order can be cancelled")
    # liability: present = good, but a blanket "not responsible for lost/damaged parcels" is the opposite
    unfair = []
    for p in ("terms", "shipping", "returns"):
        t = html_to_text(pages.get(p, ("", ""))[1])
        for pat in UNFAIR_LIABILITY:
            s = snippet(t, pat, 60)
            if s:
                unfair.append(f"{p}: '...{s}...'")
    record("pages", "WARN" if unfair else "PASS", "No blanket 'not responsible for lost/damaged parcels' disclaimer",
           " | ".join(unfair[:3]) + " - until delivery the risk is the seller's (consumer law); reword to how you handle "
           "lost/damaged parcels (claim with the carrier, resend or refund)" if unfair else "")
    terms_t, terms_h = unique_text("terms")
    if terms_h:
        disp = [k for k in ("спір", "спор", "суперечк", "dispute", "spor", "reklamac", "streit") if k in terms_t]
        liab = [k for k in ("відповідальн", "ответственн", "liabilit", "odpowiedzialn", "haftung") if k in terms_t]
        record("pages", "PASS" if disp and liab else "WARN", "Terms cover dispute handling + liability limits",
               f"dispute: {disp or 'missing'}, liability: {liab or 'missing'}")
        full_terms = html_to_text(terms_h)
        miss = [k for k, stems in TERMS_GROUPS.items() if not stems_in(full_terms, stems)]
        contact = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s()-]{8,}\d", full_terms))
        if not contact:
            miss.append("seller contact details")
        record("pages", "WARN" if miss else "PASS", "Terms cover acceptance, IP, termination, changes, contacts",
               f"missing: {miss}" if miss else "")
    priv_h = pages.get("privacy", ("", ""))[1]
    if priv_h:
        pt = html_to_text(priv_h)
        miss = [k for k, stems in PRIVACY_GROUPS.items() if not stems_in(pt, stems)]
        law = PRIVACY_LAW.get(meta.get("country"), PRIVACY_LAW_EU)
        if not stems_in(pt, law):
            miss.append(f"applicable law ({' / '.join(law[:2])})")
        if not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", pt):
            miss.append("data controller contact (email)")
        record("pages", "WARN" if miss else "PASS", "Privacy policy covers data, purpose, sharing, retention, deletion, law",
               f"missing: {miss}" if miss else "")

    # ---------------- 4. policy consistency
    if mid:
        section("4. Policy consistency - Merchant Center settings vs website policy pages")
        ship_text = html_to_text(pages.get("shipping", ("", ""))[1])
        ret_text = html_to_text(pages.get("returns", ("", ""))[1])
        services = [s for s in (shipping or {}).get("services", []) if s.get("active")]
        if shipping is not None and not services:
            record("policy", "FAIL", "Active shipping service in Merchant Center", "none configured")
        for s in services:
            dt = s.get("deliveryTime", {})
            h_min, h_max = dt.get("minHandlingTimeInDays", 0), dt.get("maxHandlingTimeInDays", 0)
            t_min, t_max = dt.get("minTransitTimeInDays", 0), dt.get("maxTransitTimeInDays", 0)
            rates, table = [], []
            for g in s.get("rateGroups", []):
                v = g.get("singleValue", {})
                if "flatRate" in v:
                    rates.append(float(v["flatRate"]["value"]))
                elif v.get("noShipping"):
                    rates.append(None)
                elif "mainTable" in g:   # e.g. weight table copied from the carrier's price list
                    mt = g["mainTable"]
                    heads = (mt.get("rowHeaders", {}).get("weights") or mt.get("rowHeaders", {}).get("prices") or [])
                    for hd, row in zip(heads, mt.get("rows", [])):
                        cell = (row.get("cells") or [{}])[0].get("flatRate", {})
                        if cell:
                            table.append((f"{hd.get('value')} {hd.get('unit', hd.get('currency', ''))}".strip(), float(cell["value"])))
                else:
                    rates.append("carrier rate")
            if table:
                out(f"  MC rate table: " + ", ".join(f"up to {k}: {v:g}" for k, v in table))
            out(f"  MC service '{s.get('name')}' ({s.get('deliveryCountry')}): handling {h_min}-{h_max}d, "
                f"transit {t_min}-{t_max}d (total {h_min + t_min}-{h_max + t_max}d), rates {rates}")
            ranges = extract_day_ranges(ship_text)
            if not ship_text:
                record("policy", "FAIL", "Shipping times on website", "no shipping page to compare against")
            elif not ranges:
                record("policy", "WARN", "Shipping times on website",
                       "no 'N-M days' found on the shipping page - Google wants handling + transit time stated explicitly")
            else:
                ok = any((a, b) in [(t_min, t_max), (h_min + t_min, h_max + t_max)] for a, b, _ in ranges)
                record("policy", "PASS" if ok else "WARN",
                       f"Shipping time {t_min}-{t_max}d transit / {h_min + t_min}-{h_max + t_max}d total matches website",
                       "website says: " + " | ".join(f"{a}-{b}d: '...{snip}...'" for a, b, snip in ranges[:4]))
            prices = extract_prices(ship_text)
            if table:
                missing = [f"{k}: {v:g}" for k, v in table if not any(abs(p - v) < 0.01 for p in prices)]
                record("policy", "PASS" if not missing else "FAIL", "MC shipping rate table published on the shipping page",
                       "all amounts found" if not missing else f"not on the page: {missing} - shoppers and Google's reviewer "
                       "must see the same prices Merchant Center shows in ads")
            for rate in [r for r in rates if isinstance(r, float)]:
                ok = any(abs(p - rate) < 0.01 for p in prices)
                record("policy", "PASS" if ok else "WARN", f"Shipping cost {rate:g} {s.get('currency')} stated on website",
                       "found" if ok else f"amounts on shipping page: {sorted(set(prices))[:12] or 'none'}"
                       " - if the site quotes carrier tariffs instead of a flat fee, MC should use carrier/table rates")

        if returns == []:
            record("policy", "FAIL", "Return policy configured in Merchant Center",
                   "none - Google requires one even if you do not accept returns")
        for rp in returns or []:
            pol = rp.get("policy", {})
            ptype = pol.get("type")
            days = pol.get("numberOfDays") or pol.get("days")
            uri = rp.get("returnPolicyUri", "")
            out(f"  MC return policy '{rp.get('label')}' {rp.get('countries')}: type={ptype} days={days} "
                f"restockingFee={rp.get('restockingFee')} returnShippingFee={rp.get('returnShippingFee')} url={unquote(uri)}")
            st, _, _ = fetch(uri) if uri else (None, "", "")
            record("policy", "PASS" if st == 200 and domain in uri else "FAIL",
                   "MC return-policy URL is live and on the store domain", f"{unquote(uri) or 'missing'} -> HTTP {st}")
            mentioned = [(a, b, s) for a, b, s in extract_day_ranges(ret_text) if b <= 60]
            if ptype == "NO_RETURNS":
                if mentioned:
                    record("policy", "FAIL", "MC says NO_RETURNS but the returns page mentions a return window",
                           " | ".join(f"'...{s}...'" for _, _, s in mentioned[:3]) +
                           " - align them (MC 'number of days' policy, or reword the page)")
                else:
                    record("policy", "WARN", "MC says NO_RETURNS",
                           "check the returns page really states no returns, and that this is legal for the "
                           "country/product (e.g. EU/UA consumer 14-day rules have product-category exceptions)")
            elif days:
                ok = any(b == int(days) for _, b, _ in mentioned)
                record("policy", "PASS" if ok else "FAIL", f"Return window {days} days stated on returns page",
                       "found" if ok else f"page mentions: {[(a, b) for a, b, _ in mentioned][:6] or 'no day counts'}")
            fee = (rp.get("restockingFee") or {}).get("fixedFee", {}).get("value")
            if fee and float(fee) > 0 and "restock" not in ret_text.lower():
                record("policy", "WARN", "Restocking fee set in MC", f"{fee} - must be disclosed on the returns page before checkout")

    # ---------------- 5. technical / trust
    section("5. Technical & trust signals")
    record("tech", "PASS" if home_url.startswith("https://") else "FAIL", "Site served over HTTPS", home_url)
    if account.get("websiteUrl"):
        same = urlparse(account["websiteUrl"]).netloc.replace("www.", "") == domain.replace("www.", "")
        record("tech", "PASS" if same else "FAIL", "MC website URL matches the client domain",
               f"{account['websiteUrl']} vs {domain}")
    hits = []
    for ptype, (url, html) in pages.items():
        t = html_to_text(html)
        for pat in PLACEHOLDERS:
            m = re.search(pat, t, re.I)
            if m:
                s = max(0, m.start() - 50)
                hits.append(f"{ptype}: '...{t[s:m.end() + 30]}...'")
    record("tech", "FAIL" if hits else "PASS", "No placeholder / template text on key pages", " | ".join(hits[:5]))
    if account.get("name"):
        norm = lambda x: re.sub(r"[^a-zа-яіїєґ0-9]", "", x.lower())
        title = re.search(r"(?is)<title>(.*?)</title>", home_html)
        hay = norm(domain) + norm(title.group(1) if title else "")
        ok = norm(account["name"]) in hay
        record("tech", "PASS" if ok else "WARN", f"MC business name '{account['name']}' matches the site brand/domain",
               "" if ok else f"site title: {title.group(1).strip()[:80] if title else '?'} - keep name, domain and email branding consistent")
    if not mid:   # with a feed, reviews are checked on the actual product pages in section 6
        reviews = any(k in site_text.lower() for k in ("відгук", "отзыв", "review", "opini", "bewertung"))
        record("tech", "PASS" if reviews else "WARN", "Reviews / testimonials mentioned on key pages (keyword only - verify)",
               "" if reviews else "trust signal recommended in Google's 'Building trust' guide")

    # text pasted straight out of the ChatGPT UI (markup / citation residue) on any key page
    gpt = [f"{p}: '{m.group(0)}'" for p, (_, h) in pages.items() for pat in CHATGPT_ARTIFACTS
           for m in [re.search(pat, h, re.I)] if m]
    record("tech", "WARN" if gpt else "PASS", "No ChatGPT copy-paste residue on key pages",
           "; ".join(gpt[:5]) + " - remove the pasted markup and rewrite the text in your own words" if gpt else "")

    # sitewide shipping claims must say the same thing as the shipping page (video 2: "consistency is key")
    ship_page_t = html_to_text(pages.get("shipping", ("", ""))[1])
    claims = [(m.group(0).strip(), digits(m.group(1))) for m in FREE_SHIP_CLAIM.finditer(html_to_text(home_html))]
    if claims:
        collapsed = re.sub(r"(?<=\d)\s+(?=\d)", "", ship_page_t)   # "1 500" -> "1500"
        bad = [c for c, n in claims if n and not re.search(rf"(?<!\d){n}(?!\d)", collapsed)]
        record("tech", "WARN" if bad else "PASS", "Free-shipping threshold on the homepage = shipping page",
               f"homepage says {bad[:2]}, shipping page doesn't state that threshold" if bad else f"{claims[0][0]!r} found on both")

    # many sold-out products on the homepage = "unavailable offers" (Sunder Avenue audit video)
    so = len(SOLD_OUT.findall(home_html))
    record("tech", "WARN" if so >= 3 else "PASS", "Homepage doesn't showcase sold-out products",
           f"{so} sold-out markers on the homepage - hide sold-out items with no restock date, or mark pre-order with a date"
           if so >= 3 else f"{so} sold-out markers")

    # ---------------- 6. feed vs site
    if mid:
        section("6. Product feed vs website")
        products = list_products(mid, headers)
        online = [p for p in products if p.get("channel") == "online"]
        out(f"  Feed: {len(online)} online products")
        sm = sitemap_product_count(home_url)
        if sm is not None:
            gap = abs(sm - len(online)) / max(sm, 1)
            record("feed", "PASS" if gap <= 0.2 else "WARN", "Feed size vs website product sitemap",
                   f"feed {len(online)} vs sitemap {sm}" + ("" if gap <= 0.2 else
                   " - big gaps read as the catalogue not being represented accurately; check feed filters/rules"))
        random.seed(args.seed)
        sample = random.sample(online, min(args.sample, len(online)))
        bad_domain = [p for p in online if domain.replace("www.", "") not in urlparse(p.get("link", "")).netloc]
        record("feed", "FAIL" if bad_domain else "PASS", "All product links on the claimed domain",
               f"{len(bad_domain)} off-domain, e.g. {bad_domain[0].get('link')}" if bad_domain else "")
        record("feed", "PASS" if online else "FAIL", "Active feed with at least one product",
               f"{len(online)} online products" if online else "no online products - the Request review button needs an active feed")

        # ---- feed-wide data checks (compliance guide, videos 2-3), all products, not just the sample
        promo = [p for p in online if PROMO_TITLE.search(p.get("title", "")) or EMOJI.search(p.get("title", ""))]
        record("feed", "WARN" if promo else "PASS", "Feed titles free of promo text and emojis",
               f"{len(promo)} titles, e.g. " + " | ".join(repr(p.get("title", "")[:70]) for p in promo[:3]) +
               " - titles describe the product only ('free shipping', 'sale', '-20%', emojis go)" if promo else "")
        thin = [p for p in online if len(html_to_text(p.get("description", "")).split()) < 25]
        record("feed", "WARN" if thin else "PASS", "Feed descriptions not thin (25+ words)",
               f"{len(thin)} of {len(online)} under 25 words, e.g. {thin[0].get('offerId')}" if thin else "")
        gpt_feed = [p.get("offerId") for p in online if any(re.search(pat, p.get("description", ""), re.I) for pat in CHATGPT_ARTIFACTS)]
        record("feed", "WARN" if gpt_feed else "PASS", "No ChatGPT copy-paste residue in feed descriptions",
               f"{len(gpt_feed)} products: {gpt_feed[:8]} - strip the pasted markup" if gpt_feed else "")
        deep, undated = [], []
        for p in online:
            if not p.get("salePrice"):
                continue
            reg, sale = float(p.get("price", {}).get("value", 0) or 0), float(p["salePrice"].get("value", 0) or 0)
            if reg and sale and (reg - sale) / reg > 0.5:
                deep.append(f"{p.get('offerId')} {reg:g}->{sale:g}")
            if not p.get("salePriceEffectiveDate"):
                undated.append(p.get("offerId"))
        record("feed", "WARN" if deep else "PASS", "No discounts deeper than 50% in the feed",
               f"{len(deep)}: {deep[:5]} - deep 'was' prices read as fake reference pricing; keep them real and provable"
               if deep else "")
        if undated:
            record("feed", "WARN", "Sale prices have an end date (sale_price_effective_date)",
                   f"{len(undated)} sale items without dates, e.g. {undated[:5]} - also state the end date on the product page")
        oos = [p for p in online if p.get("availability", "").replace(" ", "_") == "out_of_stock"]
        share = len(oos) / max(len(online), 1)
        record("feed", "WARN" if share > 0.3 else "PASS", "Most of the feed is in stock",
               f"{len(oos)} of {len(online)} out of stock ({share:.0%})" +
               (" - a catalogue that is mostly unbuyable reads as 'unavailable offers'; hide items with no restock date"
                if share > 0.3 else ""))

        urgency_hits, badge_hits = [], []
        pp_no_links, pp_no_ship, pp_no_reviews, pp_deep, cond_bad, pp_no_nr, pp_checked = [], [], [], [], [], [], 0
        no_returns_policy = any((rp.get("policy") or {}).get("type") == "NO_RETURNS" for rp in returns or []) or \
            bool(stems_in(html_to_text(pages.get("returns", ("", ""))[1]), NO_RETURNS_WORDS))
        for p in sample:
            link = p.get("link", "")
            st, final, html = fetch(link)
            low = html.lower()
            for pat in URGENCY:
                m = re.search(pat, low)
                if m:
                    urgency_hits.append(f"{p.get('offerId')}: '{m.group(0)}'")
            for pat in FAKE_BADGES:
                m = re.search(pat, low)
                if m:
                    badge_hits.append(f"{p.get('offerId')}: '{m.group(0)}'")
            if st == 200:
                # title + image of the feed item should be what the landing page shows
                og = re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html)
                h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
                page_title = html_to_text((h1.group(1) if h1 else "") + " " + (og.group(1) if og else "")).lower()
                ft = set(re.findall(r"[^\W_]{3,}", p.get("title", "").lower()))
                overlap = len([w for w in ft if w in page_title]) / max(len(ft), 1)
                record("feed", "PASS" if overlap >= 0.5 else "WARN", f"{p.get('offerId')} title matches page",
                       "" if overlap >= 0.5 else f"feed '{p.get('title')}' vs page '{page_title[:90]}'")
                img = re.sub(r"(-\d+x\d+)?\.(jpe?g|png|webp|gif)$", "", urlparse(p.get("imageLink", "")).path.rsplit("/", 1)[-1], flags=re.I)
                if img:
                    record("feed", "PASS" if img.lower() in low else "WARN", f"{p.get('offerId')} feed image is on the page",
                           "" if img.lower() in low else f"{p.get('imageLink')} not referenced by the landing page")
                # what the shopper sees on the product page itself (compliance guide§3/§6, videos 2-3)
                pp_checked += 1
                linked_pp = {classify(u, t) for u, t in links_from(html, final)}
                if not {"returns", "shipping"} <= linked_pp:
                    pp_no_links.append(p.get("offerId"))
                body = html_to_text(main_content(html)).lower()
                if no_returns_policy and not stems_in(body, NO_RETURNS_WORDS):
                    pp_no_nr.append(p.get("offerId"))
                if not any(k in body for k in ("доставк", "shipping", "delivery", "dostaw", "wysyłk", "versand", "lieferung")):
                    pp_no_ship.append(p.get("offerId"))
                if not re.search(r"tab-reviews|woocommerce-reviews|id=[\"']reviews|jdgm|judge\.me|trustpilot|aggregaterating"
                                 r"|відгук|отзыв|opinie|bewertung|\breviews?\b",
                                 re.sub(r"(?is)<head\b.*?</head>", " ", main_content(html)), re.I):
                    pp_no_reviews.append(p.get("offerId"))
                for d, i in re.findall(r"(?is)<del[^>]*>(.*?)</del>\s*<ins[^>]*>(.*?)</ins>", html)[:1]:
                    a, b = extract_prices(html_to_text(d)), extract_prices(html_to_text(i))
                    if a and b and a[0] and (a[0] - b[0]) / a[0] > 0.5:
                        pp_deep.append(f"{p.get('offerId')} {a[0]:g}->{b[0]:g}")
                pc = re.search(r'itemCondition"?\s*:\s*"[^"]*?(New|Used|Refurbished|Damaged)Condition', html)
                if pc and p.get("condition") and pc.group(1).lower() != p["condition"].lower():
                    cond_bad.append(f"{p.get('offerId')} feed {p['condition']} vs page {pc.group(1).lower()}")
            fp = float(p.get("salePrice", p.get("price", {})).get("value", "nan"))
            label = f"{p.get('offerId')} {p.get('title', '')[:45]!r}"
            if st != 200:
                record("feed", "FAIL", f"{label} landing page", f"{link} -> HTTP {st}")
                continue
            if urlparse(final).path.rstrip("/") in ("", "/") and urlparse(link).path.rstrip("/"):
                record("feed", "FAIL", f"{label} landing page", f"redirects to homepage ({final})")
                continue
            page_price, avail = jsonld_offer(html)
            var_price, var_stock = woo_variation_offer(html, link)
            if var_price is not None:
                ok = abs(var_price - fp) < 0.01
                record("feed", "PASS" if ok else "FAIL", f"{label} price feed {fp:g} vs page variant {var_price:g}",
                       "" if ok else link)
                fa = p.get("availability", "").replace("_", "").replace(" ", "").lower()
                if (fa == "instock") != var_stock:
                    record("feed", "FAIL", f"{label} availability feed '{fa}' vs page variant in_stock={var_stock}")
                continue
            if page_price is None:
                txt = html_to_text(html)
                ok = any(abs(v - fp) < 0.01 for v in extract_prices(txt))
                record("feed", "PASS" if ok else "WARN", f"{label} price {fp:g}",
                       "found in page text" if ok else "no structured price on page and feed price not found in text")
            else:
                ok = abs(page_price - fp) < 0.01
                record("feed", "PASS" if ok else "FAIL", f"{label} price feed {fp:g} vs page {page_price:g}",
                       "" if ok else f"{link}")
            fa = p.get("availability", "").replace("_", "").replace(" ", "").lower()
            pa = avail.rsplit("/", 1)[-1].lower()
            if pa:
                ok = fa == pa or (fa == "instock" and pa == "instock") or (fa == "outofstock" and pa in ("outofstock", "soldout"))
                record("feed", "PASS" if ok else "FAIL", f"{label} availability feed '{fa}' vs page '{pa}'")

    # ---------------- checkout probe (WooCommerce): add one sampled simple product to the
    # cart, open checkout like a reviewer would, check policy links + the shipping charge
    if mid and online:
        section("7. Checkout - add a product to the cart, open checkout")
        st0, _, h0 = fetch(urljoin(home_url, "/cart/"))
        if st0 is None and "redirects" in h0:
            record("checkout", "WARN", "Empty cart page", "/cart/ <-> /checkout/ redirect loop when the cart is empty "
                   "('Exceeded 30 redirects') - harmless once a product is added, but a reviewer clicking the cart icon first sees an error")
        probed = False
        for p in sample:
            st, final, html = fetch(p.get("link", ""))
            pid = re.search(r"postid-(\d+)", html or "")
            if st != 200 or not pid or re.search(r'<form[^>]+class="[^"]*variations_form', html):
                continue
            SESSION.post(final, data={"add-to-cart": pid.group(1), "quantity": 1}, timeout=30)
            st, cf, ch = fetch(urljoin(home_url, "/checkout/"))
            if st != 200:
                record("checkout", "FAIL", "Checkout opens with a product in the cart", f"HTTP {st} {ch[:120]}")
                probed = True
                break
            linked = {classify(u, t) for u, t in links_from(ch, cf)}
            missing = [t for t in ("privacy", "returns", "shipping", "terms") if t not in linked]
            record("checkout", "PASS" if not missing else "WARN", "Policy links visible on the checkout page",
                   f"{unquote(cf)}" + (f" - missing: {missing}" if missing else ""))
            ct = html_to_text(ch)
            flat = [float(g["singleValue"]["flatRate"]["value"]) for sv in (shipping or {}).get("services", [])
                    for g in sv.get("rateGroups", []) if "flatRate" in g.get("singleValue", {})]
            tbl = [float(c["flatRate"]["value"]) for sv in (shipping or {}).get("services", []) for g in sv.get("rateGroups", [])
                   for r in g.get("mainTable", {}).get("rows", []) for c in r.get("cells", []) if "flatRate" in c]
            amounts = extract_prices(ct)
            for rate in flat:
                ok = any(abs(a - rate) < 0.01 for a in amounts)
                record("checkout", "PASS" if ok else "FAIL", f"MC flat shipping {rate:g} charged/shown at checkout",
                       "found" if ok else f"amounts at checkout: {sorted(set(amounts))[:8]} - Google sees {rate:g} in ads/listings, "
                       "the shopper is not charged it; switch MC to carrier rates or state/charge the same fee")
            if tbl:
                amounts_c = extract_prices(ct)
                hit = any(abs(a - v) < 0.01 for a in amounts_c for v in tbl)
                record("checkout", "PASS" if hit else "WARN", "Checkout shows a delivery cost from the MC rate table",
                       "found" if hit else f"amounts at checkout: {sorted(set(amounts_c))[:8]} - delivery is not priced at checkout; "
                       "the rate table must at least be published on the shipping page so the shopper sees it before paying")
            probed = True
            break
        if not probed:
            out("  (no simple WooCommerce product in the sample to add to the cart - check checkout manually)")

    if mid and online:
        record("feed", "WARN" if urgency_hits else "PASS", "No urgency tactics on sampled product pages (timers, 'only N left')",
               "; ".join(urgency_hits[:6]) + (" - remove countdown timers even if real (practitioners report them triggering reviews); "
                                         "stock counters only if they show true stock" if urgency_hits else ""))
        record("feed", "WARN" if badge_hits else "PASS", "No unverified security/trust badges on sampled product pages",
               "; ".join(badge_hits[:6]) + (" - remove any badge the store is not actually certified for" if badge_hits else ""))
        if pp_checked:
            record("feed", "WARN" if pp_no_links else "PASS", "Shipping + returns policies linked from product pages",
                   f"{len(pp_no_links)} of {pp_checked} sampled pages lack a link to both: {pp_no_links[:6]}" if pp_no_links
                   else f"{pp_checked} sampled pages")
            record("feed", "WARN" if pp_no_ship else "PASS", "Delivery info on the product page itself (near Add to cart)",
                   f"{len(pp_no_ship)} of {pp_checked} pages mention delivery only in header/footer: {pp_no_ship[:6]} - "
                   "add a short shipping/returns summary or tab with links" if pp_no_ship else f"{pp_checked} sampled pages")
            record("feed", "WARN" if pp_no_reviews else "PASS", "Reviews section on product pages",
                   f"{len(pp_no_reviews)} of {pp_checked} pages have no reviews block: {pp_no_reviews[:6]} - an empty "
                   "verified-buyer reviews widget is better than none" if pp_no_reviews else f"{pp_checked} sampled pages")
            record("feed", "WARN" if pp_deep else "PASS", "No strike-through discounts deeper than 50% on product pages",
                   ", ".join(pp_deep[:5]) if pp_deep else "")
            if cond_bad:
                record("feed", "FAIL", "Product condition feed = page", "; ".join(cond_bad[:5]))
            if no_returns_policy:
                record("feed", "WARN" if pp_no_nr else "PASS", "No-returns policy also stated on product pages",
                       f"{len(pp_no_nr)} of {pp_checked} pages don't say returns aren't accepted: {pp_no_nr[:6]} - "
                       "Google checks the product page separately from the policy page" if pp_no_nr else f"{pp_checked} sampled pages")

    # ---------------- summary - always FAIL first, then WARN, then PASS (user rule 2026-10-15)
    section("Summary (FAIL first, then WARN, then PASS)")
    ordered = sorted(RESULTS, key=lambda r: STATUS_ORDER[r[1]])
    for status in ("FAIL", "WARN", "PASS"):
        rows = [r for r in ordered if r[1] == status]
        out(f"{status}: {len(rows)}")
        for sec, _, check, ev in rows:
            out(f"  [{sec}] {check}" + (f" - {ev[:160]}" if ev else ""))
    out(f"\nPolicy page texts saved for manual reading: {page_dir.relative_to(WORKSPACE)}/")

    log = report_dir / f"policy_check_{today}.log"
    log.write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
    # machine-readable copy for the client PDF (scripts/policy_report_pdf.py) - same order
    facts = {"client": meta["name"], "slug": meta["slug"], "date": today, "domain": domain,
             "merchant_center_id": mid, "pages_checked": {k: v[0] for k, v in pages.items()},
             "results": [dict(section=r[0], status=r[1], check=r[2], evidence=r[3]) for r in ordered]}
    (report_dir / f"policy_check_{today}.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Log: {log.relative_to(WORKSPACE)}  (+ .json)")
    return 1 if any(r[1] == "FAIL" for r in RESULTS) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("client")
    ap.add_argument("--sample", type=int, default=10, help="products to check on the live site (default 10)")
    ap.add_argument("--seed", type=int, default=1)
    sys.exit(run(ap.parse_args()))


if __name__ == "__main__":
    main()
