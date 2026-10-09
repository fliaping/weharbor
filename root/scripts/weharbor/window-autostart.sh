#!/bin/bash
set -euo pipefail

if [[ "${ENABLE_WINDOW_DEFAULTS:-true}" != true ]]; then
    exit 0
fi

python3 /scripts/weharbor/window-layout.py --configure
mkdir -p /config/.local/log
nohup python3 /scripts/weharbor/window-layout.py \
    >>/config/.local/log/weharbor-window-layout.log 2>&1 </dev/null &
