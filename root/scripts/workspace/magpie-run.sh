#!/usr/bin/with-contenv bash
set -euo pipefail
export HOME=/config
export XDG_CONFIG_HOME=/config/.config
# dsh comes from /usr/local/bin (the terminal PATH) so Magpie does not flag it as off-PATH.
export PATH="/opt/weharbor/magpie:/opt/weharbor/node/bin:${PATH}"
export DSH_HOME=/config/.local/share/weharbor/harness
export MAGPIE_BIN="${MAGPIE_BIN:-/opt/weharbor/magpie/magpie}"
export MAGPIE_ADDR="${MAGPIE_ADDR:-127.0.0.1:3425}"
export MAGPIE_WEB_UPSTREAM_PORT="${MAGPIE_WEB_UPSTREAM_PORT:-3431}"
export MAGPIE_WEB_PROXY_PORT="${MAGPIE_WEB_PROXY_PORT:-3430}"
export MAGPIE_WEB_PROXY_PREFIX=/magpie
export DO_NOT_TRACK=1
export MAGPIE_NO_STATS=1
export MAGPIE_DSH_PATCH="${DSH_HOME}/profiles/web/cordis.patch.yml"
export MAGPIE_GATEWAY_KEY="${MAGPIE_GATEWAY_KEY:-magpie}"

mkdir -p /config/.config/magpie /config/.local/share/weharbor/magpie "${DSH_HOME}/profiles/web"
chmod 0700 /config/.config/magpie /config/.local/share/weharbor/magpie "${DSH_HOME}"

python3 - <<'PY'
import json
import os
from pathlib import Path

cfg_dir = Path("/config/.config/magpie")
settings_path = cfg_dir / "settings.json"
defaults = {
    "lang": "zh",
    "redact": True,
    "redactPersonal": True,
    "gatewayMode": "off",
    "noStats": True,
    "noUsageStats": True,
    "noAutoUpdate": True,
    "noAutoDownload": True,
}
try:
    current = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    if not isinstance(current, dict):
        current = {}
except Exception:
    current = {}
changed = not settings_path.exists()
for k, v in defaults.items():
    if k not in current:
        current[k] = v
        changed = True
if changed:
    settings_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    settings_path.chmod(0o600)

dsh_home = Path(os.environ.get("DSH_HOME", "/config/.local/share/weharbor/harness"))
magpie_addr = os.environ.get("MAGPIE_ADDR", "127.0.0.1:3425")
patch_path = dsh_home / "profiles/web/cordis.patch.yml"
patch_text = patch_path.read_text().strip() if patch_path.exists() else ""
if not patch_text or patch_text == "[]":
    patch_path.write_text(
        f'''- id: llm-pi-ai # magpie
  name: "@deepseek-ai/dsh-llm-pi-ai"
  config:
    providers:
      magpie:
        displayName: Magpie
        apiKeyEnv: MAGPIE_GATEWAY_KEY
        api: openai-completions
        baseURL: http://{magpie_addr}/v1
        models: []
'''
    )

# Chinese dsh UI by default (Settings → General → Language still overrides). Seeded once,
# so a later choice or removal by the user is kept.
locale_marker = dsh_home / ".weharbor-locale-seeded"
if not locale_marker.exists():
    text = patch_path.read_text() if patch_path.exists() else ""
    if not any(line.startswith("- id: locale") for line in text.splitlines()):
        block = '- id: locale\n  name: "@deepseek-ai/dsh-client-locale"\n  config:\n    preference: zh\n'
        text = block if text.strip() in ("", "[]") else text.rstrip("\n") + "\n" + block
        patch_path.write_text(text)
    locale_marker.write_text("")

env_path = dsh_home / ".env"
env_lines = env_path.read_text().splitlines() if env_path.exists() else []
if not any(line.startswith("MAGPIE_GATEWAY_KEY=") for line in env_lines):
    env_lines.append("MAGPIE_GATEWAY_KEY=magpie")
    env_path.write_text("\n".join(env_lines) + "\n")
    env_path.chmod(0o600)

creds_path = dsh_home / ".credentials.yaml"
if not creds_path.exists():
    creds_path.write_text("version: 1\nrefs:\n  MAGPIE_GATEWAY_KEY: magpie\n")
    creds_path.chmod(0o600)
elif "MAGPIE_GATEWAY_KEY:" not in creds_path.read_text():
    text = creds_path.read_text()
    if "refs:" in text:
        text = text.rstrip() + "\n  MAGPIE_GATEWAY_KEY: magpie\n"
    else:
        text = text.rstrip() + "\nrefs:\n  MAGPIE_GATEWAY_KEY: magpie\n"
    creds_path.write_text(text)
    creds_path.chmod(0o600)
PY

exec /opt/weharbor/node/bin/node /scripts/workspace/magpie-proxy.mjs --port "${MAGPIE_WEB_PROXY_PORT}"
