#!/bin/bash
# Rebuild dashboard/index.html and push it to the hosted copy if credentials exist.
# See .claude/commands/update-dashboard.md for the manual-run version of this.
set -uo pipefail

# Windows Task Scheduler launches processes with a minimal PATH and Git Bash
# doesn't self-source its usual PATH additions unless it's a login shell — see
# the identical guard in scaffold_client_audit.py's TEMPLATE for the full story.
# This MUST run before WORKSPACE below, since that line itself calls dirname.
# No-op on macOS/Linux.
for _gitbin in "/c/Program Files/Git/usr/bin" "/c/Program Files/Git/bin" \
               "$HOME/AppData/Local/Programs/Git/usr/bin" "$HOME/AppData/Local/Programs/Git/bin"; do
    [[ -d "$_gitbin" ]] && PATH="$_gitbin:$PATH"
done

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE"

# Windows' Python defaults stdout/file I/O to the system codepage (e.g. cp1250) instead of
# UTF-8, which crashes on non-ASCII client-brief/report content (Polish diacritics, etc.) or
# on this script's own "→" in build_dashboard.py's print output. No-op on macOS/Linux.
export PYTHONUTF8=1

"$WORKSPACE/.venv/bin/python3" scripts/build_dashboard.py

if [[ -f "$WORKSPACE/scripts/deploy_dashboard.sh" && -f "$WORKSPACE/scripts/.hostinger-credentials" ]]; then
    bash "$WORKSPACE/scripts/deploy_dashboard.sh"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SKIP] Deploy step skipped — scripts/.hostinger-credentials or scripts/deploy_dashboard.sh not present on this machine (local dashboard/index.html still rebuilt)."
fi
