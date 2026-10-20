#!/usr/bin/with-contenv bash
set -e
export HOME=/config
export WECHAT_TOOL_CAPTURE_HELPER=/usr/local/bin/weharbor-capture-key
export PYTHONPATH=/opt/weharbor/analysis/src
export WECHAT_TOOL_DATA_DIR=/config/.local/share/weharbor/analysis
export WECHAT_TOOL_OUTPUT_DIR=${WECHAT_TOOL_DATA_DIR}/output
export WECHAT_TOOL_UI_DIR=/opt/weharbor/analysis/ui
exec s6-setuidgid abc /opt/weharbor/python/bin/python -m uvicorn \
    wechat_decrypt_tool.api:app --host 127.0.0.1 --port 10392 --root-path /analysis
