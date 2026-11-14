# Client: <Name> (<domain>)

This file is read by every AI-judgment step (negative-keyword audits, PMax
audits, keyword expansion) for this client. It's the main thing you edit to
tune behavior — no code changes needed. Copy this template into
`clients/<slug>/client-brief.md`, fill it in, and add the matching entry to
`scripts/client_registry.py`.

## Business Context
<1-3 sentences: what the business sells, who its customer is, what "success" looks like (leads vs. sales).>

## Monthly Budget
<Amount and currency — used for pacing checks in /55-daily-check.>

## Products / Services Offered — NEVER negate
<List the real products/services/models this client actually offers. Anything
here should never be treated as irrelevant, even if it looks like a generic
term.>

## Brand Terms — NEVER negate
<The client's own brand name(s) and common misspellings/transliterations.>

## Geography
<Where the client actually serves customers — used to catch wrong-geography searches.>

## Languages
<Language(s) searches should be evaluated in.>

## Always Negate (Pre-approved)
List categories of search terms that should always be treated as irrelevant
without asking again. Common starting categories — delete/edit as needed:

### Employment / Careers
<e.g. "jobs at X", "careers", "vacancies">

### DIY / Educational (if not relevant to this business)
<e.g. "how to build X myself">

### Wrong category / not offered
<Products, services, or models this client explicitly does NOT offer.>

### Competitor Brands
<Named competitors — decide per client whether to negate these or bid on them.>

## Protected — NEVER negate these
<Any pattern that looks like it should be negated by the rules above but
shouldn't be — e.g. a model name that overlaps with a generic word. This is
your safety net against false positives.>

## Implementation Instructions
### After identifying negative keywords:
Follow the standard flow for this toolkit: NEGATED / KEPT / BROAD MATCH
classification, shown to a human for approval before anything is written
(see `/55-keyword-audit` and `/55-pmax-brand-generic-audit`).
