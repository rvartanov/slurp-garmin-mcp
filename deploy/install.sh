#!/usr/bin/env bash
# Install Slurp garmin-mcp as a hardened systemd service. Run as root.
# Safe to run again: it upgrades the package and leaves the environment file,
# the secrets and the Garmin tokens alone.
#
#   sudo deploy/install.sh              # install/upgrade from GitHub (main)
#   sudo REF=v1.0.0 deploy/install.sh   # a tag, branch or commit
#   sudo SOURCE=. deploy/install.sh     # from a local checkout
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/rvartanov/slurp-garmin-mcp}"
REF="${REF:-main}"
SOURCE="${SOURCE:-git+${REPO_URL}@${REF}}"
PYTHON="${PYTHON:-python3}"

SERVICE=slurp-garmin-mcp
RUN_USER=garmin-mcp
PREFIX=/opt/slurp-garmin-mcp
ETC=/etc/slurp-garmin-mcp
STATE=/var/lib/slurp-garmin-mcp
UNIT=/etc/systemd/system/${SERVICE}.service
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 12))' \
    || { echo "Python 3.12 or newer is required (set PYTHON=...)." >&2; exit 1; }
"$PYTHON" -c 'import venv, ensurepip' 2>/dev/null \
    || { echo "Python's venv module is missing (Debian/Ubuntu: apt install python3-venv)." >&2; exit 1; }
case "$SOURCE" in
    git+*) command -v git >/dev/null || { echo "git is required to install from $SOURCE." >&2; exit 1; } ;;
esac

# 1. Service user: no login shell, home is the state directory.
if ! id "$RUN_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$STATE" --no-create-home \
        --shell /usr/sbin/nologin "$RUN_USER"
    echo "Created user $RUN_USER"
fi
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0700 "$STATE"

# 2. Virtualenv with the package.
install -d -m 0755 "$PREFIX"
[ -x "$PREFIX/venv/bin/python" ] || "$PYTHON" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade pip
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade "$SOURCE"
echo "Installed $("$PREFIX/venv/bin/garmin-mcp" --version) in $PREFIX/venv"

# 3. Configuration: created once, never overwritten.
install -d -o root -g "$RUN_USER" -m 0750 "$ETC"
if [ ! -e "$ETC/env" ]; then
    install -o root -g "$RUN_USER" -m 0640 "$HERE/env.example" "$ETC/env"
    echo "Created $ETC/env"
fi
NEW_SECRET=no
if [ ! -e "$ETC/url-secret" ] && grep -q '^GARMIN_MCP_URL_SECRET_FILE=' "$ETC/env"; then
    (umask 027; "$PREFIX/venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))' > "$ETC/url-secret")
    chown root:"$RUN_USER" "$ETC/url-secret"
    chmod 0640 "$ETC/url-secret"
    NEW_SECRET=yes
fi

# 4. Unit.
install -o root -g root -m 0644 "$HERE/systemd/${SERVICE}.service" "$UNIT"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null

# 5. Start only when Garmin tokens are present; otherwise explain the one-time login.
if [ -n "$(find "$STATE" -maxdepth 1 -name '*.json' -print -quit)" ]; then
    systemctl restart "$SERVICE"
    echo "Service restarted: systemctl status $SERVICE"
else
    cat <<MSG

Next: log in to Garmin once (interactive; asks for an MFA code if enabled):

  sudo -u $RUN_USER env GARMINTOKENS=$STATE HOME=$STATE $PREFIX/venv/bin/garmin-mcp-auth

Then start the service:

  sudo systemctl start $SERVICE
MSG
fi

PORT="$(sed -n 's/^GARMIN_MCP_PORT=//p' "$ETC/env" | tail -1)"
cat <<MSG

Configuration:  $ETC/env
Health check:   curl http://127.0.0.1:${PORT:-8000}/healthz
MCP endpoint:   http://127.0.0.1:${PORT:-8000}/<secret>/mcp   (secret: sudo cat $ETC/url-secret)
MSG
[ "$NEW_SECRET" = yes ] && echo "A new URL secret was generated in $ETC/url-secret."
echo "Put a reverse proxy or tunnel with TLS in front before exposing it: docs/deployment.md"
