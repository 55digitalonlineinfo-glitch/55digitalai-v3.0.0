#!/usr/bin/env python3
"""
55DigitalAI — Add Shared Negative Keywords (apply step)
=============================================================
Purpose  : Takes a plan file (exact-match + broad-match negative terms,
           already reviewed and approved by the user) and adds them to a
           client's shared negative-keyword list via SharedCriterionService.
           This is the ONLY step in the interactive /keyword-audit flow
           that writes to the account — it must only be called after the
           user has seen the full proposed list and explicitly confirmed
           it, same convention as keyword_expansion.py's apply step.

           Plan file format (JSON):
             {"exact": ["term one", "term two"], "broad": ["token"]}

Usage    : python3 add_shared_negatives.py <client_slug> --plan plan.json --confirm
Changelog: 2026-07-26  Initial version — mutate_shared_criteria pattern
                       reused from an earlier client-specific pmax_audit.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402
from change_log import log_change, new_run_id  # noqa: E402

from google.ads.googleads.client import GoogleAdsClient

GOOGLE_ADS_YAML = Path(__file__).resolve().parent.parent / "google-ads.yaml"


def add_negatives(ads_client, customer_id, list_id, terms, match_type_enum, client_slug, run_id):
    if not terms:
        return 0
    match_name = match_type_enum.name
    shared_criterion_service = ads_client.get_service("SharedCriterionService")
    operations = []
    for term in terms:
        op = ads_client.get_type("SharedCriterionOperation")
        sc = op.create
        sc.shared_set = f"customers/{customer_id}/sharedSets/{list_id}"
        sc.keyword.text = term
        sc.keyword.match_type = match_type_enum
        operations.append(op)

    added = 0
    added_terms = []
    for i in range(0, len(operations), 1000):
        batch = operations[i:i + 1000]
        try:
            resp = shared_criterion_service.mutate_shared_criteria(customer_id=customer_id, operations=batch, timeout=60)
            added += len(resp.results)
            added_terms.extend(terms[i:i + 1000])
        except Exception as e:
            print(f"  Batch failed ({e}), retrying terms individually...")
            for j, op in enumerate(batch):
                try:
                    resp = shared_criterion_service.mutate_shared_criteria(customer_id=customer_id, operations=[op], timeout=60)
                    added += len(resp.results)
                    added_terms.append(terms[i + j])
                except Exception as e2:
                    print(f"    FAILED: {op.create.keyword.text!r} — {e2}")

    for term in added_terms:
        log_change(client_slug=client_slug, script="add_shared_negatives.py", action="add_negative_keyword",
                   resource_type="shared_criterion", resource_id=list_id, detail=f"{term} ({match_name})",
                   run_id=run_id)
    return added


def cmd_apply(args):
    client_meta = resolve(args.client)
    list_id = client_meta.get("negative_list_id")
    if not list_id:
        print(f"No negative_list_id configured for '{args.client}' in client_registry.py")
        sys.exit(2)

    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    exact_terms = plan.get("exact", [])
    broad_terms = plan.get("broad", [])

    print(f"Client      : {client_meta['name']} ({args.client})")
    print(f"Shared list : {list_id}")
    print(f"Plan file   : {plan_path}")
    print(f"Exact-match to add: {len(exact_terms)}")
    print(f"Broad-match to add: {len(broad_terms)}")

    if not args.confirm:
        print("\nDRY RUN — pass --confirm to actually write these to the account. Nothing was changed.")
        for t in exact_terms:
            print(f"  [would add EXACT] {t}")
        for t in broad_terms:
            print(f"  [would add BROAD] {t}")
        return

    ads_client = GoogleAdsClient.load_from_storage(str(GOOGLE_ADS_YAML))
    customer_id = client_meta["customer_id"]
    run_id = new_run_id()

    exact_added = add_negatives(ads_client, customer_id, list_id, exact_terms, ads_client.enums.KeywordMatchTypeEnum.EXACT, args.client, run_id)
    broad_added = add_negatives(ads_client, customer_id, list_id, broad_terms, ads_client.enums.KeywordMatchTypeEnum.BROAD, args.client, run_id)

    print(f"\nAdded {exact_added}/{len(exact_terms)} exact-match negatives.")
    print(f"Added {broad_added}/{len(broad_terms)} broad-match negatives.")


def main():
    parser = argparse.ArgumentParser(description="Apply an approved negative-keyword plan to a shared list")
    parser.add_argument("client")
    parser.add_argument("--plan", required=True, help="Path to a JSON plan file: {\"exact\": [...], \"broad\": [...]}")
    parser.add_argument("--confirm", action="store_true", help="Actually write to the account. Without this, dry-run only.")
    parser.set_defaults(func=cmd_apply)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
