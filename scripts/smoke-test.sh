#!/usr/bin/env bash
set -euo pipefail
image="${1:-weharbor:0.1.0}"
test_parent="${WEHARBOR_TEST_ROOT:-/tmp}"
mkdir -p "$test_parent"
test_directory="$(mktemp -d "$test_parent/weharbor-smoke.XXXXXX")"
container="weharbor-smoke-$(date +%s)-$$"
cleanup() {
    if [[ "$?" != 0 ]]; then docker logs --tail 160 "$container" >&2 || true; fi
    docker rm -f "$container" >/dev/null 2>&1 || true
    if [[ -d "$test_directory" ]]; then
        docker run --rm --entrypoint /bin/bash -v "$test_directory:/smoke-state" "$image" \
            -c 'find /smoke-state -mindepth 1 -delete' >/dev/null 2>&1 || true
        rmdir "$test_directory" 2>/dev/null || true
    fi
}
trap cleanup EXIT
mkdir "$test_directory/config"
# Seed synthetic state with the permissions seen on NAS volumes. No user data.
python3 - "$test_directory/config" <<'PY'
import sys
from pathlib import Path
for relative in ['.local/share/com.alpha.guard', '.local/state/alpha']:
    root = Path(sys.argv[1]) / relative
    directory = root / 'weharbor-permission-fixture'
    directory.mkdir(parents=True)
    directory.chmod(0o705)
    root.chmod(0o705)
    state = directory / 'state'
    state.write_text('preserve existing state\n')
    state.chmod(0o644)
PY
# The base image hands PASSWORD to `openssl passwd`, which reads a leading "-" as an option.
export PASSWORD="$(python3 -c 'import secrets; print("w" + secrets.token_urlsafe(24))')"
docker run -d --name "$container" --shm-size=1gb --cap-add SYS_PTRACE \
    -e CUSTOM_USER=weharbor -e PASSWORD -e PUID="${WEHARBOR_TEST_UID:-1000}" -e PGID="${WEHARBOR_TEST_GID:-1000}" \
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
def wait_for(path, predicate=lambda response, body: response.status == 200):
    for attempt in range(120):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + path, headers=headers), timeout=5) as response:
                body = response.read()
                if predicate(response, body): return body
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise SystemExit('Service did not become ready: ' + path)
wait_for('notifications/apps', lambda r, b: all(json.loads(b)[a]['running'] and json.loads(b)[a]['windows'] for a in ['wechat','alpha']))
wait_for('analysis/api/health')
analysis = wait_for('analysis/')
assert b'/analysis/_nuxt/' in analysis
wait_for('analysis/agreement')
wait_for('workspace/health')
assistant = wait_for('assistant/', lambda r, b: r.status == 200 and b'<html' in b.lower())
assert b'/assistant/assets/' in assistant
assert b'crypto.randomUUID' in assistant
# Exercise an actual same-origin RPC through the proxy, not only the HTML shell.
assistant_rpc = url + 'assistant/api/host.listDirectory'
for origin, expected in [(os.environ['SMOKE_URL'], 200), ('https://evil.example', 403)]:
    payload = {'type':'client-request', 'rpcId':'weharbor-smoke',
               'method':'host.listDirectory', 'payload':{'path':'/config'}}
    request = urllib.request.Request(assistant_rpc, data=json.dumps(payload).encode(),
        headers={**headers, 'Content-Type':'application/json', 'Origin':origin})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            assert response.status == expected
            assert json.load(response)['result']['ok'] is True
    except urllib.error.HTTPError as error:
        assert error.code == expected, (origin, error.code, error.read())
with urllib.request.urlopen(url + 'workspace/skill/SKILL.md', timeout=5) as response:
    assert b'wechat_prepare_send' in response.read()
for path in ['workspace/mcp', 'workspace/data/health']:
    try:
        urllib.request.urlopen(url + path, timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 401, (path, error.code)
    else:
        raise SystemExit('Workspace transport unexpectedly allows anonymous access: ' + path)
print('Workspace, Linux analysis, Harness and portable Skill are ready; transport auth passed')
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
    assert apps['wechat']['running'] and apps['alpha']['running'], apps
for app in ['wechat', 'alpha']:
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
for app in ['alpha', 'wechat']:
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
    other = 'wechat' if app == 'alpha' else 'alpha'
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
import hashlib, json, stat, subprocess
import urllib.request
from pathlib import Path
token = Path('/config/.config/weharbor/workspace.token').read_text().strip()
request = urllib.request.Request('http://127.0.0.1:8766/mcp',
    data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'}).encode(),
    headers={'Authorization':'Bearer ' + token, 'Content-Type':'application/json'})
with urllib.request.urlopen(request, timeout=5) as response:
    tools = json.load(response)['result']['tools']
assert len(tools) == 12
print('Authenticated MCP exposes twelve tools')
for relative in ['.local/share/com.alpha.guard', '.local/state/alpha']:
    root = Path('/config') / relative
    directory = root / 'weharbor-permission-fixture'
    state = directory / 'state'
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    assert state.read_text() == 'preserve existing state\n'
print('Alpha private state permissions repaired without changing contents')
lock = json.loads(Path('/usr/share/weharbor/versions.lock.json').read_text())
version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'wechat'], text=True)
assert version == lock['wechat']['version'], version
alpha = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'alpha'], text=True)
assert alpha == lock['alpha']['version'], alpha
subprocess.run(['dpkg', '--verify', 'alpha'], check=True)
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
print('Pinned versions, unmodified packages and data-path compatibility passed')
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
alpha = [r for r in rules if r.get('class') == 'alpha-desktop' and r.get('title') == 'Alpha'][-1]
assert alpha.find('{*}iconic').text == 'yes'
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
