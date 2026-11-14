#!/usr/bin/env python3
"""
55DigitalAI — Product Feed Optimization: Titles + Descriptions (both check + apply)
=============================================================
Purpose  : Two related workflows sharing the same keyword-mining
           foundation — real customer search terms, validated against
           Keyword Planner for standalone volume — and the same confirmed
           apply mechanism.

           MIGRATED (2026-09-17) off the sunset Content API for Shopping
           entirely, onto the Merchant API (`products.list`/`products.get`
           for reads, `productInputs.patch` for writes). Two things learned
           the hard way, both still true post-migration — read both before
           assuming a write persists:

           (1) DURABILITY IS NOT AUTOMATIC. The Merchant API models an
           account's data as multiple named data sources merged by an
           explicit rule — there is no built-in "manual edit always wins"
           behavior the old Content API implied. A write only shows up in
           the served product if the account's PRIMARY data source's rule
           actually pulls that field from an API-type data source; a rule
           that's still `takeFromDataSources: [{"self": true}]` (the
           default on an account that's never had this configured) will
           silently keep serving its own feed value forever, no matter how
           many times `apply` reports success. `find_write_target()`
           resolves the write destination *from that rule itself* — it
           does NOT guess by matching feedLabel/contentLanguage on the API
           source's own config, because a genuinely correct supplemental
           source doesn't carry that config, and doing so silently picks
           the wrong one the moment an account has more than one
           `input: "API"` data source (which happens exactly when someone
           sets this up correctly). If the owning primary's rule is
           self-only, `apply` stops with a clear, actionable error instead
           of writing somewhere that can never surface.

           (2) EVEN WITH THE RULE CONFIGURED CORRECTLY, some individual
           products can still get stuck — confirmed on 3 products across
           2-4 identical write attempts each, on an account whose merge
           rule was already set up right: `productInputs.patch` returns a
           clean 200 and the title never actually changes, while a
           description write on the SAME product succeeds. This was
           re-tested against both the old Content API and the new Merchant
           API on the identical stuck product and got the identical
           result, which rules out API version as the cause — it looks
           like a product/field-specific hold inside Merchant Center's own
           processing, independent of everything above. The confirmed,
           PERMANENT fallback when this happens is a manual edit via the
           Merchant Center UI, regardless of which API was used to try it.
           Do not add a retry loop around this — retrying doesn't clear it.

           Merchant API v1 access itself (separate from the two issues
           above) required the OAuth identity's Merchant Center aggregator
           account to complete its own homepage verification before
           `datasources.list`/`productInputs.patch` would work at all — if
           a fresh client account gets an access/registration error here
           that isn't one of the two documented failure modes above, check
           that first.

           TITLE MODE (`title fetch-candidates` / `title apply`).
           fetch-candidates finds two kinds of signal: (a) concepts with
           real search activity that aren't reflected in ANY current
           product title (PMax/Shopping only), and (b) real ACCOUNT-WIDE
           converting search terms with the client's own brand stripped
           out, ranked by conversions — the stronger signal for deciding
           which term should actually lead a restructured title, brand
           pushed right after it. `title apply` writes the approved title
           via `apply_field_updates` (see its docstring, and the two
           numbered findings in the MIGRATED note above) — same shared
           write path as describe apply, just for `field="title"`.

           DESCRIPTION MODE (`describe` subcommand) — same shared apply
           step (`apply_field_updates`, `field="description"`), gated the
           same way as every other apply step in this workspace — plan
           first, explicit approval, then --confirm. Description writes
           have been the more reliable of the two in practice (see finding
           (2) above — some individual products get stuck on `title`
           specifically, description on the same product hasn't shown the
           same problem), but neither is guaranteed without the account's
           merge rule already configured per finding (1).

           SCOPE CAVEAT (both modes): PMax does not expose which specific
           product a given search term actually converted/clicked on via
           the Ads API — search-term-to-SKU attribution inside PMax is not
           public. Both modes operate catalog-wide ("is this concept
           represented ANYWHERE" / "which search terms convert account-
           wide"), not per-SKU. Use human judgement (the product's own
           theme, or its individual conversion history) to decide which
           product a given keyword actually belongs to — see `describe`'s
           own docstring below for how this plays out in practice.

Usage    : python3 feed_title_optimizer.py title <client_slug> [--days 90] [--min-impressions 10]
           python3 feed_title_optimizer.py describe fetch-candidates <client_slug> --select best15
           python3 feed_title_optimizer.py describe apply <client_slug> --plan plan.json [--confirm]
Changelog: 2026-07-25  Initial version (title mode only, check-only) — tested live against a real client account.
           2026-09-16  Added `describe` mode (fetch-candidates + apply) — built from a live
                       session manually rewriting 8 real client product descriptions with
                       conversion-weighted keywords, then confirmed the apply path persists
                       (see DESCRIPTION MODE note above).
           2026-09-16  Added product-selection scoping (`--select all|best5|best15|best30|ids`,
                       shared `resolve_product_selection()`) to title mode too, matching describe
                       mode. Added `title apply`, using the same confirmed-persistent
                       `Products.insert` mechanism as describe apply, plus a new account-wide,
                       brand-stripped, conversion-ranked generic-term signal
                       (`fetch_account_search_terms_ranked` + `load_brand_terms` +
                       `filter_generic_terms`) to drive which term leads a restructured title.
           2026-09-17  Migrated off the Content API for Shopping entirely,
                       onto the Merchant API: `products.list`/`products.get`
                       for reads, `productInputs.patch` (via
                       `apply_field_updates`) for writes, resolving the
                       write destination from the owning primary data
                       source's own merge rule (`find_write_target()`) —
                       see the two numbered findings above for why this
                       isn't a drop-in URL swap. `plan.json`'s `product_id`
                       is now the Merchant API key format
                       (`contentLanguage~feedLabel~offerId`, e.g.
                       `en~US~sku123`) instead of the old Content API
                       composite id (`online:en:US:sku123`) —
                       `print_product_selection()`'s "product id" column
                       already prints the new format, so build plan.json
                       from that column as before.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402
from ga4_reports import get_credentials, run_report, REPORTS, GA4_DATA_API  # noqa: E402
from keyword_research import GEO_TARGET_CONSTANTS, LANGUAGE_CONSTANTS, fetch_historical_metrics, micros  # noqa: E402
from pmax_brand_generic_audit import get_pmax_campaigns, get_search_terms as get_pmax_search_terms, parse_brand_terms  # noqa: E402

from google.ads.googleads.client import GoogleAdsClient

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"
PRODUCTS_API = "https://merchantapi.googleapis.com/products/v1"
DATASOURCES_API = "https://merchantapi.googleapis.com/datasources/v1"
# Common short function words per language, so tokenize() doesn't treat them as "meaningful" words
# when checking title coverage. Not exhaustive — extend per-language as a new client's account
# surfaces obvious gaps (e.g. a stopword slipping through as a false "missing concept").
STOPWORDS = {
    # Ukrainian
    "з", "та", "і", "й", "на", "у", "в", "до", "за", "від", "як", "що", "це", "для", "по", "не", "або",
    # Polish
    "i", "w", "z", "na", "do", "za", "od", "po", "dla", "nie", "lub", "oraz", "się", "są", "jest", "to",
    # German
    "und", "oder", "für", "mit", "der", "die", "das", "von", "nicht", "ist", "ein", "eine", "im", "am",
    # French
    "et", "ou", "pour", "avec", "le", "la", "de", "du", "ne", "pas", "est", "un", "une", "les", "des",
    # Spanish
    "y", "o", "para", "con", "el", "no", "es", "un", "una", "los", "las", "del",
    # Italian
    "e", "o", "per", "con", "il", "di", "non", "è", "un", "una", "gli", "le",
    # English
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with",
}
# Terms that look like generic descriptive gaps by pure word-coverage but are not product descriptors:
# (a) another business's brand name that happens to contain a category word as a substring, (b) a
# navigational/local query, or (c) a business/place noun (e.g. "brewery", "shop") rather than a product
# attribute. None of these belong in a title regardless of search volume. This list ships EMPTY on
# purpose: extend it per account as new false positives are found (add the lowercase term), it is never
# comprehensive. NAVIGATIONAL_MARKERS is a starter set in several languages (address, phone, hours).
KNOWN_BAD_TERMS = set()
NAVIGATIONAL_MARKERS = {"address", "phone", "opening hours", "near me", "adres", "telefon", "godziny otwarcia",
                        "адрес", "адреса", "телефон", "графік", "режим роботи", "öffnungszeiten"}


def get_ads_client():
    return GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))


def tokenize(text):
    # [^\W_]+ matches Unicode word characters (letters in ANY language + digits), minus underscore —
    # NOT a hardcoded [a-zа-я] character class. The old explicit-Cyrillic-only version silently broke
    # on Polish diacritics (ą ć ę ł ń ó ś ź ż) and any other accented European text (German ä ö ü ß,
    # French é è ê ç, Spanish ñ, etc.) — those characters fell outside the class entirely, splitting
    # words like "łóżko" into fragments at every accented letter. re.findall on a Python 3 str pattern
    # is Unicode-aware by default, so this one pattern now works correctly for every European language.
    words = re.findall(r"[^\W_]+", text.lower(), re.UNICODE)
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def fetch_pmax_shopping_search_terms(ads_client, customer_id, date_from, date_to):
    ga_service = ads_client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign_search_term_view.search_term, campaign.name,
               metrics.impressions, metrics.clicks, metrics.conversions
        FROM campaign_search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
          AND campaign.advertising_channel_type IN ('SHOPPING', 'PERFORMANCE_MAX')
    """
    terms = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        term = row.campaign_search_term_view.search_term
        d = terms.setdefault(term, {"impressions": 0, "clicks": 0, "conversions": 0.0})
        d["impressions"] += row.metrics.impressions
        d["clicks"] += row.metrics.clicks
        d["conversions"] += row.metrics.conversions
    return terms


def _get_with_retry(url, headers, params=None, retries=4):
    """Shared GET-with-retry for the Merchant API. Two distinct transient
    failure modes confirmed live on a real client account against the old, now-migrated-off
    Content API, both cleared by retrying: (a) a 410 misleadingly worded as a full API-sunset
    error, and (b) — more dangerous — an HTTP 200 whose JSON body is actually an error
    object (`{"error": {...}}`), not the real resource. (b) silently broke
    a title apply run: get_product's old status-code-only check treated it
    as a valid product, an insert built from it re-submitted the error
    object as the product body, and Google correctly 400'd the resulting
    garbage payload — leaving the product's title untouched with no clear
    signal why. Checking the body shape, not just the status code, kept
    defensively for the Merchant API too since nothing guarantees the same
    failure modes can't recur."""
    last = None
    for attempt in range(retries):
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 200 and "error" not in r.json():
            return r
        last = r
        if attempt < retries - 1:
            time.sleep(3)
    body = last.json() if last.status_code == 200 else last.text[:500]
    raise RuntimeError(f"Merchant API error (status {last.status_code}): {body}")


def product_key(content_language, feed_label, offer_id):
    """The Merchant API's product identifier: `content_language~feed_label~offer_id`. Used as the
    last path segment for both `accounts/{account}/products/{key}` (read-only, merged product) and
    `accounts/{account}/productInputs/{key}` (the input you write, before rules/merging)."""
    return f"{content_language}~{feed_label}~{offer_id}"


def fetch_product_titles(merchant_id, headers):
    titles = []
    page_token = None
    while True:
        params = {"pageSize": 250}
        if page_token:
            params["pageToken"] = page_token
        r = _get_with_retry(f"{PRODUCTS_API}/accounts/{merchant_id}/products", headers, params)
        data = r.json()
        for p in data.get("products", []):
            titles.append(p.get("productAttributes", {}).get("title", ""))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return titles


def fetch_all_products(merchant_id, headers):
    """Full product resources (not just titles) — used by describe mode for
    both the id-based and best-N-by-revenue selection paths, and as the
    base object the apply step's write-target/plan-key logic keys off of.
    `title`/`description`/`id` are flattened onto the returned dict for
    convenience — `id` becomes the Merchant API's own resource `name` (not
    a Content API composite id, which no longer exists), used for the
    same dedupe-by-identity purpose as before."""
    products = []
    page_token = None
    while True:
        params = {"pageSize": 250}
        if page_token:
            params["pageToken"] = page_token
        r = _get_with_retry(f"{PRODUCTS_API}/accounts/{merchant_id}/products", headers, params)
        data = r.json()
        for p in data.get("products", []):
            attrs = p.get("productAttributes", {})
            p["title"] = attrs.get("title", "")
            p["description"] = attrs.get("description", "")
            p["id"] = p.get("name", "")
            products.append(p)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return products


def get_product(merchant_id, headers, key, retries=4):
    """Single-product GET (the merged/served product, read-only) with the same retry +
    body-shape check as _get_with_retry. `key` is the Merchant API product key
    (`contentLanguage~feedLabel~offerId`), not the old Content API composite id."""
    last = None
    for attempt in range(retries):
        r = requests.get(f"{PRODUCTS_API}/accounts/{merchant_id}/products/{key}", headers=headers)
        if r.status_code == 200 and "error" not in r.json():
            return r.json()
        last = r
        if attempt < retries - 1:
            time.sleep(3)
    body = last.json() if last.status_code == 200 else last.text[:300]
    raise RuntimeError(f"GET {key} failed after {retries} attempts (status {last.status_code}): {body}")


def list_data_sources(merchant_id, headers):
    data_sources = []
    page_token = None
    while True:
        params = {"pageSize": 250}
        if page_token:
            params["pageToken"] = page_token
        r = _get_with_retry(f"{DATASOURCES_API}/accounts/{merchant_id}/dataSources", headers, params)
        data = r.json()
        data_sources.extend(data.get("dataSources", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return data_sources


def find_write_target(merchant_id, headers, content_language, feed_label):
    """Resolve where `apply_field_updates` should actually write title/description, by reading
    the *rule* rather than guessing a data source independently. A genuinely correct supplemental
    source (one with `supplementalProductDataSource` set, referenced by the owning primary's own
    `defaultRule`) has no `primaryProductDataSource.contentLanguage`/`feedLabel` of its own to
    match against — matching on those fields silently picks the wrong data source the moment an
    account has more than one `input: "API"` source, which happens exactly when someone sets this
    up correctly in the Merchant Center UI.

    Steps: find the primary data source that owns this contentLanguage/feedLabel, read its
    `defaultRule.takeFromDataSources`, and use the first non-`self` entry as the write target —
    that IS the account's actual configured override path, not a guess. Raises a clear, actionable
    error if the owning primary's rule is self-only (no override path exists yet — confirmed live
    to let writes succeed with a clean 200 and never surface, with no error anywhere queryable)."""
    data_sources = list_data_sources(merchant_id, headers)
    by_name = {d["name"]: d for d in data_sources}

    owning_primary = None
    for d in data_sources:
        primary = d.get("primaryProductDataSource")
        if primary and primary.get("contentLanguage") == content_language and primary.get("feedLabel") == feed_label:
            owning_primary = d
            break
    if owning_primary is None:
        raise RuntimeError(
            f"No primary data source found for contentLanguage={content_language!r}, "
            f"feedLabel={feed_label!r} on this account."
        )

    rule = owning_primary.get("primaryProductDataSource", {}).get("defaultRule", {})
    takes_from = rule.get("takeFromDataSources", [])
    override_ref = next((t for t in takes_from if t.get("supplementalDataSourceName")), None)
    if override_ref is None:
        raise RuntimeError(
            f"Primary data source \"{owning_primary.get('displayName')}\" ({owning_primary['name']})'s "
            f"merge rule only takes attributes from itself — there is no override path configured for "
            f"this account yet. Writes would return a clean 200 and never surface in the served product, "
            f"with no error anywhere queryable (confirmed live). Fix in Merchant Center: Settings > Data "
            f"sources > that primary source > rules > add a supplemental API data source above self."
        )
    write_target = by_name.get(override_ref["supplementalDataSourceName"])
    if write_target is None:
        raise RuntimeError(
            f"Primary data source's rule references {override_ref['supplementalDataSourceName']!r}, "
            f"but no data source with that name was found on this account."
        )
    return write_target, owning_primary


def normalize_for_match(text):
    return set(tokenize(text))


def match_ga4_items_to_products(item_names, products):
    """Best-effort fuzzy match of a GA4 itemName (from top_products) to a
    Merchant Center product by token overlap on title. NOT reliable — GA4's
    item_name and the live MC title can diverge (renamed/repackaged SKUs, or
    the analytics data layer using a different label than the feed). Confirmed
    live on a real client account (2026-09-16): 2 of 8 GA4 top-seller names had no matching MC
    title at all. Always report unmatched items explicitly rather than
    guessing or silently dropping them — a human needs to resolve those by
    hand (check the item's real SKU/ID in GA4, or ask the client)."""
    matched, unmatched = {}, []
    for name in item_names:
        name_tokens = normalize_for_match(name)
        if not name_tokens:
            unmatched.append(name)
            continue
        best, best_score = None, 0.0
        for p in products:
            title_tokens = normalize_for_match(p.get("title", ""))
            if not title_tokens:
                continue
            overlap = len(name_tokens & title_tokens) / len(name_tokens)
            if overlap > best_score:
                best, best_score = p, overlap
        if best and best_score >= 0.6:
            matched[name] = best
        else:
            unmatched.append(name)
    return matched, unmatched


def select_best_products_by_revenue(client_meta, n, days):
    """Top-N products by GA4 revenue (`top_products` report), for describe
    mode's --select best5/best15/best30. Returns GA4 itemNames in revenue
    order — caller still has to match these to real Merchant Center products
    (see match_ga4_items_to_products; matching is not guaranteed)."""
    property_id = client_meta.get("ga4_property_id")
    if not property_id:
        raise RuntimeError(f"No ga4_property_id configured for this client — can't rank by revenue.")
    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)
    data = run_report(property_id, headers, REPORTS["top_products"], date_from, date_to, limit=n)
    names = []
    for row in data.get("rows", []):
        names.append(row["dimensionValues"][0]["value"])
    return names


ADS_RANK_METRICS = {"impressions", "clicks", "conversions", "conversions_value"}


def select_best_offer_ids_by_ads_metric(ads_client, customer_id, n, days, metric):
    """Top-N Merchant Center offerIds by a real Google Ads Shopping/PMax
    metric (shopping_performance_view), for --select best5/15/30 with
    --rank-by impressions|clicks|conversions|conversions_value.

    Deliberately a different, more reliable path than
    select_best_products_by_revenue()'s GA4 route: shopping_performance_view's
    segments.product_item_id IS the Merchant Center offerId directly — no
    fuzzy name-matching needed at all, unlike GA4's itemName (see
    match_ga4_items_to_products' documented unreliability — 2 of 8 top-revenue
    GA4 names had no matching feed title, confirmed live on a real client account). Added
    2026-09-16 after manually ranking a random 90-day, >20-click product set
    this same way for a live test batch."""
    if metric not in ADS_RANK_METRICS:
        raise ValueError(f"metric must be one of {ADS_RANK_METRICS}, got {metric!r}")
    ga_service = ads_client.get_service("GoogleAdsService")
    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=days))
    date_to = str(today)
    query = f"""
        SELECT segments.product_item_id, metrics.impressions, metrics.clicks,
               metrics.conversions, metrics.conversions_value
        FROM shopping_performance_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    agg = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        pid = row.segments.product_item_id
        if not pid:
            continue
        d = agg.setdefault(pid, {"impressions": 0, "clicks": 0, "conversions": 0.0, "conversions_value": 0.0})
        d["impressions"] += row.metrics.impressions
        d["clicks"] += row.metrics.clicks
        d["conversions"] += row.metrics.conversions
        d["conversions_value"] += row.metrics.conversions_value
    ranked = sorted(agg.items(), key=lambda kv: kv[1][metric], reverse=True)
    return [offer_id for offer_id, _ in ranked[:n]]


def fetch_search_terms_ranked(ads_client, customer_id, date_from, date_to, min_impressions=5):
    """Real PMax search terms, ranked by conversions, for describe mode's
    keyword-candidate list — a high-converting term should get more
    prominence in a description than a high-impression-but-low-converting
    one. Fetched the same way /pmax-audit does it (enumerate live PMax
    campaigns via advertising_channel_type = 'PERFORMANCE_MAX' AND
    status = 'ENABLED', then pull campaign_search_term_view per campaign
    id) rather than title mode's blanket advertising_channel_type IN
    ('SHOPPING','PERFORMANCE_MAX') query — campaign-scoped is the version
    already proven live in production (the scheduled Tue/Fri PMax audits),
    so describe mode reuses it instead of a second, untested query shape."""
    ga_service = ads_client.get_service("GoogleAdsService")
    campaigns = get_pmax_campaigns(ga_service, customer_id)
    terms = {}
    for c in campaigns:
        for t in get_pmax_search_terms(ga_service, customer_id, c["id"], date_from, date_to):
            d = terms.setdefault(t["term"], {"impressions": 0, "clicks": 0, "conversions": 0.0})
            d["impressions"] += t["impressions"]
            d["clicks"] += t["clicks"]
            d["conversions"] += t["conversions"]
    rows = []
    for term, m in terms.items():
        if m["impressions"] < min_impressions:
            continue
        conv_rate = (m["clicks"] and m["conversions"] / m["clicks"]) or 0.0
        rows.append({"term": term, **m, "conv_rate": conv_rate})
    rows.sort(key=lambda r: r["conversions"], reverse=True)
    return rows


def fetch_account_search_terms_ranked(ads_client, customer_id, date_from, date_to, min_impressions=5):
    """FULL ACCOUNT search terms (every campaign type, not just PMax/Shopping),
    ranked by conversions — for Title Mode's "what generic, non-branded term
    is actually converting account-wide, that a specific product's title
    could lead with." Same campaign_search_term_view resource as the PMax-only
    helpers above, just without the advertising_channel_type filter."""
    ga_service = ads_client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign_search_term_view.search_term,
               metrics.impressions, metrics.clicks, metrics.conversions
        FROM campaign_search_term_view
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
    """
    terms = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        term = row.campaign_search_term_view.search_term
        d = terms.setdefault(term, {"impressions": 0, "clicks": 0, "conversions": 0.0})
        d["impressions"] += row.metrics.impressions
        d["clicks"] += row.metrics.clicks
        d["conversions"] += row.metrics.conversions
    rows = []
    for term, m in terms.items():
        if m["impressions"] < min_impressions:
            continue
        conv_rate = (m["clicks"] and m["conversions"] / m["clicks"]) or 0.0
        rows.append({"term": term, **m, "conv_rate": conv_rate})
    rows.sort(key=lambda r: r["conversions"], reverse=True)
    return rows


def load_brand_terms(client_meta):
    """Brand tokens for this client, used to separate "generic" (non-branded)
    search terms from branded ones. Reuses pmax_audit.py's own brief parser
    (its '## Brand Terms' section) so there's one source of truth for what
    counts as a brand term, not a second copy invented here. Falls back to
    just the client's registry name if no brief/section exists — better than
    hard-failing, since not every client has a branded PMax campaign (the
    only thing that currently requires the brief to have this section)."""
    brief_path = Path(__file__).resolve().parent.parent / "clients" / client_meta["slug"] / "client-brief.md"
    if brief_path.exists():
        terms = parse_brand_terms(brief_path.read_text())
        if terms:
            return [t.lower() for t in terms]
    return [client_meta["name"].lower()]


def filter_generic_terms(rows, brand_terms):
    """Drop any search term that contains a brand token — what's left is
    "generic" in the sense Title Mode's word-order rule cares about: a term
    that describes the PRODUCT, not the company, and is therefore a
    candidate to lead a title with brand pushed after it."""
    out = []
    for r in rows:
        term_l = r["term"].lower()
        if any(b in term_l for b in brand_terms):
            continue
        out.append(r)
    return out


def build_title_token_corpus(titles):
    corpus = set()
    for t in titles:
        corpus.update(tokenize(t))
    return corpus


def find_missing_concepts(search_terms, title_corpus, min_impressions):
    candidates = []
    for term, m in search_terms.items():
        if m["impressions"] < min_impressions:
            continue
        term_l = term.lower()
        if any(bad in term_l for bad in KNOWN_BAD_TERMS) or any(nav in term_l for nav in NAVIGATIONAL_MARKERS):
            continue
        tokens = tokenize(term)
        if not tokens:
            continue
        covered = sum(1 for t in tokens if t in title_corpus)
        coverage = covered / len(tokens)
        if coverage < 0.5:  # majority of the term's meaningful words aren't in any title
            candidates.append({"term": term, **m, "coverage": coverage})
    candidates.sort(key=lambda c: c["impressions"], reverse=True)
    return candidates


def validate_with_keyword_planner(ads_client, client, customer_id, terms, geo, language):
    if not terms:
        return {}
    network_enum = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    response = fetch_historical_metrics(client, ads_client, customer_id, terms, geo, language, network_enum)
    out = {}
    for result in response.results:
        m = result.keyword_metrics
        out[result.text.lower()] = {
            "avg_monthly_searches": m.avg_monthly_searches if m.avg_monthly_searches else 0,
            "competition": m.competition.name if m.competition is not None else "n/a",
        }
    return out


def print_table(headers, rows):
    widths = [max(len(str(h)), 10) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(str(c)))
    line = " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def cmd_title(args):
    client_meta = resolve(args.client)
    merchant_id = client_meta.get("merchant_center_id")
    if not merchant_id:
        print(f"No Merchant Center account configured for '{args.client}' — this tool needs a product feed.")
        sys.exit(2)

    country = client_meta.get("country")
    geo = GEO_TARGET_CONSTANTS.get(country)
    language = LANGUAGE_CONSTANTS.get(country)
    if not geo or not language:
        print(f"No geo/language constant configured for country '{country}' in keyword_research.py.")
        sys.exit(2)

    ads_client = get_ads_client()
    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    today = datetime.utcnow().date()
    date_from = str(today - timedelta(days=args.days))
    date_to = str(today)

    print(f"Client   : {client_meta['name']} ({args.client})")
    print(f"Period   : {date_from} -> {date_to} ({args.days} days)")
    print(f"Merchant : {merchant_id}")
    print(f"Selection: {args.select}" + (f" (ids: {args.ids})" if args.select == "ids" else "") + "\n")

    selected = resolve_product_selection(args.select, args.ids, client_meta, merchant_id, headers, args.days, rank_by=args.rank_by)
    print_product_selection(selected)
    print("\n(Coverage checking below still scans the FULL catalog's titles, regardless of selection above —")
    print("a term already covered by some other product's title genuinely isn't a gap, even if that other")
    print("product wasn't in your selection. The selection instead scopes which product(s) get an actual")
    print("restructuring suggestion once a gap is found — see Step 5 in the command file.)\n")

    print("Pulling PMax + Shopping search terms...")
    search_terms = fetch_pmax_shopping_search_terms(ads_client, client_meta["customer_id"], date_from, date_to)
    print(f"  {len(search_terms)} distinct search terms found")

    print("Pulling current product titles from Merchant Center...")
    titles = fetch_product_titles(merchant_id, headers)
    print(f"  {len(titles)} product titles found")

    title_corpus = build_title_token_corpus(titles)
    print(f"  {len(title_corpus)} distinct meaningful words across all titles\n")

    candidates = find_missing_concepts(search_terms, title_corpus, args.min_impressions)
    if not candidates:
        print(f"No search terms with >= {args.min_impressions} impressions were found missing from the title corpus.")
        return

    print(f"{len(candidates)} candidate term(s) have real account search activity but aren't reflected in any")
    print("current product title. Validating each against Keyword Planner for standalone search volume...\n")

    top_candidates = candidates[: args.top]
    kw_data = validate_with_keyword_planner(ads_client, ads_client, client_meta["customer_id"],
                                             [c["term"] for c in top_candidates], geo, language)

    rows = []
    for c in top_candidates:
        kw = kw_data.get(c["term"].lower(), {})
        vol = kw.get("avg_monthly_searches", "n/a")
        comp = kw.get("competition", "n/a")
        rows.append([c["term"], c["impressions"], c["clicks"], f"{c['conversions']:.1f}", vol, comp])
    print_table(["search term", "impressions (acct)", "clicks (acct)", "conversions (acct)", "avg monthly vol (KWP)", "competition"], rows)

    no_kwp_data = [c["term"] for c in top_candidates if c["term"].lower() not in kw_data]
    if no_kwp_data:
        print(f"\nNo Keyword Planner data for: {', '.join(no_kwp_data)} (too low standalone volume, or too long-tail)")

    print("\nWARNING — KNOWN_BAD_TERMS/NAVIGATIONAL_MARKERS filters out previously-caught false positives (a")
    print("competitor brand name that happens to contain a category word, a business/place noun, or a navigational")
    print("query like \"...address\") — but that list is NOT comprehensive, it only")
    print("grows as new clients surface new false positives. Still read every row before recommending it; a new")
    print("client's account will surface new categories of noise this list hasn't seen yet.")

    print("\nNOTE: this is catalog-wide — PMax doesn't expose which specific product a search term converted on via")
    print("the API, so these are concepts worth adding to SOME product's title, not an automated per-SKU assignment.")
    print("Use judgement (or the product's own search-term/conversion history) to pick the right SKU per term.")

    print("\n--- Top converting GENERIC (non-branded) search terms, full account, all campaign types ---")
    brand_terms = load_brand_terms(client_meta)
    print(f"Brand tokens excluded: {', '.join(brand_terms)}\n")
    account_terms = fetch_account_search_terms_ranked(ads_client, client_meta["customer_id"], date_from, date_to,
                                                        min_impressions=args.min_impressions)
    generic_terms = filter_generic_terms(account_terms, brand_terms)
    top_generic = generic_terms[: args.top]
    if top_generic:
        gen_rows = [[r["term"], r["impressions"], r["clicks"], f"{r['conversions']:.1f}", f"{r['conv_rate']*100:.1f}%"]
                    for r in top_generic]
        print_table(["search term", "impressions", "clicks", "conversions", "conv. rate"], gen_rows)
        print("\nThis is a real-conversion signal, not just an impression-based coverage gap — for the word-order")
        print("decision in Step 5, a term that shows up here for a product already in your selection is a strong")
        print("candidate to lead that product's title with, brand pushed to right after it (see Step 5's rule:")
        print("new title = \"{term} {brand} {remaining distinguishing attributes}\" — never drop the attributes")
        print("that make one SKU distinct from a sibling variant, e.g. pack size or a named style/flavor).")
    else:
        print("No generic (non-branded) terms with real search activity found in this window.")

    print("\nNOTE on the apply step below: title overrides go through the same apply_field_updates path")
    print("as Description Mode (Merchant API productInputs.patch) — see the module docstring's two")
    print("numbered findings before trusting a title write here without checking it actually stuck.")


def resolve_product_selection(select, ids_arg, client_meta, merchant_id, headers, days, rank_by="revenue"):
    """Shared by both modes — 'how many/which products to optimize' is the same
    question whether the output is a new title or a new description, so both
    `title` and `describe fetch-candidates` ask it the same way and resolve it
    here rather than each having their own copy of this logic.

    `rank_by` controls what "best" means for best5/15/30 — this used to be
    hardcoded to GA4 revenue with no way to pick anything else. Added
    2026-09-16: 'revenue' keeps the original GA4 top_products path (real
    revenue, but subject to the documented itemName-matching unreliability);
    'impressions'/'clicks'/'conversions'/'conversions_value' use Google Ads'
    own shopping_performance_view instead, which maps a Merchant Center
    offerId directly — no fuzzy matching needed at all. There's no single
    right default: revenue answers "which products make us the most money,"
    clicks/impressions answer "which products already get real traffic
    worth polishing," conversions/conversions_value answers "which products
    already sell, worth reinforcing." Ask the user which one fits their
    actual goal rather than assuming — see the command file's Step 0."""
    if select == "all":
        print("WARNING: this will process the ENTIRE feed. That can mean a large amount of")
        print("output/tokens for a big catalog — best5/best15/best30 or explicit --ids is usually a")
        print("better default unless full-catalog coverage is genuinely what's needed.\n")
        return fetch_all_products(merchant_id, headers)

    if select == "ids":
        if not ids_arg:
            print("--ids is required when --select ids (comma-separated Merchant Center product IDs or offerIds).")
            sys.exit(2)
        ids = [i.strip() for i in ids_arg.split(",") if i.strip()]
        # Accept either the full Merchant API key ("uk~FEEDLABEL~1936") or just the bare offerId
        # ("1936") — resolve bare offerIds against the full product list, since that's the shorter
        # form a human (or Claude reading a GA4/analysis table) will naturally reach for. Split on
        # "~" now, not ":" — the old Content API composite id used ":", the Merchant API key uses "~".
        needs_resolve = [i for i in ids if "~" not in i]
        offer_to_full = {}
        if needs_resolve:
            all_products = fetch_all_products(merchant_id, headers)
            offer_to_full = {p.get("offerId"): p for p in all_products}
        selected = []
        for pid in ids:
            if "~" not in pid:
                p = offer_to_full.get(pid)
                if not p:
                    print(f"WARNING: offerId '{pid}' not found in the feed — skipping.")
                    continue
                selected.append(p)
            else:
                p = get_product(merchant_id, headers, pid)
                attrs = p.get("productAttributes", {})
                p["title"] = attrs.get("title", "")
                p["description"] = attrs.get("description", "")
                p["id"] = p.get("name", "")
                selected.append(p)
        return selected

    n = {"best5": 5, "best15": 15, "best30": 30}[select]

    if rank_by in ADS_RANK_METRICS:
        print(f"Pulling top {n} products by Google Ads {rank_by} (last {days} days, shopping_performance_view)...")
        ads_client = get_ads_client()
        offer_ids = select_best_offer_ids_by_ads_metric(ads_client, client_meta["customer_id"], n, days, rank_by)
        products = fetch_all_products(merchant_id, headers)
        by_offer_id = {p.get("offerId"): p for p in products}
        selected, unmatched = [], []
        for offer_id in offer_ids:
            p = by_offer_id.get(offer_id)
            if p:
                selected.append(p)
            else:
                unmatched.append(offer_id)
        if unmatched:
            print(f"\n{len(unmatched)} of {n} top-{rank_by} offerId(s) have Ads performance history but are no")
            print("longer in the live Merchant Center feed (likely discontinued/delisted) — resolve manually:")
            for offer_id in unmatched:
                print(f"  - {offer_id}")
        return selected

    print(f"Pulling top {n} products by GA4 revenue (last {days} days)...")
    item_names = select_best_products_by_revenue(client_meta, n, days)
    products = fetch_all_products(merchant_id, headers)
    matched, unmatched = match_ga4_items_to_products(item_names, products)
    # Dedupe by product id — two different GA4 item names can legitimately match the same
    # live product (e.g. a renamed SKU showing up under both its old and new name across the
    # date range), and without this the same product would print twice.
    seen_ids, selected = set(), []
    for p in matched.values():
        if p.get("id") not in seen_ids:
            seen_ids.add(p.get("id"))
            selected.append(p)
    if unmatched:
        print(f"\n{len(unmatched)} of {n} top-revenue GA4 product name(s) could NOT be matched to a live")
        print("Merchant Center title (renamed/repackaged SKU, or the analytics label just differs from")
        print("the feed title) — resolve these manually, don't guess:")
        for name in unmatched:
            print(f"  - {name}")
    return selected


def print_product_selection(selected):
    """The "product id" column is the Merchant API key (`contentLanguage~feedLabel~offerId`) —
    paste this exact value into plan.json's `product_id` field for the apply step, not the
    `name` field (that's the full resource path, `accounts/{account}/products/{key}`)."""
    print(f"\n{len(selected)} product(s) selected:\n")
    rows = []
    for p in selected:
        key = product_key(p.get("contentLanguage", "?"), p.get("feedLabel", "?"), p.get("offerId", "?"))
        price = p.get("productAttributes", {}).get("price", {})
        amount = float(price.get("amountMicros", 0)) / 1_000_000 if price.get("amountMicros") else "?"
        rows.append([p.get("offerId", "?"), key, p.get("title", "")[:60],
                     f"{amount} {price.get('currencyCode', '')}",
                     (p.get("description", "") or "")[:50]])
    print_table(["offerId", "product id", "title", "price", "current description (truncated)"], rows)


def cmd_describe_fetch_candidates(args):
    """Step 1 of describe mode. Prints (a) the selected product set — from
    the whole feed, GA4's best N by revenue, or explicit IDs — and (b) real
    search terms ranked by conversions, as the raw material for Claude to
    turn into an interactive keyword-selection step with the user (see the
    /feed-title-optimizer command file's Description Mode section for the
    actual conversation flow — that part is judgement-driven, not scripted)."""
    client_meta = resolve(args.client)
    merchant_id = client_meta.get("merchant_center_id")
    if not merchant_id:
        print(f"No Merchant Center account configured for '{args.client}' — this tool needs a product feed.")
        sys.exit(2)

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    print(f"Client   : {client_meta['name']} ({args.client})")
    print(f"Merchant : {merchant_id}")
    print(f"Selection: {args.select}" + (f" (ids: {args.ids})" if args.select == "ids" else "") + "\n")

    selected = resolve_product_selection(args.select, args.ids, client_meta, merchant_id, headers, args.days, rank_by=args.rank_by)
    print_product_selection(selected)

    country = client_meta.get("country")
    geo = GEO_TARGET_CONSTANTS.get(country)
    language = LANGUAGE_CONSTANTS.get(country)
    if geo and language:
        ads_client = get_ads_client()
        today = datetime.utcnow().date()
        date_from = str(today - timedelta(days=args.days))
        date_to = str(today)
        print(f"\nPulling search terms ranked by conversions (last {args.days} days)...")
        ranked = fetch_search_terms_ranked(ads_client, client_meta["customer_id"], date_from, date_to,
                                            min_impressions=args.min_impressions)
        print(f"{len(ranked)} term(s) with >= {args.min_impressions} impressions:\n")
        kw_rows = [[r["term"], r["impressions"], r["clicks"], f"{r['conversions']:.1f}", f"{r['conv_rate']*100:.1f}%"]
                   for r in ranked[: args.top]]
        print_table(["search term", "impressions", "clicks", "conversions", "conv. rate"], kw_rows)
    else:
        print(f"\nNo geo/language constant for country '{country}' — skipping search-term keyword pull.")

    print("\nNEXT: this is catalog-wide search-term data (PMax doesn't expose which SKU a term actually")
    print("converted on) — match each keyword to the product(s) it actually describes by judgement, the")
    print("same way title suggestions are matched to a SKU in title mode. Then either ask the user which")
    print("keywords they want as primary, or offer this ranked list and let them pick. Ordering rule: a")
    print("keyword's conversion count should drive both how early it appears in the description AND how")
    print("many times it's repeated — the top-converting keyword goes first (and can be used twice), a")
    print("low-converting keyword goes later and is mentioned once. Write plan.json as a list of")
    print('{"product_id": "<value>", "description": "<new text>"} where <value> is exactly the "product id"')
    print("column value from the selection table above (not offerId) — show it to the user for explicit")
    print("approval before running `describe apply --confirm`.")


def apply_field_updates(client_meta, plan_path, field, confirm, extra_note=None):
    """Shared apply mechanics for both modes — write ONLY the given field (title or description)
    via `productInputs.patch`'s partial-update `updateMask` (no more GET-modify-POST-insert of the
    whole product; the Merchant API's write resource is a true partial update), targeting whichever
    data source the owning primary feed's own merge rule actually pulls overrides from (see
    `find_write_target()`), then poll to confirm the write actually propagated rather than trusting
    the immediate 200 response alone. `plan_path`'s `product_id` is the Merchant API key
    (`contentLanguage~feedLabel~offerId`) — see `print_product_selection()`.

    DURABILITY IS NOT AUTOMATIC — see the module docstring's two numbered findings before assuming
    this always works: (1) requires the account's primary data source rule to already reference an
    API-type data source (find_write_target raises a clear error if not, rather than writing
    somewhere that can never surface), and (2) even with that configured, some individual products
    can still get stuck on `title` specifically for reasons independent of API/config — confirmed to
    require a manual Merchant Center UI edit as the permanent fallback in that case."""
    merchant_id = client_meta.get("merchant_center_id")
    if not merchant_id:
        print(f"No Merchant Center account configured for '{client_meta['slug']}'.")
        sys.exit(2)

    plan = json.loads(Path(plan_path).read_text())
    if not plan:
        print("Plan is empty — nothing to do.")
        return

    print(f"Client : {client_meta['name']} ({client_meta['slug']})")
    print(f"Plan   : {len(plan)} product {field}(s) from {plan_path}\n")
    for item in plan:
        print(f"  {item['product_id']}: {item[field][:80]}...")

    if extra_note:
        print(f"\n{extra_note}")

    if not confirm:
        print("\nDRY RUN — no changes made. Re-run with --confirm to write these to Merchant Center.")
        return

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

    # Resolve the write target once per distinct (contentLanguage, feedLabel) pair in the plan —
    # from the owning primary's own rule, not a guess (see find_write_target's docstring for why
    # matching on the API source's own config instead is a real, previously-hit bug).
    write_targets = {}
    for item in plan:
        content_language, feed_label, _offer_id = item["product_id"].split("~", 2)
        lang_label_key = (content_language, feed_label)
        if lang_label_key not in write_targets:
            try:
                write_target, owning_primary = find_write_target(merchant_id, headers, *lang_label_key)
            except RuntimeError as e:
                print(f"{e}")
                sys.exit(2)
            write_targets[lang_label_key] = write_target
            print("=" * 70)
            print(f"Primary source: \"{owning_primary.get('displayName')}\" ({owning_primary['name']})")
            print(f"Writing into : \"{write_target.get('displayName')}\" ({write_target['name']})")
            print("=" * 70 + "\n")

    print(f"Writing {field}s...")
    pending = {}
    for item in plan:
        pid = item["product_id"]
        content_language, feed_label, _offer_id = pid.split("~", 2)
        write_target = write_targets[(content_language, feed_label)]
        # Retry the write itself — the same transient failure modes that hit GETs (a 410
        # misleadingly worded as a full API-sunset error, and a 200 whose body is actually an
        # error object) were confirmed live to hit writes too on the old Content API, and nothing
        # guarantees they can't recur here. A status-code-only check can't tell a real success
        # from a masked failure, so check the body shape here as well, not just resp.status_code.
        r, write_attempts = None, 3
        for attempt in range(write_attempts):
            r = requests.patch(
                f"{PRODUCTS_API}/accounts/{merchant_id}/productInputs/{pid}",
                headers=headers,
                params={"updateMask": f"productAttributes.{field}", "dataSource": write_target["name"]},
                data=json.dumps({"productAttributes": {field: item[field]}}),
            )
            if r.status_code == 200 and "error" not in r.json():
                break
            if attempt < write_attempts - 1:
                time.sleep(3)
        if r.status_code == 200 and "error" not in r.json():
            print(f"  {pid}: submitted (200)")
            pending[pid] = item[field]
        else:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300]
            reason = body.get("error", {}).get("message", "") if isinstance(body, dict) else ""
            if "multiple feeds" in reason.lower():
                print(f"  {pid}: FAILED — {reason}")
                print(f"    This product exists in more than one data source (likely a stray entry from an")
                print(f"    earlier write into an unreferenced API source). Not retryable from here — resolve")
                print(f"    in Merchant Center (Data sources) which source should own this product.")
            else:
                print(f"  {pid}: FAILED after {write_attempts} attempts — {r.status_code} {body}")

    if not pending:
        return

    print("\nVerifying propagation (Merchant Center merges API writes asynchronously, usually")
    print("within 30-90 seconds — polling for up to 2 minutes)...")
    for attempt in range(8):
        if not pending:
            break
        time.sleep(15)
        still_pending = {}
        for pid, value in pending.items():
            try:
                live = get_product(merchant_id, headers, pid)
            except RuntimeError:
                still_pending[pid] = value
                continue
            if live.get("productAttributes", {}).get(field, "") == value:
                print(f"  {pid}: UPDATED")
            else:
                still_pending[pid] = value
        pending = still_pending

    if pending:
        print(f"\n{len(pending)} product(s) still not confirmed after 2 minutes — the write was accepted")
        print("(clean 200) but the live field doesn't match yet. This can be ordinary propagation delay, the")
        print("primary data source's merge rule not pulling from the API source at all (see the warning above,")
        print("if one was printed), or — confirmed to happen even with the rule configured correctly — a")
        print("product/field-specific hold in Merchant Center's own processing (see the module docstring's")
        print("finding (2)). If still stuck after a few more minutes with no merge-rule warning above, edit")
        print("it directly in the Merchant Center UI — that's the confirmed, permanent fallback:")
        for pid in pending:
            print(f"  - {pid}")
    else:
        print(f"\nAll {field}s confirmed live.")


def cmd_describe_apply(args):
    """Step 2 of describe mode — the only step that writes to Merchant Center.
    Only ever run after the user has seen the full before/after list per
    product and explicitly approved it, same convention as every other apply
    step in this workspace (add_shared_negatives.py, pmax_bucketing.py, etc)."""
    client_meta = resolve(args.client)
    apply_field_updates(client_meta, args.plan, "description", args.confirm)


def cmd_title_apply(args):
    """Title Mode's apply step — same mechanics as describe apply
    (apply_field_updates, Merchant API productInputs.patch). Title writes
    have been the less reliable of the two field types in practice — see
    the module docstring's finding (2): confirmed on real products that a
    title write can return a clean 200 and never actually change, with a
    description write on the same product succeeding both times. Only run
    this after the user has seen and approved the exact before/after title
    per product, same convention as every other apply step here."""
    client_meta = resolve(args.client)
    apply_field_updates(client_meta, args.plan, "title", args.confirm)


def main():
    parser = argparse.ArgumentParser(description="Product feed optimization — titles and descriptions, both check + apply")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_title = sub.add_parser("title", help="Title optimization — check (fetch-candidates) + apply")
    title_sub = p_title.add_subparsers(dest="title_cmd", required=True)

    p_title_fetch = title_sub.add_parser("fetch-candidates", help="Find title gaps + top converting generic terms")
    p_title_fetch.add_argument("client")
    p_title_fetch.add_argument("--select", choices=["all", "best5", "best15", "best30", "ids"], required=True,
                                help="Which products to scope the restructuring suggestions to (same question as describe mode)")
    p_title_fetch.add_argument("--ids", help="Comma-separated Merchant Center product IDs (required if --select ids)")
    p_title_fetch.add_argument("--rank-by", choices=["revenue", "impressions", "clicks", "conversions", "conversions_value"],
                                default="revenue", help="What 'best' means for --select best5/15/30 (default: revenue via GA4)")
    p_title_fetch.add_argument("--days", type=int, default=90)
    p_title_fetch.add_argument("--min-impressions", type=int, default=10)
    p_title_fetch.add_argument("--top", type=int, default=20)
    p_title_fetch.set_defaults(func=cmd_title)

    p_title_apply = title_sub.add_parser("apply", help="Write approved titles to Merchant Center")
    p_title_apply.add_argument("client")
    p_title_apply.add_argument("--plan", required=True, help="JSON file: list of {product_id, title}")
    p_title_apply.add_argument("--confirm", action="store_true", help="Without this, dry-run only")
    p_title_apply.set_defaults(func=cmd_title_apply)

    p_describe = sub.add_parser("describe", help="Description optimization — has an apply step")
    describe_sub = p_describe.add_subparsers(dest="describe_cmd", required=True)

    p_fetch = describe_sub.add_parser("fetch-candidates", help="Pick products + pull ranked keyword candidates")
    p_fetch.add_argument("client")
    p_fetch.add_argument("--select", choices=["all", "best5", "best15", "best30", "ids"], required=True)
    p_fetch.add_argument("--ids", help="Comma-separated Merchant Center product IDs (required if --select ids)")
    p_fetch.add_argument("--rank-by", choices=["revenue", "impressions", "clicks", "conversions", "conversions_value"],
                          default="revenue", help="What 'best' means for --select best5/15/30 (default: revenue via GA4)")
    p_fetch.add_argument("--days", type=int, default=90)
    p_fetch.add_argument("--min-impressions", type=int, default=5)
    p_fetch.add_argument("--top", type=int, default=30)
    p_fetch.set_defaults(func=cmd_describe_fetch_candidates)

    p_apply = describe_sub.add_parser("apply", help="Write approved descriptions to Merchant Center")
    p_apply.add_argument("client")
    p_apply.add_argument("--plan", required=True, help="JSON file: list of {product_id, description}")
    p_apply.add_argument("--confirm", action="store_true", help="Without this, dry-run only")
    p_apply.set_defaults(func=cmd_describe_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
