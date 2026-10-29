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
# Chromium requires private temporary-directory modes, including under nested
# fuse-overlayfs. DSH also loads native addons from its temporary cache.
docker run -d --name "$container" --shm-size=1gb --cap-add SYS_PTRACE \
    --tmpfs /tmp:rw,exec,nosuid,nodev,mode=1777 \
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
import base64, html, http.cookiejar, json, os, re, struct, time, urllib.error, urllib.parse, urllib.request
url = os.environ['SMOKE_URL'] + '/'
try:
    urllib.request.urlopen(url, timeout=5)
except urllib.error.HTTPError as error:
    assert error.code == 401, error.code
else:
    raise SystemExit('Browser unexpectedly allows anonymous access')
headers = {'Authorization': 'Basic ' + base64.b64encode(('weharbor:' + os.environ['PASSWORD']).encode()).decode()}
# DSH 0.2 exchanges its launch token for an HttpOnly browser session cookie.
# Keep anonymous transport checks on urllib's separate default opener.
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def wait_for(path, predicate=lambda response, body: response.status == 200):
    for attempt in range(120):
        try:
            with browser.open(urllib.request.Request(url + path, headers=headers), timeout=5) as response:
                body = response.read()
                if predicate(response, body): return body
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise SystemExit('Service did not become ready: ' + path)
wait_for('notifications/apps', lambda r, b: all(json.loads(b)[a]['running'] and json.loads(b)[a]['windows'] for a in ['wechat','alpha']))
wait_for('analysis/api/health')
capabilities = json.loads(wait_for('analysis/api/advanced/capabilities'))
assert capabilities['counts'] == {'total': 79, 'available': 48}, capabilities['counts']
assert capabilities['features']['contact-search']['state'] == 'blocked'
assert capabilities['features']['send-file']['state'] == 'available'
assert capabilities['features']['contact-list-labels']['state'] == 'available'
assert capabilities['features']['automation-onboarding']['state'] == 'available'
assert capabilities['features']['automation-moments-sync']['state'] == 'available'
assert 'automation-moments-follow' not in capabilities['features']
assert all(value['unlocked'] for value in capabilities['features'].values())
# Exercise browser -> nginx -> analysis -> authenticated workspace streaming.
# Upload only; do not prepare or send anything to a WeChat account.
upload = url + 'analysis/api/advanced/attachments/weharbor-smoke.bin'
sample = b'WeHarbor private upload fixture\n' * 70000
for origin, expected in [('https://evil.example', 403), (os.environ['SMOKE_URL'], 200)]:
    request = urllib.request.Request(upload, method='PUT', data=sample,
        headers={**headers, 'Content-Type':'application/octet-stream', 'Origin':origin})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == expected
            result = json.load(response)
            assert result['size'] == len(sample)
            assert result['filename'] == 'weharbor-smoke.bin'
            assert result['path'].startswith('/config/.local/share/weharbor/uploads/')
    except urllib.error.HTTPError as error:
        assert error.code == expected, (origin, error.code, error.read())
print('48 advanced execution paths and private streaming upload passed; no WeChat action submitted')
analysis = wait_for('analysis/')
assert b'/analysis/_nuxt/' in analysis
assert b'ui.first_use_agreement' not in analysis
assert b'first-use-route-guard' not in analysis
wait_for('analysis/agreement')
wait_for('workspace/health')
assistant = wait_for('assistant/', lambda r, b: r.status == 200 and b'<html' in b.lower())
scripts = re.findall(r'<script[^>]+src="([^"]+)"', assistant.decode())
assert any('/assets/' in path for path in scripts), 'DSH entry script is absent'
for path in scripts:
    asset_url = urllib.parse.urljoin(url + 'assistant/', html.unescape(path))
    assert asset_url.startswith(url + 'assistant/'), asset_url
    with browser.open(urllib.request.Request(asset_url, headers=headers), timeout=15) as response:
        assert response.status == 200 and response.read(), asset_url
assert b'crypto.randomUUID' in assistant
# Exercise an actual same-origin RPC through the proxy, not only the HTML shell.
assistant_rpc = url + 'assistant/api/settings/describe'
for origin, expected in [(os.environ['SMOKE_URL'], 200), ('https://evil.example', 403)]:
    payload = {'type':'client-request', 'rpcId':'weharbor-smoke',
               'method':'settings/describe', 'payload':{'args':{}}}
    request = urllib.request.Request(assistant_rpc, data=json.dumps(payload).encode(),
        headers={**headers, 'Content-Type':'application/json', 'Origin':origin})
    try:
        with browser.open(request, timeout=15) as response:
            assert response.status == expected
            assert json.load(response)['result']['ok'] is True
    except urllib.error.HTTPError as error:
        assert error.code == expected, (origin, error.code, error.read())
def harness_rpc(method, payload):
    request = urllib.request.Request(url + 'assistant/api/' + method,
        data=json.dumps({'type':'client-request', 'rpcId':'weharbor-skill-smoke',
                         'method':method, 'payload':payload}).encode(),
        headers={**headers, 'Content-Type':'application/json', 'Origin':os.environ['SMOKE_URL']})
    with browser.open(request, timeout=20) as response:
        result = json.load(response)['result']
        assert result['ok'] is True, result
        return result['value']
# A local empty session exercises official Skill discovery without a model call.
session = harness_rpc('session/create', {'args':{'request':{'cwd':'/config/.local/share/weharbor/assistant-workspace'}}})
skills = harness_rpc('skills/list', {'args':{'request':{'sessionId':session['sessionId']}}})['skills']
assert any(skill['name'] == 'weharbor-api' and skill['modelInvocable'] for skill in skills), skills
assert any(skill['name'] == 'wechat-analysis-actions' and skill['modelInvocable'] for skill in skills), skills
print('Official Harness discovers the WeHarbor action/automation Skill; no model request made')
magpie_page = wait_for('magpie/', lambda r, b: r.status == 200 and b'<title>magpie</title>' in b)
magpie_boot = wait_for('magpie/boot.js', lambda r, b: r.status == 200 and b'window.bootPrefs' in b)
assert b'const prefix = "/magpie"' in magpie_boot
magpie_state = json.loads(wait_for('magpie/api/state'))
assert any(agent.get('id') == 'dsh' for agent in magpie_state.get('agents', [])), magpie_state.get('agents')
assert magpie_state.get('settings', {}).get('redact') is True
assert magpie_state.get('settings', {}).get('redactPersonal') is True
mask_req = urllib.request.Request(url + 'magpie/api/masking/preview',
    data=json.dumps({'text': '手机号 13800138000 密码 s3cr3tPass123!'}).encode(),
    headers={**headers, 'Content-Type': 'application/json', 'Origin': os.environ['SMOKE_URL']})
with browser.open(mask_req, timeout=15) as response:
    preview = json.load(response)
    assert preview['off'] is False and len(preview['hits']) >= 2, preview
    assert '13800138000' not in preview['text'] and '{{PHONE_' in preview['text'], preview
print('Magpie web UI, local desensitization and DeepSeek Harness agent discovery passed')
payload = {'type':'client-request', 'rpcId':'weharbor-plugins',
           'method':'pluginInventory/list', 'payload':{'args':{}}}
request = urllib.request.Request(url + 'assistant/api/pluginInventory/list',
    data=json.dumps(payload).encode(), headers={**headers,
        'Content-Type':'application/json', 'Origin':os.environ['SMOKE_URL']})
with browser.open(request, timeout=15) as response:
    plugins = json.load(response)['result']
    assert plugins['ok'] is True
    for entry in ['include:weharbor-mcp', 'include:wechat-analysis-mcp']:
        assert any(p['entryId'] == entry and p['fiberPhase'] == 'active'
                   for p in plugins['value']['entries'])
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
with urllib.request.urlopen(urllib.request.Request(url + 'weharbor-apps.js', headers=headers), timeout=5) as response:
    dock = response.read()
    for marker in [b'weharbor-apps-button', b'matchShortcut', b'prefers-reduced-motion', b'weharbor-dock-shortcuts']:
        assert marker in dock, marker
with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5) as response:
    assert re.search(rb'<script src="\./weharbor-apps\.js\?v=[0-9a-f]{12}"></script>', response.read())
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
assert len(tools) == 35
assert {'wechat_send_file', 'wechat_chat_set_mute', 'wechat_prepare_operation', 'wechat_contact_list_labels', 'wechat_contact_set_labels'} <= {t['name'] for t in tools}
by_name = {t['name']: t for t in tools}
assert by_name['wechat_contact_list_labels']['annotations']['readOnlyHint'] is True
assert by_name['wechat_contact_set_labels']['inputSchema']['properties']['labels']['items'] == {'type': 'string'}
assert by_name['wechat_sns_autorefresh']['annotations']['readOnlyHint'] is False
print('Authenticated MCP exposes 35 tools')
payload = json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list'}) + '\n'
result = subprocess.run(['s6-setuidgid', 'abc', 'env',
    'WECHAT_ANALYSIS_MCP_TOKEN_FILE=/config/.local/share/weharbor/analysis/advanced/mcp.token',
    '/opt/weharbor/python/bin/python', '/opt/weharbor/analysis/scripts/advanced_mcp_stdio.py'],
    input=payload, capture_output=True, text=True, timeout=15, check=True)
analysis_tools = json.loads(result.stdout)['result']['tools']
assert len(analysis_tools) == 19
assert sum(tool['annotations']['readOnlyHint'] for tool in analysis_tools) == 12
assert {'wechat_prepare_action', 'wechat_commit_action', 'wechat_create_task', 'wechat_timeline'} <= {tool['name'] for tool in analysis_tools}
assert 'wechat-analysis-mcp' in Path('/usr/share/weharbor/harness-mcp.yml').read_text()
analysis_token = Path('/config/.local/share/weharbor/analysis/advanced/mcp.token')
assert stat.S_IMODE(analysis_token.stat().st_mode) == 0o600
assert stat.S_IMODE(analysis_token.parent.stat().st_mode) == 0o700
skill_request = json.dumps({'jsonrpc':'2.0','id':3,'method':'resources/read','params':{'uri':'wechat-analysis://skill'}}) + '\n'
skill_result = subprocess.run(['s6-setuidgid', 'abc', 'env',
    'WECHAT_ANALYSIS_MCP_TOKEN_FILE=/config/.local/share/weharbor/analysis/advanced/mcp.token',
    '/opt/weharbor/python/bin/python', '/opt/weharbor/analysis/scripts/advanced_mcp_stdio.py'],
    input=skill_request, capture_output=True, text=True, timeout=15, check=True)
assert 'automation-moments-sync' in json.loads(skill_result.stdout)['result']['contents'][0]['text']
assert 'wechat_create_task' in Path('/usr/share/weharbor/skills/weharbor-api/SKILL.md').read_text()
print('Harness analysis stdio bridge exposes 19 authenticated tools and the action/automation Skill')
uploads = list(Path('/config/.local/share/weharbor/uploads').glob('*/weharbor-smoke.bin'))
assert len(uploads) == 1
assert uploads[0].read_bytes() == b'WeHarbor private upload fixture\n' * 70000
assert stat.S_IMODE(uploads[0].stat().st_mode) == 0o400
assert stat.S_IMODE(uploads[0].parent.stat().st_mode) == 0o700
assert stat.S_IMODE(uploads[0].parent.parent.stat().st_mode) == 0o700
print('Uploaded bytes and private permissions verified')
assert len(tools) == 35
assert {'wechat_open_chat', 'wechat_desktop_status'} <= {t['name'] for t in tools}
print('Authenticated MCP exposes navigation and readiness alongside advanced operations')
request = urllib.request.Request('http://127.0.0.1:8766/desktop/status',
    headers={'Authorization':'Bearer ' + token})
with urllib.request.urlopen(request, timeout=30) as response:
    readiness = json.load(response)
assert readiness['state'] == 'blocked', 'A fresh logged-out profile cannot be ready'
assert readiness['code'] and readiness['recovery'] and isinstance(readiness['retryable'], bool)
print('Fresh-profile desktop readiness reports a structured blocker')
identity = subprocess.run(['s6-setuidgid', 'abc', 'sudo', '-n',
    '/usr/local/bin/weharbor-capture-key'], input=json.dumps(
        {'mode': 'session', 'account': 'synthetic'}),
    text=True, capture_output=True, check=True, timeout=20)
assert json.loads(identity.stdout) == {'verified': False, 'error': 'SESSION_IDENTITY_UNAVAILABLE'}
print('Fixed privileged identity helper rejects an account absent from the fresh desktop')
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
magpie_ver = subprocess.check_output(['magpie', 'version'], text=True).strip()
assert magpie_ver == 'magpie ' + lock['magpie']['version'], magpie_ver
subprocess.run(['magpie', 'healthcheck'], check=True)
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:3425/v1/models',
        headers={'Authorization': 'Bearer magpie'}), timeout=5) as response:
    assert json.load(response)['object'] == 'list'
assert 'http://127.0.0.1:3425/v1' in Path('/config/.local/share/weharbor/harness/profiles/web/cordis.patch.yml').read_text()
assert '    preference: zh' in Path('/config/.local/share/weharbor/harness/profiles/web/cordis.patch.yml').read_text()
assert Path('/usr/local/bin/dsh').stat().st_mode & 0o111
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
# Docker may allocate a different ephemeral host port when restarting.
export SMOKE_URL="http://$(docker port "$container" 3000/tcp | head -n 1)"
python3 - <<'PY'
import base64, http.cookiejar, json, os, time, urllib.error, urllib.request
url = os.environ['SMOKE_URL'] + '/assistant/'
headers = {'Authorization': 'Basic ' + base64.b64encode(
    ('weharbor:' + os.environ['PASSWORD']).encode()).decode()}
# A new browser must bootstrap against the restarted Harness, whose signing
# state persists in the profile. Never depend on the old process's launch token.
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
for attempt in range(90):
    try:
        with browser.open(urllib.request.Request(url, headers=headers), timeout=5) as response:
            page = response.read()
            assert b'crypto.randomUUID' in page and b'assets/' in page
        payload = {'type':'client-request', 'rpcId':'weharbor-restart',
                   'method':'settings/describe', 'payload':{'args':{}}}
        request = urllib.request.Request(url + 'api/settings/describe',
            data=json.dumps(payload).encode(), headers={**headers,
                'Content-Type':'application/json', 'Origin':os.environ['SMOKE_URL']})
        with browser.open(request, timeout=15) as response:
            assert json.load(response)['result']['ok'] is True
        break
    except (OSError, ValueError):
        time.sleep(1)
else:
    raise SystemExit('Harness browser bootstrap/RPC failed after restart')
print('Harness signed browser session and settings RPC passed after restart')
PY
printf '%s\n' 'WeHarbor fresh-profile smoke test passed, including restart'
