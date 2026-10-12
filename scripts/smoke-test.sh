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
import base64, json, os, struct, time, urllib.error, urllib.request
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
for path in ['weharbor.webmanifest', 'weharbor-sw.js', 'pwa-icons/icon-512.png',
             'weharbor-apps.js', 'notifications/apps']:
    try:
        urllib.request.urlopen(url + path, timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 401, (path, error.code)
    else:
        raise SystemExit('PWA resource unexpectedly allows anonymous access: ' + path)
with urllib.request.urlopen(urllib.request.Request(url + 'weharbor.webmanifest', headers=headers), timeout=5) as response:
    assert response.headers.get_content_type() == 'application/manifest+json'
    manifest = json.load(response)
    assert manifest['name'] == 'WeHarbor｜微港'
    assert manifest['start_url'] == manifest['scope'] == './'
for icon in manifest['icons']:
    with urllib.request.urlopen(urllib.request.Request(url + icon['src'], headers=headers), timeout=5) as response:
        data = response.read()
        assert data[:8] == b'\x89PNG\r\n\x1a\n'
        width, height = struct.unpack('>II', data[16:24])
        assert icon['sizes'] == f'{width}x{height}'
with urllib.request.urlopen(urllib.request.Request(url + 'weharbor-sw.js', headers=headers), timeout=5) as response:
    assert response.headers.get_content_type() == 'application/javascript'
    assert response.headers['Cache-Control'] == 'no-cache'
    assert b'event.respondWith' in response.read()
print('Browser authentication, notifications and PWA resources passed')
with urllib.request.urlopen(urllib.request.Request(url + 'notifications/apps', headers=headers), timeout=5) as response:
    apps = json.load(response)
    assert apps['wechat']['running'] and apps['weflow']['running'], apps
for app in ['wechat', 'weflow']:
    restart_url = url + f'notifications/apps/{app}/restart'
    for extra in [{}, {'Content-Type': 'application/json', 'X-WeHarbor-Action': 'restart',
                       'Origin': 'https://evil.example'}]:
        try:
            urllib.request.urlopen(urllib.request.Request(restart_url, data=b'{}',
                                   headers={**headers, **extra}), timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 403, error.code
        else:
            raise SystemExit('Restart accepted a cross-origin or unguarded request')
    with urllib.request.urlopen(urllib.request.Request(restart_url, data=b'{}',
            headers={**headers, 'Content-Type': 'application/json',
                     'X-WeHarbor-Action': 'restart'}), timeout=30) as response:
        assert json.load(response)['running']
print('Authenticated application restarts and cross-origin protection passed')
def app_status():
    with urllib.request.urlopen(urllib.request.Request(url + 'notifications/apps', headers=headers), timeout=5) as response:
        return json.load(response)
for app in ['weflow', 'wechat']:
    for attempt in range(60):
        if app_status()[app]['windows']:
            break
        time.sleep(.5)
    else:
        raise SystemExit('Application did not create a selectable window: ' + app)
    switch_headers = {**headers, 'Content-Type': 'application/json', 'X-WeHarbor-Action': 'switch'}
    switch_url = url + f'notifications/apps/{app}/switch'
    try:
        urllib.request.urlopen(urllib.request.Request(switch_url, data=b'{}',
            headers={**switch_headers, 'Origin': 'https://evil.example'}), timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 403
    else:
        raise SystemExit('Switch accepted cross-origin request')
    with urllib.request.urlopen(urllib.request.Request(switch_url, data=b'{}', headers=switch_headers), timeout=10) as response:
        assert json.load(response)['windowId']
    other = 'wechat' if app == 'weflow' else 'weflow'
    for attempt in range(30):
        state = app_status()
        if state[app]['active'] and all(w['minimized'] for w in state[other]['windows']):
            break
        time.sleep(.2)
    else:
        raise SystemExit('Window focus/minimize did not settle: ' + app)
    try:
        urllib.request.urlopen(urllib.request.Request(switch_url,
            data=b'{"windowId": 4294967295}', headers=switch_headers), timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        raise SystemExit('Switch accepted an unowned window')
print('Web application switching, ownership and minimize behavior passed')
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
subprocess.run(['pgrep', '-f', '^python3 /scripts/weharbor/window-layout.py$'],
               check=True, stdout=subprocess.DEVNULL)
subprocess.run(['dpkg', '--verify', 'wechat'], check=True)
assert Path('/usr/bin/wechat').resolve() == Path('/scripts/weharbor/wechat-launch.py')
clients = []
for executable in Path('/proc').glob('[0-9]*/exe'):
    try:
        if executable.resolve() == Path('/opt/wechat/wechat'):
            env = dict(item.split(b'=', 1) for item in
                       (executable.parent / 'environ').read_bytes().split(b'\0') if b'=' in item)
            assert float(env[b'QT_FONT_DPI']) > 0
            clients.append(executable.parent.name)
    except (FileNotFoundError, PermissionError):
        continue
assert clients, 'WeChat did not start through the DPI compatibility launcher'
setting = Path('/config/.config/weharbor/wechat-dpi')
setting.parent.mkdir(parents=True, exist_ok=True)
setting.write_text('144\n')
print('Pinned versions, original ASAR and data-path compatibility passed')
PY
docker restart "$container" >/dev/null
ready=false
for ((attempt=0; attempt<60; attempt++)); do
    if docker exec "$container" weharbor-health >/dev/null 2>&1; then ready=true; break; fi
    sleep 2
done
[[ "$ready" == true ]] || { printf '%s\n' 'Restart health check failed' >&2; exit 1; }
docker exec -i "$container" python3 - <<'PY'
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
subprocess.run(['pgrep', '-f', '^python3 /scripts/weharbor/window-layout.py$'],
               check=True, stdout=subprocess.DEVNULL)
config = Path('/config/.config/openbox/rc.xml')
assert config.read_text().count('WeHarbor window defaults: begin') == 1
rules = ET.parse(config).findall('.//{*}application')
wechat = [r for r in rules if r.get('class') == 'wechat'][-1]
assert wechat.find('{*}maximized').text == 'no'
weflow = [r for r in rules if r.get('class') == 'weflow' and r.get('title') == 'WeFlow'][-1]
assert weflow.find('{*}iconic').text == 'yes'
assert Path('/config/.config/weharbor/wechat-dpi').read_text().strip() == '144'
clients = []
for executable in Path('/proc').glob('[0-9]*/exe'):
    try:
        if executable.resolve() == Path('/opt/wechat/wechat'):
            env = dict(item.split(b'=', 1) for item in
                       (executable.parent / 'environ').read_bytes().split(b'\0') if b'=' in item)
            assert env[b'QT_FONT_DPI'] == b'144', 'Persisted WeChat DPI was not applied'
            clients.append(executable.parent.name)
    except (FileNotFoundError, PermissionError):
        continue
assert clients, 'WeChat did not restart'
print('Window helper, main-only maximize defaults and repeatable restart passed')
PY
printf '%s\n' 'WeHarbor fresh-profile smoke test passed, including restart'
