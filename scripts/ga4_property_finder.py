#!/usr/bin/env python3
"""
55DigitalAI — GA4 Property Finder
=============================================================
Purpose  : Auto-discover a client's GA4 property id via the Analytics Admin
           API instead of asking the user to paste one in by hand. Walks
           every GA4 account/property the connected Google account can see,
           reads each property's web data stream default URI, and matches
           it against the client's `domain` field in clients.json.

           Read-only by default — `find` only prints candidates. Writing
           the match back to clients.json requires --save, which still
           only fires on an unambiguous single match.

Usage    : python3 ga4_property_finder.py list
           python3 ga4_property_finder.py find <client_slug> [--save]
           python3 ga4_property_finder.py whoami
Changelog: 2026-07-27  Initial version
           2026-07-27  Added `whoami` — best-effort identity check for the
                       account behind the toolkit's current refresh token,
                       used to confirm "is this the right GA4 account?"
                       before a lookup, since the wrong-account case looks
                       identical to a plain access gap (both 403).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import CLIENTS, resolve, save_clients, reload  # noqa: E402
from ga4_reports import get_credentials  # noqa: E402

GA4_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"


def normalize_domain(url_or_domain: str) -> str:
    if not url_or_domain:
        return ""
    if "://" not in url_or_domain:
        url_or_domain = f"https://{url_or_domain}"
    host = urlparse(url_or_domain).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def list_properties(headers) -> list[dict]:
    """Every GA4 property visible to this OAuth grant, with its web stream domain(s)."""
    properties = []
    page_token = None
    while True:
        params = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(f"{GA4_ADMIN_API}/accountSummaries", headers=headers, params=params)
        if r.status_code != 200:
            raise RuntimeError(f"GA4 Admin API error {r.status_code}: {r.text[:500]}")
        data = r.json()
        for acc in data.get("accountSummaries", []):
            for p in acc.get("propertySummaries", []):
                prop_id = p["property"].split("/")[-1]
                streams_r = requests.get(f"{GA4_ADMIN_API}/properties/{prop_id}/dataStreams", headers=headers)
                domains = []
                if streams_r.status_code == 200:
                    for s in streams_r.json().get("dataStreams", []):
                        uri = s.get("webStreamData", {}).get("defaultUri")
                        if uri:
                            domains.append(normalize_domain(uri))
                properties.append({
                    "account": acc["displayName"],
                    "property_id": prop_id,
                    "display_name": p["displayName"],
                    "domains": domains,
                })
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return properties


def find_matches(client_domain: str, properties: list[dict]) -> list[dict]:
    target = normalize_domain(client_domain)
    return [p for p in properties if target and target in p["domains"]]


def whoami(headers) -> str | None:
    """Best-effort email of the account behind the current token. None if the
    token's scopes don't include an identity scope (the production token as
    shipped doesn't — see get_google_refresh_token.py to reissue one that does)."""
    r = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers=headers)
    if r.status_code != 200:
        return None
    return r.json().get("email")


def cmd_whoami(args):
    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}
    email = whoami(headers)
    if email:
        print(email)
    else:
        print("Unknown — current token doesn't carry an identity scope "
              "(re-run scripts/get_google_refresh_token.py to get one that does).")


def cmd_list(args):
    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}
    properties = list_properties(headers)
    if not properties:
        print("No GA4 properties visible to this Google account.")
        return
    for p in properties:
        domains = ", ".join(p["domains"]) or "(no web stream)"
        print(f"{p['property_id']:>15}  {p['display_name']:<30} [{p['account']}]  domains: {domains}")


def cmd_find(args):
    client_meta = resolve(args.client)
    domain = client_meta.get("domain")
    if not domain:
        sys.exit(f"Client '{args.client}' has no `domain` set in clients.json — can't match against GA4 by domain.")

    creds = get_credentials()
    headers = {"Authorization": f"Bearer {creds.token}"}
    properties = list_properties(headers)
    matches = find_matches(domain, properties)

    print(f"Client : {client_meta['name']} ({args.client})")
    print(f"Domain : {domain}  (normalized: {normalize_domain(domain)})\n")

    if not matches:
        print("No GA4 property found with a matching web stream domain.")
        print("Either this Google account doesn't have GA4 access on that property yet, "
              "or the property is under a different domain — check manually in GA4 Admin.")
        return

    for m in matches:
        print(f"MATCH  properties/{m['property_id']}  \"{m['display_name']}\"  [{m['account']}]  domains: {', '.join(m['domains'])}")

    if len(matches) > 1:
        print("\nMultiple properties share this domain — resolve manually, not saving.")
        return

    property_id = matches[0]["property_id"]
    if args.save:
        reload()
        CLIENTS[args.client]["ga4_property_id"] = property_id
        save_clients(CLIENTS)
        print(f"\nSaved ga4_property_id={property_id} for '{args.client}' to clients.json.")
    else:
        print(f"\nRun with --save to write ga4_property_id={property_id} into clients.json for '{args.client}'.")


def main():
    parser = argparse.ArgumentParser(description="Find a client's GA4 property id via the Analytics Admin API.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List every GA4 property visible to this Google account, with its domain(s).")
    sub.add_parser("whoami", help="Best-effort email of the account behind the current token.")

    p_find = sub.add_parser("find", help="Find the GA4 property matching a client's domain.")
    p_find.add_argument("client")
    p_find.add_argument("--save", action="store_true", help="Write the match into clients.json if unambiguous.")

    args = parser.parse_args()
    {"list": cmd_list, "find": cmd_find, "whoami": cmd_whoami}[args.command](args)


if __name__ == "__main__":
    main()
