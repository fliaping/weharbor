#!/bin/bash

/scripts/notifications/notification-autostart.sh

if [ "${AUTO_START_WEFLOW:-true}" = "true" ]; then
    # WeChat in this image stores its profile at /config/xwechat_files, while
    # WeFlow's Linux auto-detection checks ~/Documents/xwechat_files. Keep a
    # compatibility link without replacing an existing user-managed path.
    mkdir -p /config/Documents
    if [ ! -e /config/Documents/xwechat_files ] \
        && [ ! -L /config/Documents/xwechat_files ]; then
        ln -s ../xwechat_files /config/Documents/xwechat_files
    fi

    # Let Openbox and WeChat create their first windows before opening WeFlow.
    (
        sleep 3
        /scripts/weflow/weflow-start.sh
    ) >/dev/null 2>&1 &
fi
