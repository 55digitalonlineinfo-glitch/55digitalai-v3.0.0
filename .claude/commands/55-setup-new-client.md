---
description: Add a new client — the recurring "add another client" part of setup_wizard.py, driven through questions instead of a terminal
---

Add a new client to this toolkit. This is the non-interactive counterpart to `setup_wizard.py`'s "add a client" step — same underlying logic (`scripts/add_client.py` reuses `setup_wizard.py`'s own functions), just asked through questions since you can't answer a real terminal's `input()` prompts the way a human running the wizard directly can.

**Prerequisite this command assumes is already done:** `google-ads.yaml` must already exist (first-time developer token + OAuth browser sign-in). If it doesn't exist yet, stop and tell the user to run `bash setup.sh` once in a real terminal first — that part genuinely needs a browser and can't be driven through questions.

## Step 1 — List accounts under the MCC
`.venv/bin/python3 scripts/add_client.py list-accounts`

Read-only. Show the user the list (name + customer ID).

## Step 2 — Ask for the client's details
One AskUserQuestion-style set of questions (can be plain conversational asks if a fixed option list doesn't fit, e.g. free-text name/domain):
- **Which account?** Pick a number from Step 1's list, or type a customer ID directly if it's not in the list
- **Client name** (default: the account's name from Step 1, if picked from the list)
- **Short slug** (used in folder names, e.g. `acme` — default: name lowercased, spaces to dashes, first 20 chars)
- **Website domain** (e.g. `acme.example`, no `https://`)
- **Country code** (e.g. US, PL, UA)
- **Timezone** (e.g. `America/New_York`, `Europe/Warsaw`)
- **Business type**: `lead_gen` or `ecommerce`
- **Currency code** (e.g. USD, PLN, UAH)
- **Monthly budget** (optional, numbers only — skip if not known yet)
- **Shared negative-keyword list name**, as shown in Google Ads > Tools & Settings > Shared Library (optional — can be set later via `/55-keyword-audit`'s own list-scanning step, so don't block on this)

Before finalizing, check the customer ID isn't already registered under a different slug in `clients.json` — if it is, tell the user and ask whether to proceed anyway (`--allow-duplicate`) or stop.

## Step 3 — Add the client
`.venv/bin/python3 scripts/add_client.py add --name "..." --customer-id "..." --slug "..." --domain "..." --country "..." --timezone "..." --business-type <lead_gen|ecommerce> --currency "..." [--monthly-budget N] [--negative-list-name "..."] [--allow-duplicate]`

This writes `clients.json` and scaffolds `clients/<slug>/client-brief.md` from the template.

## Step 4 — Auto-draft the client brief, automatically
No need to ask — go straight to it, same as the setup wizard: `.venv/bin/python3 scripts/generate_brief.py <slug> https://<domain>`

Tell the user plainly afterward that this is an unreviewed draft — every real audit depends on this brief being accurate, so they should skim it now for anything obviously wrong (wrong products, wrong geography, wrong protected terms) before it drives real judgment later. If the fetch fails (site unreachable, etc.), say so and tell them to fill in `clients/<slug>/client-brief.md` by hand instead.

## Step 5 — Prove it actually works
`.venv/bin/python3 scripts/add_client.py smoke-test <slug>`

This pulls real 7-day spend/campaign data for this specific account — proof it's connected, not just that the MCC connection works in general. Report the result plainly. If it fails, say so (could mean no recent activity, or the signed-in Google account doesn't have access to this specific account yet).

## Step 6 — Point to what's next
Tell the user:
- `clients/<slug>/client-brief.md` is ready to review (or write, if auto-draft failed)
- They can now run `/55-daily-check <slug>` or `/55-keyword-audit <slug>` (the latter will offer to scan/create a shared negative-keyword list if one wasn't set in Step 2)
- If they want scheduled automation for this client's keyword audits later, that's `/55-setup-keyword-audit-automation <slug>`
