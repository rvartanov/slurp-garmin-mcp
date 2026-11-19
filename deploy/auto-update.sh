#!/usr/bin/env bash
# Update a running Slurp garmin-mcp install to the newest commit on main whose
# CI passed, restart the service and roll back when it does not become ready.
# Meant for a systemd timer (deploy/systemd/slurp-garmin-mcp-update.*); runs
# as the service's user, no root needed for a user-unit install.
#
# Settings (environment, e.g. ~/.config/slurp-garmin-mcp/update.env):
#   REPO       GitHub repository             (rvartanov/slurp-garmin-mcp)
#   BRANCH     branch to follow               (main)
#   SRC        clean checkout used to install (~/.local/share/slurp-garmin-mcp/src)
#   VENV       virtualenv of the service      (~/.local/share/slurp-garmin-mcp/venv)
#   SERVICE    systemd unit to restart        (slurp-garmin-mcp)
#   SCOPE      --user or --system             (--user)
#   READY_URL  readiness probe                (http://127.0.0.1:8000/readyz)
#   STATE      file with the deployed commit  (~/.local/state/slurp-garmin-mcp/deployed-commit)
#   UV         uv executable                  (uv)
set -euo pipefail

REPO="${REPO:-rvartanov/slurp-garmin-mcp}"
BRANCH="${BRANCH:-main}"
SRC="${SRC:-$HOME/.local/share/slurp-garmin-mcp/src}"
VENV="${VENV:-$HOME/.local/share/slurp-garmin-mcp/venv}"
SERVICE="${SERVICE:-slurp-garmin-mcp}"
SCOPE="${SCOPE:---user}"
READY_URL="${READY_URL:-http://127.0.0.1:8000/readyz}"
STATE="${STATE:-$HOME/.local/state/slurp-garmin-mcp/deployed-commit}"
UV="${UV:-uv}"

log() { echo "auto-update: $*"; }

if [ ! -d "$SRC/.git" ]; then
    git clone -q "https://github.com/${REPO}.git" "$SRC"
fi
git -C "$SRC" fetch -q origin "$BRANCH"
target="$(git -C "$SRC" rev-parse "origin/${BRANCH}")"
current="$(cat "$STATE" 2>/dev/null || true)"
if [ "$target" = "$current" ]; then
    exit 0
fi

# Only deploy a commit whose check runs all finished successfully (public
# repository: the unauthenticated API is enough for a 15-minute timer).
runs="$(curl -fsS -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/commits/${target}/check-runs?per_page=100")"
verdict="$(printf '%s' "$runs" | python3 -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs:
    print("pending")
elif any(r["status"] != "completed" for r in runs):
    print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("green")
else:
    print("red")
')"
if [ "$verdict" != "green" ]; then
    log "${target:0:7} not deployed: CI is ${verdict}"
    exit 0
fi

install_commit() {
    local commit="$1" req
    git -C "$SRC" checkout -q --detach "$commit"
    req="$(mktemp)"
    (cd "$SRC" && "$UV" export -q --frozen --no-dev --no-emit-project --no-hashes -o "$req")
    "$UV" pip install -q --python "$VENV/bin/python" -r "$req"
    "$UV" pip install -q --python "$VENV/bin/python" --no-deps --reinstall-package slurp-garmin-mcp "$SRC"
    rm -f "$req"
}

ready() {
    local _
    for _ in $(seq 1 60); do
        if [ "$(curl -fsS --max-time 5 "$READY_URL" 2>/dev/null)" = '{"status":"ready"}' ]; then
            return 0
        fi
        sleep 2
    done
    return 1
}

log "deploying ${target:0:7} (was ${current:0:7})"
install_commit "$target"
systemctl "$SCOPE" restart "$SERVICE"
if ready; then
    mkdir -p "$(dirname "$STATE")"
    echo "$target" >"$STATE"
    log "${target:0:7} is live"
    exit 0
fi

log "${target:0:7} did not become ready; rolling back"
if [ -n "$current" ]; then
    install_commit "$current"
    systemctl "$SCOPE" restart "$SERVICE"
    if ready; then
        log "rolled back to ${current:0:7}"
    else
        log "rollback to ${current:0:7} is not ready either"
    fi
fi
exit 1
