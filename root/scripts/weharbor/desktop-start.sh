#!/bin/bash
# WeHarbor desktop session start-up for the plain LinuxServer.io Selkies base.
# Runs as abc from the Openbox autostart file.

# A stale PID file from a previous container run stops dbus from starting.
rm -f /run/dbus/pid 2>/dev/null || true

# Let docked tray windows overlap application windows instead of reserving space.
rc="${HOME}/.config/openbox/rc.xml"
mkdir -p "$(dirname "${rc}")"
[ -f "${rc}" ] || cp /etc/xdg/openbox/rc.xml "${rc}"
if grep -A20 '<dock>' "${rc}" | grep -q '<noStrut>no</noStrut>'; then
    sed -i '/<dock>/,/<\/dock>/s/<noStrut>no<\/noStrut>/<noStrut>yes<\/noStrut>/' "${rc}"
    openbox --reconfigure 2>/dev/null || true
fi

if ! pgrep -u "$(id -u)" -x stalonetray >/dev/null 2>&1; then
    nohup /usr/local/bin/stalonetray >/dev/null 2>&1 &
fi

if [ "${AUTO_START_WECHAT:-true}" = "true" ]; then
    /scripts/wechat/wechat-start.sh
fi
