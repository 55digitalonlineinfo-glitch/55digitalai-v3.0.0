---
description: Keyword Planner in the terminal — search volume, CPC, competition, 12-month trend for a list of terms, cross-checked against the account's existing keywords
---

Run keyword research for client **$1** on the terms the user provided (everything after the client slug — comma-separated, or a natural list; reconstruct it into a single comma-separated string if the raw arguments don't already look like one).

1. Run: `.venv/bin/python3 scripts/keyword_research.py $1 "<comma-separated terms>"`
   - If `$1` looks wrong or isn't a known client slug, the script will list valid slugs — show that to the user and stop.
   - The script auto-selects geo targeting and language from the client's country in `client_registry.py` — no need to ask the user for this.
   - Read-only. Makes zero changes to the account.
   - **Always includes a "SIMILAR KEYWORD IDEAS" section by default** — this calls Keyword Planner's idea-generation mode (`GenerateKeywordIdeas`, seeded from the requested terms), not just historical metrics for the exact terms typed, so the user gets related suggestions even when they only asked about one or two specific terms. Pass `--no-ideas` only if the user explicitly wants just the exact terms checked with nothing else. `--idea-limit N` controls how many ideas show (default 20, sorted by volume).
2. Present the results conversationally, organized around what's actionable:
   - **New terms worth adding** (`[NEW]` + real search volume) — lead with these, especially ones with decent volume and low/medium competition, since that's the highest-value finding. Draw from both the requested-terms results and the similar-ideas section.
   - **Already in account** (`[IN ACCOUNT]`) — mention briefly as "already covered," don't re-pitch adding them.
   - **Zero/near-zero volume terms** — flag as likely not worth pursuing rather than silently omitting them.
   - **Similar keyword ideas need more scrutiny than the exact-requested terms** — idea mode routinely surfaces competitor/other-business names (e.g. a rival's name embedded in a suggested phrase) and off-topic suggestions alongside genuine gaps. Read every idea row before recommending it; don't just relay the list.
   - Note the 12-month trend only when it's notably seasonal or trending up/down — don't recite all 12 months verbatim for every term.
3. If the user asks for recommendations, use judgment based on volume, competition level, and CPC range relative to what's already in the account — don't just dump the raw numbers back at them.
