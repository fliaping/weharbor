#!/usr/bin/with-contenv bash
set -e
export HOME=/config
export XDG_CONFIG_HOME=/config/.config
export PATH=/opt/weharbor/magpie:/opt/weharbor/harness/node_modules/.bin:/opt/weharbor/node/bin:${PATH}
export DSH_HOME=/config/.local/share/weharbor/harness
export DSH_WORKSPACE=/config/.local/share/weharbor/assistant-workspace
export DSH_BIN=/opt/weharbor/harness/node_modules/.bin/dsh
export DSH_WEB_PROXY_PREFIX=/assistant
export MAGPIE_GATEWAY_KEY="${MAGPIE_GATEWAY_KEY:-magpie}"
exec s6-setuidgid abc node /scripts/workspace/harness-proxy.mjs \
    --host 127.0.0.1 --port 3080 --patch /usr/share/weharbor/harness-mcp.yml --no-open
