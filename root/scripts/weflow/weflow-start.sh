#!/bin/bash

# Clear Electron and legacy AppImage variables inherited from other launchers.
unset APPDIR APPIMAGE ELECTRON_RUN_AS_NODE ELECTRON_NO_ATTACH_CONSOLE

if pgrep -x weflow >/dev/null 2>&1; then
    # Starting Electron again can create a second process tree. Existing windows
    # are focused by the X11 app switcher, so never launch another copy here.
    exit 0
fi

nohup /opt/weflow/weflow --no-sandbox "$@" >/config/weflow.log 2>&1 &
