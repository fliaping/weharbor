#!/bin/bash
# Provide an unlocked Secret Service (gnome-keyring) on the desktop session bus.
# The collection lives unencrypted in /config/.local/share/keyrings: secrets
# such as Alpha's API token are protected by the volume boundary only.
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    exit 1
fi
if dbus-send --session --print-reply --dest=org.freedesktop.DBus / \
        org.freedesktop.DBus.NameHasOwner string:org.freedesktop.secrets 2>/dev/null \
        | grep -q 'boolean true'; then
    exit 0
fi
keyrings="${HOME}/.local/share/keyrings"
mkdir -p "${keyrings}"
chmod 700 "${HOME}/.local/share/keyrings"
# Without a default collection libsecret pops up a "new keyring password"
# dialog. Seed an unencrypted (plaintext-format) collection once instead.
if [ -z "$(find "${keyrings}" -maxdepth 1 -name '*.keyring' -print -quit)" ]; then
    umask 077
    printf '[keyring]\ndisplay-name=weharbor\nctime=0\nmtime=0\nlock-on-idle=false\nlock-after=false\n' \
        >"${keyrings}/weharbor.keyring"
    printf 'weharbor' >"${keyrings}/default"
fi
gnome-keyring-daemon --replace --daemonize --components=secrets >/dev/null 2>&1
for _ in $(seq 1 20); do
    if dbus-send --session --print-reply --dest=org.freedesktop.DBus / \
        org.freedesktop.DBus.NameHasOwner string:org.freedesktop.secrets 2>/dev/null \
        | grep -q 'boolean true'; then
        exit 0
    fi
    sleep 0.25
done
exit 1
