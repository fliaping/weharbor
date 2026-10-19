#!/bin/bash
# Start WeChat once; the X11 app switcher focuses an existing window instead.
if pgrep -x wechat >/dev/null 2>&1; then
    exit 0
fi
mkdir -p /config/.local/log
export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
export QT_ACCESSIBILITY=1
export NO_AT_BRIDGE=0
nohup /usr/bin/wechat >>/config/.local/log/wechat.log 2>&1 &
