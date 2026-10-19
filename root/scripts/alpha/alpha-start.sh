#!/bin/bash
# Start Alpha once. Alpha keeps its HTTP API token in Electron safeStorage,
# which on Linux needs a Secret Service; plain-text storage is refused.
unset APPDIR APPIMAGE ELECTRON_RUN_AS_NODE ELECTRON_NO_ATTACH_CONSOLE

if pgrep -f '^/opt/Alpha/alpha( |$)' >/dev/null 2>&1; then
    exit 0
fi

umask 077
python3 /scripts/alpha/prepare-private-state.py || exit 1
/scripts/alpha/keyring-start.sh || echo "WeHarbor: Secret Service unavailable" >&2
mkdir -p /config/.local/log
nohup /opt/Alpha/alpha --no-sandbox --password-store=gnome-libsecret "$@" \
    >>/config/.local/log/alpha.log 2>&1 &
