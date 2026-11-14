#!/bin/bash
# Hourly read-only pulse-check for every client in clients.json.
# No AI judgment involved (daily_check.py is pure deterministic Python) — no
# Claude CLI dependency, no live writes, so no approval/lock ceremony needed,
# unlike the negative-keyword automation. Each client's own run already
# appends to clients/<slug>/reports/daily_check_YYYY-MM-DD.log.
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

# Windows' Python defaults stdout/file I/O to the system codepage instead of
# UTF-8, which crashes on non-ASCII client-brief/report content. No-op elsewhere.
export PYTHONUTF8=1

SLUGS=$("$WORKSPACE/.venv/bin/python3" -c "
import json
with open('clients.json') as f:
    print(' '.join(json.load(f).keys()))
")

for slug in $SLUGS; do
    mkdir -p "$WORKSPACE/clients/$slug/reports"
    "$WORKSPACE/.venv/bin/python3" scripts/daily_check.py "$slug" \
        >> "$WORKSPACE/clients/$slug/reports/hourly_check_runner.log" 2>&1
    if [[ $? -ne 0 ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] daily_check.py failed for $slug" \
            >> "$WORKSPACE/clients/$slug/reports/hourly_check_runner.log"
    fi
done

# Refresh the dashboard so any new flags show up right away.
bash "$WORKSPACE/scripts/run_dashboard_build.sh"
