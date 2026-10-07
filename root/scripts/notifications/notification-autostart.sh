#!/bin/bash

if ! pgrep -x dunst >/dev/null 2>&1; then
    nohup dunst >>/config/dunst.log 2>&1 &
    sleep 0.25
fi

if [ "${ENABLE_BROWSER_NOTIFICATIONS:-true}" != "true" ]; then
    exit 0
fi

if pgrep -f "/scripts/notifications/browser-notification-bridge.py" \
    >/dev/null 2>&1; then
    exit 0
fi

nohup /scripts/notifications/browser-notification-bridge.py \
    >>/config/browser-notifications.log 2>&1 &

sleep 0.25
