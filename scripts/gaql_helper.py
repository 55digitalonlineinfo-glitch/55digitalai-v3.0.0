#!/usr/bin/env python3
"""
55DigitalAI — GAQL Query Safety Wrapper
=============================================================
Purpose  : Wraps GoogleAdsService.search() with two things a raw call
           doesn't give you:
             1. A pre-flight check for known-bad query patterns (e.g. DURING
                literals, which are inconsistently supported across resources
                — always use an explicit BETWEEN date range instead) so the
                mistake is caught before spending a round trip / API quota.
             2. Friendlier error messages on GoogleAdsException — the raw
                gRPC error is still available (never swallowed), but the
                common failure modes (bad field name, auth failure, quota)
                get a plain-English hint printed first.

           This does NOT validate full GAQL grammar — that would mean
           reimplementing Google's own query parser. It catches the specific
           mistakes this toolkit's scripts have actually hit in production.

Usage    : from gaql_helper import safe_search
           rows = safe_search(ga_service, customer_id, query)
"""

import re
import sys

_DURING_RE = re.compile(r"\bDURING\s+(LAST_\w+|THIS_\w+)\b", re.IGNORECASE)


def preflight_check(query: str) -> list:
    """Returns a list of warning strings for known-bad patterns. Doesn't raise —
    callers decide whether to abort or just warn."""
    warnings = []
    m = _DURING_RE.search(query)
    if m:
        warnings.append(
            f"Query uses 'DURING {m.group(1)}' — this date literal isn't supported "
            f"on every resource. Use an explicit 'segments.date BETWEEN \"YYYY-MM-DD\" "
            f"AND \"YYYY-MM-DD\"' instead."
        )
    return warnings


def safe_search(ga_service, customer_id: str, query: str, timeout: int = 120, strict: bool = False):
    """Drop-in replacement for ga_service.search(customer_id=..., query=...).

    strict=True raises on a preflight warning instead of just printing it —
    use this in non-interactive/scheduled contexts where nobody will see the
    warning printed to stdout.
    """
    warnings = preflight_check(query)
    for w in warnings:
        msg = f"[gaql_helper] WARNING: {w}"
        if strict:
            raise ValueError(msg)
        print(msg, file=sys.stderr)

    try:
        return list(ga_service.search(customer_id=customer_id, query=query, timeout=timeout))
    except Exception as e:
        hint = _friendly_hint(e)
        if hint:
            print(f"[gaql_helper] {hint}", file=sys.stderr)
        raise


def _friendly_hint(e: Exception) -> str:
    text = str(e)
    if "UNAUTHENTICATED" in text or "invalid_grant" in text.lower():
        return ("Hint: this looks like an auth failure — check developer_token/"
                "client_secret/refresh_token in google-ads.yaml are current "
                "(a refresh_token stops working if the client_secret it was issued "
                "under gets regenerated).")
    if "PERMISSION_DENIED" in text:
        return ("Hint: the Google account behind this OAuth token doesn't have "
                "access to this customer_id — check Access and Security in the "
                "Google Ads UI for this account.")
    if "QUERY_ERROR" in text or "InvalidQueryError" in text:
        return ("Hint: GAQL syntax/field error — check field names against the "
                "current API version's schema (fields do get renamed/deprecated "
                "between versions).")
    if "RESOURCE_EXHAUSTED" in text or "RATE_EXCEEDED" in text:
        return "Hint: API quota/rate limit hit — wait and retry, or reduce query frequency."
    return ""
