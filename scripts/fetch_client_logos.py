#!/usr/bin/env python3
"""
Fetch client logos for the dashboard
=============================================================
Purpose  : Downloads each client's own site icon (apple-touch-icon / favicon / svg logo
           linked in the home page <head>), renders it to a 64x64 PNG and saves it as
           clients/<slug>/logo.png. build_dashboard.py copies these into dashboard/logos/
           and shows them instead of the initials avatar. Logos that are almost white
           get a dark backing so they stay visible on white cards.
Usage    : .venv/bin/python3 scripts/fetch_client_logos.py            # clients without a logo
           .venv/bin/python3 scripts/fetch_client_logos.py --force    # re-fetch all
           .venv/bin/python3 scripts/fetch_client_logos.py acme other   # only these
           .venv/bin/python3 scripts/fetch_client_logos.py --file acme path/to/logo.svg
                                                     # use a logo file you downloaded yourself
Setup    : Playwright (renders svg/ico/jpg uniformly) + Pillow, both already in .venv.
Skips    : sites that block the request (403) and generic builder icons (Wix pfavico),
           which keep the initials avatar. Delete clients/<slug>/logo.png to go back.
Changelog: 2026-11-12  Initial version.
           2026-11-12  --file <slug> <path> for manually downloaded logos (sites that block the fetch).
"""
import base64
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from client_registry import CLIENTS  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}
GENERIC_ICON_RE = re.compile(r"parastorage\.com/client/pfavico|wix\.com/favicon", re.I)
MIME = {"png": "image/png", "svg": "image/svg+xml", "ico": "image/x-icon"}


def get(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15)


def icon_candidates(domain: str) -> list:
    """Icon URLs from the home page <head>, best first (apple-touch, then biggest size)."""
    base = f"https://{domain}/"
    cands = []
    html = get(base).read(400_000).decode("utf-8", "replace")
    for tag in re.findall(r"<link[^>]+>", html, re.I):
        rel = re.search(r'rel=["\']([^"\']+)', tag, re.I)
        href = re.search(r'href=["\']([^"\']+)', tag, re.I)
        if rel and href and "icon" in rel.group(1).lower():
            size = re.search(r'sizes=["\'](\d+)', tag)
            prio = (2 if "apple" in rel.group(1).lower() else 1, int(size.group(1)) if size else 0)
            cands.append((prio, urllib.parse.urljoin(base, href.group(1))))
    cands.sort(reverse=True)
    return [u for _, u in cands] + [base + "apple-touch-icon.png", base + "favicon.ico"]


def download_icon(domain: str):
    """Return (bytes, ext) of the first usable brand icon, or None."""
    for url in icon_candidates(domain):
        if GENERIC_ICON_RE.search(url):
            continue
        try:
            r = get(url)
            data, ctype = r.read(), r.headers.get("content-type", "")
        except Exception:
            continue
        if len(data) < 100 or "html" in ctype:
            continue
        ext = "svg" if ("svg" in ctype or url.endswith(".svg")) else \
              "ico" if ("icon" in ctype or url.endswith(".ico")) else "png"
        return data, ext
    return None


def render_png(page, data: bytes, ext: str, out: Path) -> None:
    """Render any image type to a 64x64 transparent PNG; back near-white logos with dark."""
    from PIL import Image
    uri = f"data:{MIME[ext]};base64," + base64.b64encode(data).decode()
    page.set_content(f'<body style="margin:0"><img id="i" src="{uri}" '
                     f'style="width:64px;height:64px;object-fit:contain;display:block"></body>')
    page.wait_for_timeout(300)
    page.locator("#i").screenshot(path=str(out), omit_background=True)
    im = Image.open(out).convert("RGBA")
    px = [p for p in im.getdata() if p[3] > 128]
    if len(px) < 64:          # blank / transparent icon (seen on Wix sites) - not a logo
        out.unlink()
        return False
    if sum((r + g + b) / 765 for r, g, b, _ in px) / len(px) > 0.85:
        bg = Image.new("RGBA", im.size, (18, 18, 22, 255))
        bg.alpha_composite(im)
        bg.save(out)
    return True


def main():
    from playwright.sync_api import sync_playwright
    if "--file" in sys.argv:
        i = sys.argv.index("--file")
        slug, path = sys.argv[i + 1], Path(sys.argv[i + 2]).expanduser()
        if slug not in CLIENTS:
            sys.exit(f"unknown client slug: {slug}")
        ext = path.suffix.lstrip(".").lower().replace("jpeg", "png").replace("jpg", "png")
        if ext not in MIME:
            sys.exit(f"unsupported file type: {path.suffix} (png, jpg, svg, ico)")
        out = ROOT / "clients" / slug / "logo.png"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 64, "height": 64})
            ok = render_png(page, path.read_bytes(), ext, out)
            browser.close()
        print(f"{slug}: saved {out.relative_to(ROOT)} ({out.stat().st_size} B)" if ok else f"{slug}: file renders blank, not saved")
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 64, "height": 64})
        for slug, meta in CLIENTS.items():
            if args and slug not in args:
                continue
            out = ROOT / "clients" / slug / "logo.png"
            if out.exists() and not force:
                continue
            domain = re.sub(r"^https?://", "", meta.get("domain") or "").strip("/")  # tolerate a saved scheme
            if not domain:
                print(f"{slug}: no domain in registry, skipped")
                continue
            try:
                icon = download_icon(domain)
            except Exception as e:
                print(f"{slug}: site not reachable ({e}), skipped")
                continue
            if not icon:
                print(f"{slug}: no brand icon found, keeps initials")
                continue
            if not render_png(page, icon[0], icon[1], out):
                print(f"{slug}: icon is blank, keeps initials")
                continue
            print(f"{slug}: saved {out.relative_to(ROOT)} ({out.stat().st_size} B)")
        browser.close()


if __name__ == "__main__":
    main()
