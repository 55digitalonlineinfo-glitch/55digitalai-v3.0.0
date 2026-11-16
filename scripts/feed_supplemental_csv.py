#!/usr/bin/env python3
"""
55DigitalAI — Supplemental feed CSV generator (title/description overrides)
=============================================================
Purpose  : Alternative deliverable for the same approved plan.json that
           `feed_title_optimizer.py title|describe apply` writes live via
           the Merchant API — for when there's no API access on the
           account yet, or when a specific product is one of the confirmed
           "stuck on title" cases (see feed_title_optimizer.py's module
           docstring, finding (2)) and the permanent fallback is a manual
           edit rather than more API retries.

           Produces a plain CSV with an `id` column (the bare Merchant
           Center offerId — what a file-based supplemental feed matches
           against) plus whichever of `title`/`description` are present in
           the plan. This is Google's generic file-based supplemental feed
           shape: a secondary data source the client (or you, with access)
           registers in Merchant Center > Products > Data sources, with a
           feed rule set to take `title`/`description` from it — same
           underlying "primary data source's rule decides which fields come
           from where" model `feed_title_optimizer.py` documents for the
           API path, just via an uploaded file instead of `productInputs.patch`.
           This script does NOT upload or register anything — it only
           writes the CSV; the account-side data-source setup is a one-time
           manual step in Merchant Center, same as the API path's own
           one-time rule-configuration requirement.

Usage    : python3 feed_supplemental_csv.py <client_slug> --plan plan.json --out supplemental_feed.csv
Plan     : same file the apply step reads — list of
           {"product_id": "<Merchant API key or bare offerId>", "title": "...", "description": "..."}
           (title and/or description; at least one of the two per row).
Changelog: 2026-11-16  Initial version — built because no supplemental-feed
           generator existed in either workspace (only a one-off manual
           file for a single past client), despite the command doc having
           referenced "the deliverable is a supplemental-feed CSV" as an
           option since 2026-10-07.
"""

import argparse
import csv
import json
import sys


def offer_id_from_product_id(product_id):
    """Accepts either the Merchant API key (`contentLanguage~feedLabel~offerId`)
    or a bare offerId — a file-based supplemental feed matches on the bare
    id, same as the primary feed does."""
    if "~" in product_id:
        return product_id.rsplit("~", 1)[-1]
    return product_id


def build_rows(plan):
    fields = [f for f in ("title", "description") if any(f in item for item in plan)]
    if not fields:
        print("Plan has no 'title' or 'description' field on any row — nothing to write.")
        sys.exit(2)

    rows = []
    for item in plan:
        if "product_id" not in item:
            print(f"Skipping row with no 'product_id': {item}")
            continue
        row = {"id": offer_id_from_product_id(item["product_id"])}
        for f in fields:
            row[f] = item.get(f, "")
        rows.append(row)
    return fields, rows


def main():
    parser = argparse.ArgumentParser(description="Generate a Merchant Center supplemental feed CSV from an approved plan.json")
    parser.add_argument("client", help="Client slug (not read from the registry — kept for parity with the apply commands' call signature)")
    parser.add_argument("--plan", required=True, help="JSON file: list of {product_id, title and/or description}")
    parser.add_argument("--out", required=True, help="Output CSV path")
    args = parser.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    if not isinstance(plan, list) or not plan:
        print("Plan file must be a non-empty JSON list.")
        sys.exit(2)

    fields, rows = build_rows(plan)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id"] + fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} row(s), columns: id, {', '.join(fields)} -> {args.out}")
    print("\nNext (manual, one-time per account): in Merchant Center, Products > Data sources,")
    print("add this file as a new supplemental data source (scheduled fetch or one-off upload),")
    print("then on the account's PRIMARY data source's rule, set the relevant field(s) to take")
    print("from this new source — same override-rule model as the API apply path, just via a")
    print("file instead of a live write. Durability note: a row here can still hit the same")
    print("product/field-specific 'stuck on title' hold Merchant Center sometimes applies —")
    print("this CSV doesn't bypass that, it's just a different upload path into the same system.")


if __name__ == "__main__":
    main()
