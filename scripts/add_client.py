#!/usr/bin/env python3
"""Non-interactive CLI for adding a new client — reuses the same underlying
logic setup_wizard.py's interactive flow uses (list_live_accounts, save_client,
scaffold_client_folder, smoke_test_client, find_shared_negative_list_by_name),
just driven by CLI arguments instead of input() prompts.

Exists so /setup-new-client (a Claude Code slash command) can drive this step
by step via AskUserQuestion — Claude can't answer a real terminal's input()
prompts live the way a human running setup_wizard.py directly can, so this
gives it a non-interactive equivalent for the "add a client" part specifically
(first-time credential/OAuth setup still requires the real wizard in a
terminal, since that needs an actual browser).

Usage:
  python3 scripts/add_client.py list-accounts
  python3 scripts/add_client.py add --name "..." --customer-id ... --slug ... \\
      --domain ... --country ... --timezone ... --business-type lead_gen|ecommerce \\
      --currency ... [--monthly-budget N] [--ga4-property-id ID] \\
      [--negative-list-name "..."] [--merchant-center-id ID] [--allow-duplicate]
  python3 scripts/add_client.py smoke-test <slug>
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client_registry import resolve
from setup_wizard import (
    find_shared_negative_list_by_name,
    list_live_accounts,
    load_clients,
    save_client,
    scaffold_client_folder,
    smoke_test_client,
)


def cmd_list_accounts(args):
    accounts = list_live_accounts()
    if not accounts:
        print("No enabled accounts found under this MCC.")
        return
    for i, acc in enumerate(accounts, 1):
        print(f"{i}. {acc['name']} — {acc['customer_id']}")


def cmd_add(args):
    existing = load_clients()
    customer_id = re.sub(r"[^0-9]", "", args.customer_id)

    dupe_slug = next((s for s, e in existing.items() if e.get("customer_id") == customer_id), None)
    if dupe_slug and dupe_slug not in ("acme", args.slug) and not args.allow_duplicate:
        sys.exit(
            f"ERROR: customer ID {customer_id} is already registered as '{dupe_slug}' in "
            f"clients.json. Pass --allow-duplicate to add it again under a different slug anyway."
        )

    negative_list_id = None
    if args.negative_list_name:
        try:
            negative_list_id = find_shared_negative_list_by_name(customer_id, args.negative_list_name)
            print(f"Resolved negative list '{args.negative_list_name}' -> ID {negative_list_id}")
        except Exception as e:
            print(f"WARNING: couldn't resolve '{args.negative_list_name}' to a list ID ({e}). "
                  f"Set negative_list_id by hand in clients.json once confirmed.")

    entry = {
        "name": args.name, "domain": args.domain, "customer_id": customer_id,
        "country": args.country, "timezone": args.timezone,
        "monthly_budget": args.monthly_budget, "currency": args.currency,
        "business_type": args.business_type,
        "ga4_property_id": args.ga4_property_id,
        "negative_list_id": negative_list_id,
        "merchant_center_id": args.merchant_center_id,
        "pmax_branded_generic_list_id": None,
        "links": {},
    }

    save_client(args.slug, entry, existing)
    scaffold_client_folder(args.slug, args.name)
    print(f"\nDone — clients/{args.slug}/ is ready.")


def cmd_smoke_test(args):
    client = resolve(args.slug)
    smoke_test_client(client["customer_id"], client["currency"])


def main():
    parser = argparse.ArgumentParser(description="Add a new client (non-interactive)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-accounts", help="List enabled Google Ads accounts under this MCC")

    p_add = sub.add_parser("add", help="Add a new client to clients.json + scaffold its folder")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--customer-id", required=True)
    p_add.add_argument("--slug", required=True)
    p_add.add_argument("--domain", required=True)
    p_add.add_argument("--country", required=True)
    p_add.add_argument("--timezone", required=True)
    p_add.add_argument("--business-type", choices=["lead_gen", "ecommerce"], default="lead_gen")
    p_add.add_argument("--currency", default="USD")
    p_add.add_argument("--monthly-budget", type=float, default=None)
    p_add.add_argument("--ga4-property-id", default=None)
    p_add.add_argument("--negative-list-name", default=None)
    p_add.add_argument("--merchant-center-id", default=None)
    p_add.add_argument("--allow-duplicate", action="store_true")

    p_smoke = sub.add_parser("smoke-test", help="Pull real 7-day data to confirm the client works")
    p_smoke.add_argument("slug")

    args = parser.parse_args()
    {
        "list-accounts": cmd_list_accounts,
        "add": cmd_add,
        "smoke-test": cmd_smoke_test,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
