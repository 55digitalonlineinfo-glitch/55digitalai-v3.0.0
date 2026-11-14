#!/bin/bash
# Builds a clean, distributable copy of the toolkit for handing to a buyer —
# strips real credentials, real client data, and local build/runtime artifacts
# without touching this working copy. Mirrors .gitignore's intent, but doesn't
# rely on git (this project isn't necessarily a git repo), so it's a plain
# rsync exclude list kept in sync with .gitignore by hand.
#
# Usage: scripts/build_release.sh [output-dir]
#   Default output dir: ../55digitalai-v<VERSION> (sibling of this project, so
#   it can't accidentally end up nested inside itself), where <VERSION> comes
#   from the VERSION file at the project root — bump that file before cutting
#   a new release so buyers can tell which copy is newer.
# Produces both the stripped folder and a .zip of it.
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(cat "$WORKSPACE/VERSION" 2>/dev/null || echo "0.0.0")"
OUT_DIR="${1:-$WORKSPACE/../55digitalai-v${VERSION}}"
OUT_DIR="$(cd "$(dirname "$OUT_DIR")" && pwd)/$(basename "$OUT_DIR")"

if [[ "$OUT_DIR" == "$WORKSPACE"* ]]; then
    echo "Output dir must not be inside $WORKSPACE (got $OUT_DIR) — pick a sibling or elsewhere."
    exit 1
fi

echo "Building release v$VERSION from $WORKSPACE"
echo "Output: $OUT_DIR"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

rsync -a "$WORKSPACE/" "$OUT_DIR/" \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude "venv/" \
    --exclude "__pycache__/" \
    --exclude "*.pyc" \
    --exclude ".DS_Store" \
    --exclude "Thumbs.db" \
    --exclude "node_modules/" \
    --exclude "dashboard/" \
    --exclude "change_log.db" \
    --exclude "term_cache.db" \
    --exclude "brand_config.json" \
    --exclude "scripts/_scheduled/" \
    --exclude ".claude/scheduled_tasks.lock" \
    --exclude ".claude/settings.local.json" \
    --exclude "google-ads.yaml" \
    --exclude ".env" \
    --exclude "*.json.bak" \
    --exclude "credentials.json" \
    --exclude "merchant-center-credentials.json" \
    --exclude "scripts/.hostinger-credentials" \
    --exclude "scripts/.license_admin_token" \
    --exclude "scripts/issue_license_key.py" \
    --exclude "license-server/" \
    --exclude "clients.json" \
    --exclude ".release-blocklist" \
    --exclude "guidelines/" \
    --exclude "seo-audits/" \
    --include "clients/" \
    --include "clients/_template/" \
    --include "clients/_template/**" \
    --exclude "clients/*"

# Ship safe Claude Code permissions (ask before acting), never this machine's own settings.
cat > "$OUT_DIR/.claude/settings.json" <<'JSON'
{
  "permissions": {
    "allow": []
  }
}
JSON

# Confirm no real client folders slipped through (belt-and-suspenders on the
# rsync include/exclude ordering above).
for d in "$OUT_DIR"/clients/*/; do
    slug="$(basename "$d")"
    if [[ "$slug" != "_template" ]]; then
        echo "ERROR: real client folder leaked into release: clients/$slug — aborting."
        rm -rf "$OUT_DIR"
        exit 1
    fi
done

# Fail loudly if anything that looks like a real secret made it in.
if [[ -f "$OUT_DIR/google-ads.yaml" ]]; then
    echo "ERROR: google-ads.yaml leaked into release — aborting."
    rm -rf "$OUT_DIR"
    exit 1
fi

# Seller-only tooling (license issuing/admin token/server source) must never ship.
for leak in "license-server" "scripts/issue_license_key.py" "scripts/.license_admin_token"; do
    if [[ -e "$OUT_DIR/$leak" ]]; then
        echo "ERROR: seller-only file leaked into release: $leak — aborting."
        rm -rf "$OUT_DIR"
        exit 1
    fi
done

# Real client names/domains (from this machine's clients.json) or local home paths anywhere in the
# release = abort. Catches examples copied from real work into prompts, docs or generated files.
if ! python3 - "$WORKSPACE/clients.json" "$OUT_DIR" <<'PY'
import json, os, re, sys
cfg, out = sys.argv[1], sys.argv[2]
terms = set()
if os.path.exists(cfg):
    for slug, c in json.load(open(cfg, encoding="utf-8")).items():
        terms.add(slug)
        dom = re.sub(r"^https?://(www\.)?", "", c.get("domain") or "").strip("/")
        if dom: terms.update({dom, dom.split(".")[0]})
        for w in re.findall(r"[\w-]{5,}", c.get("name") or ""): terms.add(w)
# optional private extra terms, one per line (other client names, domains, people): .release-blocklist
bl = os.path.join(os.path.dirname(cfg), ".release-blocklist")
if os.path.exists(bl):
    terms.update(l.strip() for l in open(bl, encoding="utf-8") if l.strip() and not l.startswith("#"))
terms = {t.lower() for t in terms if len(t) >= 4}
pat = re.compile("|".join([r"(?-i:/Users/[A-Za-z])", r"(?-i:/home/[a-z]+/)"] + [re.escape(t) for t in sorted(terms)]), re.I)
hits = []
for root, _, files in os.walk(out):
    for f in files:
        path = os.path.join(root, f)
        try: text = open(path, "rb").read().decode("utf-8", "ignore")
        except OSError: continue
        for m in pat.finditer(text):
            hits.append(f"{os.path.relpath(path, out)}: {m.group(0)}")
            break
if hits:
    print("ERROR: client names / local paths found in the release:"); print("\n".join(hits[:50])); sys.exit(1)
print(f"Leak check passed ({len(terms)} client terms checked).")
PY
then
    rm -rf "$OUT_DIR"
    exit 1
fi

echo
echo "Release folder built: $OUT_DIR"

if command -v zip >/dev/null 2>&1; then
    ZIP_PATH="${OUT_DIR}.zip"
    rm -f "$ZIP_PATH"
    (cd "$(dirname "$OUT_DIR")" && zip -qr "$ZIP_PATH" "$(basename "$OUT_DIR")")
    echo "Zip built: $ZIP_PATH"
fi

echo
echo "clients/ in the release contains only:"
find "$OUT_DIR/clients" -mindepth 1 -maxdepth 1 -type d
