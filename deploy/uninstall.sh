#!/usr/bin/env bash
# Remove the Slurp garmin-mcp service. Run as root.
# Keeps the configuration and Garmin tokens unless called with --purge.
set -euo pipefail

SERVICE=slurp-garmin-mcp
RUN_USER=garmin-mcp
PREFIX=/opt/slurp-garmin-mcp
ETC=/etc/slurp-garmin-mcp
STATE=/var/lib/slurp-garmin-mcp
UNIT=/etc/systemd/system/${SERVICE}.service

PURGE=no
case "${1:-}" in
    "") ;;
    --purge) PURGE=yes ;;
    *) echo "Usage: $0 [--purge]" >&2; exit 2 ;;
esac
if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

if systemctl list-unit-files "${SERVICE}.service" >/dev/null 2>&1; then
    systemctl disable --now "$SERVICE" 2>/dev/null || true
fi
rm -f "$UNIT"
systemctl daemon-reload
rm -rf "$PREFIX"
echo "Removed the service and $PREFIX."

if [ "$PURGE" = yes ]; then
    rm -rf "$ETC" "$STATE"
    if id "$RUN_USER" >/dev/null 2>&1; then
        userdel "$RUN_USER"
    fi
    echo "Removed $ETC, $STATE (Garmin tokens) and user $RUN_USER."
else
    echo "Kept $ETC and $STATE (Garmin tokens). Remove them with: $0 --purge"
fi
