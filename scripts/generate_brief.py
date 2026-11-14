#!/usr/bin/env python3
"""
55DigitalAI — Auto-Draft Client Brief from a Website URL
=============================================================
Purpose  : Fetches a client's website, extracts readable text, and asks
           Claude to draft clients/<slug>/client-brief.md from it — same
           template structure as clients/_template/client-brief.md.

           This produces a DRAFT, not a finished brief. The output file is
           stamped with a clear header saying so. The brief is the single
           most safety-critical file in the toolkit — it's what every
           negative-keyword and PMax audit reasons against — so an AI's
           read of a homepage is a starting point for someone who knows the
           business to correct, never a substitute for that review.

Usage    : python3 scripts/generate_brief.py <client_slug> <url> [<url2> ...]
           (a single URL is treated as a homepage: its same-domain links are
           auto-discovered and crawled too, so product/category pages aren't
           missed. Pass multiple URLs yourself to fetch exactly those pages
           and skip auto-crawling.)
Changelog: 2026-07-26  Initial version
           2026-07-26  Auto-discover and crawl linked content pages when a
                       single homepage URL is given, so product/service
                       pages one click away from the homepage aren't missed
"""

import sys
import re
import subprocess
import os
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Links matching these patterns are non-content by construction (link protocol,
# CMS internals, binary assets) — skip them when auto-discovering pages to crawl
# from a homepage. Deliberately NOT filtering by words like "contact"/"cart"/
# "privacy": this toolkit serves clients in any language, and a denylist of
# English (or Polish, or any other) words would silently fail to skip — or
# worse, silently skip real product pages in — every other language.
_SKIP_LINK_PATTERN = re.compile(
    r"(^tel:|^mailto:|^javascript:|^#"
    r"|/wp-admin|/wp-content|/wp-json|/feed|xmlrpc\.php"
    r"|\.(?:jpg|jpeg|png|gif|svg|webp|pdf|css|js|xml|zip)(?:\?|$))",
    re.IGNORECASE,
)


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PPCToolkitBriefBot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text


def strip_html(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&amp;|&#\d+;|&[a-zA-Z]+;", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def fetch_text(url: str) -> str:
    return strip_html(fetch_html(url))


def discover_internal_links(base_url: str, html: str, limit: int = 8) -> list:
    """Pull same-domain content links (product/service pages, etc.) out of a
    homepage's raw HTML, skipping nav chrome and legal/contact boilerplate.

    A homepage's own text is often just a summary — real product lines (e.g.
    a "meble-lazienkowe" category page) live one click away and are easy to
    miss if only the homepage is ever fetched."""
    domain = urlparse(base_url).netloc
    seen = []
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = match.group(1).strip()
        if not href or _SKIP_LINK_PATTERN.search(href):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc != domain:
            continue
        clean = absolute.split("#")[0].rstrip("/")
        if not clean or clean == base_url.rstrip("/") or clean in seen:
            continue
        seen.append(clean)
        if len(seen) >= limit:
            break
    return seen


def gather_page_texts(urls: list, crawl_limit: int = 8) -> dict:
    """Fetch text for each given URL. When a single homepage URL is given,
    also auto-discover and fetch a handful of linked content pages so the
    brief isn't drafted from the homepage's summary text alone."""
    page_texts = {}
    for url in urls:
        try:
            html = fetch_html(url)
            page_texts[url] = strip_html(html)
            print(f"  {url} — {len(page_texts[url])} chars")
        except Exception as e:
            print(f"  {url} — FAILED ({e}), skipping")
            continue

        if len(urls) == 1:
            links = discover_internal_links(url, html, limit=crawl_limit)
            if links:
                print(f"  discovered {len(links)} linked page(s), fetching those too...")
            for link in links:
                try:
                    page_texts[link] = fetch_text(link)
                    print(f"    {link} — {len(page_texts[link])} chars")
                except Exception as e:
                    print(f"    {link} — FAILED ({e}), skipping")

    return page_texts


def find_claude_binary() -> str:
    import shutil
    binary = shutil.which("claude")
    if binary:
        return binary
    # Fallback: the desktop app and the VS Code/Cursor extensions each bundle
    # their own claude binary, which isn't always on PATH. Use the current
    # user's actual home directory here — this used to be hardcoded to one
    # specific developer's username, which would silently fail for every
    # other buyer of this toolkit.
    home = Path.home()
    candidates = sorted(
        [
            # native Windows/macOS CLI installer's default location — not always on
            # PATH yet in the same session it was installed in
            home / ".local" / "bin" / "claude",
            home / ".local" / "bin" / "claude.exe",
            *home.glob("Library/Application Support/Claude/claude-code/**/claude"),
            *home.glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
            *home.glob(".vscode-insiders/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
            *home.glob(".cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
            *home.glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
            *home.glob(".vscode-insiders/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
            *home.glob(".cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"),
        ],
        key=lambda p: str(p),
    )
    for p in reversed(candidates):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    sys.exit("ERROR: Claude binary not found. Is Claude Code installed?")


def call_claude(prompt: str, claude_binary: str, timeout: int = 300) -> str:
    result = subprocess.run(
        [claude_binary, "--dangerously-skip-permissions", "-p"],
        input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(ROOT),
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()[-2000:] or f"exit {result.returncode}"
        raise RuntimeError(f"exit {result.returncode}: {detail}")
    return result.stdout


def build_prompt(client_name: str, domain: str, page_texts: dict) -> str:
    pages_block = "\n\n".join(f"--- {url} ---\n{text[:6000]}" for url, text in page_texts.items())
    return f"""You are drafting a FIRST-PASS client brief for a Google Ads negative-keyword/PMax audit tool, based only on the real content of this business's own website below. A human who knows the business will review and correct this before it's used for anything real — write a solid starting point, not a confident final answer.

Business: {client_name} ({domain})

Website content:
{pages_block}

Fill in this exact template, in this exact markdown structure. Base every section strictly on what the website content actually says. If something isn't clear from the content, write "(not clear from the site — confirm with the client)" rather than guessing or inventing.

# Client: {client_name} ({domain})

## Business Context
<1-3 sentences: what the business sells, who its customer is, what "success" looks like (leads vs. sales)>

## Products / Services Offered — NEVER negate
<Real products/services/models this business actually offers, based on the site>

## Brand Terms — NEVER negate
<The business's own brand name(s) and any obvious variants>

## Geography
<Where the site indicates this business serves customers>

## Languages
<Language(s) the site is in>

## Always Negate (Pre-approved)
Suggest 2-4 plausible categories for this specific type of business (e.g. careers/employment terms, DIY content if this is a service business, wrong-category products if it's ecommerce). Head this section "SUGGESTED — confirm these with the client before relying on them" since these are inferred, not confirmed.

## Protected — NEVER negate these
<Flag anything from the site that looks like a false-positive risk — e.g. a product name that's also a common word. Otherwise leave a placeholder for the human to fill in.>

Return ONLY the completed markdown, no commentary before or after it."""


def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: python3 scripts/generate_brief.py <client_slug> <url> [<url2> ...]")

    slug = sys.argv[1]
    urls = sys.argv[2:]
    client = resolve(slug)

    print(f"Fetching {len(urls)} page(s)...")
    page_texts = gather_page_texts(urls)

    if not page_texts:
        sys.exit("ERROR: couldn't fetch any of the given URLs.")

    print("Drafting brief with Claude...")
    claude_binary = find_claude_binary()
    prompt = build_prompt(client["name"], client["domain"], page_texts)
    draft = call_claude(prompt, claude_binary)

    header = (
        f"<!-- DRAFT — auto-generated from {', '.join(page_texts.keys())} on {datetime.now().date()}. "
        f"Nobody who actually knows this business has reviewed this yet. Read every "
        f"section and correct it before running any audit that relies on this file. -->\n\n"
    )

    brief_path = ROOT / "clients" / slug / "client-brief.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(header + draft.strip() + "\n", encoding="utf-8")

    print(f"\nDraft written to {brief_path}")
    print("This is a STARTING POINT, not a finished brief — review every section before relying on it.")


if __name__ == "__main__":
    main()
