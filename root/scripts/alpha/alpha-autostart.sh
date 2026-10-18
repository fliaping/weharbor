#!/bin/bash

/scripts/notifications/notification-autostart.sh
/scripts/weharbor/window-autostart.sh

if [ "${AUTO_START_ALPHA:-true}" = "true" ]; then
    # WeChat stores its profile at /config/xwechat_files; Alpha's Linux
    # discovery also checks ~/Documents/xwechat_files. Keep a compatibility
    # link without replacing an existing user-managed path.
    mkdir -p /config/Documents
    if [ ! -e /config/Documents/xwechat_files ] \
        && [ ! -L /config/Documents/xwechat_files ]; then
        ln -s ../xwechat_files /config/Documents/xwechat_files
    fi

    # Let Openbox and WeChat create their first windows before opening Alpha.
    (
        sleep 3
        /scripts/alpha/alpha-start.sh
    ) >/dev/null 2>&1 &
fi
