#!/usr/bin/env bash
set -euo pipefail
image="${1:-weharbor:0.1.0}"
test_parent="${WEHARBOR_TEST_ROOT:-/tmp}"
mkdir -p "$test_parent"
test_directory="$(mktemp -d "$test_parent/weharbor-smoke.XXXXXX")"
container="weharbor-smoke-$(date +%s)-$$"
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    if [[ -d "$test_directory" ]]; then
        docker run --rm --entrypoint /bin/bash -v "$test_directory:/smoke-state" "$image" \
            -c 'find /smoke-state -mindepth 1 -delete' >/dev/null 2>&1 || true
        rmdir "$test_directory" 2>/dev/null || true
    fi
}
trap cleanup EXIT
mkdir "$test_directory/config"
export PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
docker run -d --name "$container" --shm-size=1gb --cap-add SYS_PTRACE \
    -e CUSTOM_USER=weharbor -e PASSWORD -e PUID="$(id -u)" -e PGID="$(id -g)" \
    -e TZ=Asia/Shanghai -v "$test_directory/config:/config" \
    -p 127.0.0.1::3000 "$image" >/dev/null
ready=false
for ((attempt=0; attempt<90; attempt++)); do
    if docker exec "$container" weharbor-health >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [[ "$ready" != true ]]; then
    printf '%s\n' 'Fresh-profile health check failed' >&2
    docker logs --tail 120 "$container" >&2
    exit 1
fi
export SMOKE_URL="http://$(docker port "$container" 3000/tcp | head -n 1)"
python3 - <<'PY'
import base64, os, urllib.error, urllib.request
url = os.environ['SMOKE_URL'] + '/'
try:
    urllib.request.urlopen(url, timeout=5)
except urllib.error.HTTPError as error:
    assert error.code == 401, error.code
else:
    raise SystemExit('Browser unexpectedly allows anonymous access')
headers = {'Authorization': 'Basic ' + base64.b64encode(('weharbor:' + os.environ['PASSWORD']).encode()).decode()}
with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5) as response:
    assert response.status == 200
    assert b'browser-notifications.js' in response.read()
print('Browser authentication and notification integration passed')
PY
docker exec -i "$container" python3 - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
lock = json.loads(Path('/usr/share/weharbor/versions.lock.json').read_text())
version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'wechat'], text=True)
assert version == lock['wechat']['version'], version
asar = Path('/opt/weflow/resources/app.asar')
assert hashlib.sha256(asar.read_bytes()).hexdigest() == lock['weflow']['asar_sha256']
assert Path('/config/Documents/xwechat_files').is_symlink()
subprocess.run(['dpkg', '--verify', 'wechat'], check=True)
print('Pinned versions, original ASAR and data-path compatibility passed')
PY
docker restart "$container" >/dev/null
ready=false
for ((attempt=0; attempt<60; attempt++)); do
    if docker exec "$container" weharbor-health >/dev/null 2>&1; then ready=true; break; fi
    sleep 2
done
[[ "$ready" == true ]] || { printf '%s\n' 'Restart health check failed' >&2; exit 1; }
printf '%s\n' 'WeHarbor fresh-profile smoke test passed, including restart'
