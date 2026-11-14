#!/usr/bin/env python3
"""
55DigitalAI — Extended Access Check (GA4 / Search Console / Merchant Center)
=============================================================
Purpose  : One-time (or occasional) check of which clients this Google
           account can actually see in GA4, Search Console, and Merchant
           Center — separate from Google Ads MCC access, since each of
           these products has its own permission grant. Matches by domain
           against client_registry.py.

           Read-only. Makes zero changes to any account.

Usage    : python3 scripts/check_extended_access.py
Requires : google-ads.yaml refresh_token must include the analytics.readonly,
           webmasters.readonly, and content scopes (see get_google_refresh_token.py).
Changelog: 2026-07-23  Initial version
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import CLIENTS  # noqa: E402

YAML_PATH = Path(__file__).resolve().parent.parent / "google-ads.yaml"


def get_credentials():
    cfg = yaml.safe_load(YAML_PATH.read_text())
    creds = Credentials(
        token=None,
        refresh_token=cfg["refresh_token"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return creds


def domain_of(url):
    if not url:
        return None
    if url.startswith("sc-domain:"):
        return url.replace("sc-domain:", "").lower().lstrip("www.")
    netloc = urlparse(url).netloc or url
    return netloc.lower().lstrip("www.")


def fetch_search_console_sites(headers):
    r = requests.get("https://searchconsole.googleapis.com/webmasters/v3/sites", headers=headers)
    if r.status_code != 200:
        return None, r.status_code, r.text[:300]
    entries = r.json().get("siteEntry", [])
    return {domain_of(e["siteUrl"]): e["permissionLevel"] for e in entries}, 200, None


def fetch_ga4_properties(headers):
    r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=headers)
    if r.status_code != 200:
        return None, r.status_code, r.text[:300]
    props = {}  # domain -> (account name, property name, property resource)
    for account in r.json().get("accountSummaries", []):
        for prop in account.get("propertySummaries", []):
            prop_resource = prop["property"]
            streams_r = requests.get(
                f"https://analyticsadmin.googleapis.com/v1beta/{prop_resource}/dataStreams", headers=headers
            )
            if streams_r.status_code != 200:
                continue
            for stream in streams_r.json().get("dataStreams", []):
                uri = stream.get("webStreamData", {}).get("defaultUri")
                d = domain_of(uri)
                if d:
                    props[d] = (account.get("displayName"), prop.get("displayName"), prop_resource)
    return props, 200, None


def fetch_merchant_accounts(headers):
    auth_r = requests.get("https://shoppingcontent.googleapis.com/content/v2.1/accounts/authinfo", headers=headers)
    if auth_r.status_code != 200:
        return None, auth_r.status_code, auth_r.text[:300]
    aggregator_ids = [a["aggregatorId"] for a in auth_r.json().get("accountIdentifiers", []) if "aggregatorId" in a]
    accounts = {}  # domain -> (account id, name)
    for agg_id in aggregator_ids:
        r = requests.get(f"https://shoppingcontent.googleapis.com/content/v2.1/{agg_id}/accounts", headers=headers)
        if r.status_code != 200:
            continue
        for acc in r.json().get("resources", []):
            d = domain_of(acc.get("websiteUrl"))
            if d:
                accounts[d] = (acc.get("id"), acc.get("name"))
    return accounts, 200, None


def main():
    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}

    print("Fetching Search Console sites...")
    sc_sites, sc_status, sc_err = fetch_search_console_sites(headers)
    print("Fetching GA4 properties (this walks every account's data streams, may take a moment)...")
    ga4_props, ga4_status, ga4_err = fetch_ga4_properties(headers)
    print("Fetching Merchant Center sub-accounts...")
    mc_accounts, mc_status, mc_err = fetch_merchant_accounts(headers)
    print()

    if sc_status != 200:
        print(f"Search Console API error ({sc_status}): {sc_err}\n")
    if ga4_status != 200:
        print(f"GA4 Admin API error ({ga4_status}): {ga4_err}\n")
    if mc_status != 200:
        print(f"Content API error ({mc_status}): {mc_err}\n")

    print("=" * 100)
    print(f"{'Client':<16} {'Domain':<28} {'Search Console':<20} {'GA4':<10} {'Merchant Center':<20}")
    print("=" * 100)
    for slug, meta in CLIENTS.items():
        domain = domain_of(meta.get("domain")) or ""
        if not domain:
            print(f"{slug:<16} {'(no domain on file)':<28} {'-':<20} {'-':<10} {'-':<20}")
            continue

        sc_status_str = "NOT FOUND"
        if sc_sites is not None:
            for d, perm in sc_sites.items():
                if d == domain or d.endswith("." + domain) or domain.endswith("." + d):
                    sc_status_str = perm
                    break

        ga4_status_str = "NOT FOUND"
        if ga4_props is not None:
            for d, (acc_name, prop_name, _) in ga4_props.items():
                if d == domain or d.endswith("." + domain) or domain.endswith("." + d):
                    ga4_status_str = f"{prop_name}"
                    break

        mc_status_str = "NOT FOUND"
        if mc_accounts is not None:
            for d, (acc_id, acc_name) in mc_accounts.items():
                if d == domain or d.endswith("." + domain) or domain.endswith("." + d):
                    mc_status_str = f"id {acc_id}"
                    break

        print(f"{slug:<16} {domain:<28} {sc_status_str:<20} {ga4_status_str:<10} {mc_status_str:<20}")
    print("=" * 100)
    print("\nNOT FOUND means this Google account has no visible access to that product for that client")
    print("(different from Ads MCC access — GA4/Search Console/Merchant Center each need their own grant).")


if __name__ == "__main__":
    main()
