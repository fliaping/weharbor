#!/usr/bin/with-contenv bash
set -e
export HOME=/config
export XDG_CONFIG_HOME=/config/.config
export XDG_DOCUMENTS_DIR=/config/Documents
export PATH=/usr/local/bin:/opt/weharbor/magpie:/opt/weharbor/harness/node_modules/.bin:/opt/weharbor/node/bin:${PATH}
export DSH_HOME=/config/.local/share/weharbor/harness
export DSH_WORKSPACE=/config/WeHarbor-workspace
export DSH_BIN=/opt/weharbor/harness/node_modules/.bin/dsh
export DSH_WEB_PROXY_PREFIX=/assistant
export MAGPIE_GATEWAY_KEY="${MAGPIE_GATEWAY_KEY:-magpie}"

# First-use dsh workspace. initializeDefault creates
# $Documents/deepseek-harness/default-workspace; expose it as WeHarbor-workspace too.
mkdir -p /config/Documents/deepseek-harness/default-workspace
mkdir -p /config/.local/share/weharbor/assistant-workspace
if [ ! -e /config/WeHarbor-workspace ]; then
  ln -s Documents/deepseek-harness/default-workspace /config/WeHarbor-workspace
fi
chown -R abc:abc /config/Documents /config/WeHarbor-workspace /config/.local/share/weharbor/assistant-workspace 2>/dev/null || true
mkdir -p "${DSH_HOME}/profiles/web"
chown -R abc:abc "${DSH_HOME}" 2>/dev/null || true

exec s6-setuidgid abc node /scripts/workspace/harness-proxy.mjs \
    --host 127.0.0.1 --port 3080 --patch /usr/share/weharbor/harness-mcp.yml --no-open
