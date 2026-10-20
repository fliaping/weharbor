"""Select an authenticated, reachable message service without exposing credentials."""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

STATE = Path(os.environ.get('WEHARBOR_WORKSPACE_STATE', '/config/.local/share/weharbor/workspace'))
CONFIG = Path(os.environ.get('WEHARBOR_CONNECTIONS_FILE', '/config/.config/weharbor/connections.json'))
LOCAL = os.environ.get('WEHARBOR_ANALYSIS_URL', 'http://127.0.0.1:10392').rstrip('/')

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {'connections': []}

def save_config(value):
    if not isinstance(value, dict):
        raise ValueError('Expected a configuration object')
    connections = value.get('connections', [])
    if not isinstance(connections, list) or len(connections) > 8:
        raise ValueError('At most eight connections are supported')
    previous = {c.get('id'): c for c in load_config().get('connections', [])}
    seen = set()
    for c in connections:
        if not isinstance(c, dict) or set(c) - {'id','kind','url','token','enabled','has_token'}:
            raise ValueError('Invalid connection fields')
        if not isinstance(c.get('id'), str) or not 1 <= len(c['id']) <= 128 or c['id'] == 'local' or c['id'] in seen:
            raise ValueError('Use unique connection IDs')
        seen.add(c['id'])
        if not isinstance(c.get('url'), str) or not isinstance(c.get('token', ''), str) or len(c.get('token', '')) > 4096 or not isinstance(c.get('enabled', True), bool):
            raise ValueError('Invalid connection value')
        c.pop('has_token', None)
        url = urlsplit(c.get('url', ''))
        if c.get('kind') not in ['direct', 'tailscale', 'cloudflare']:
            raise ValueError('Unknown transport')
        if url.scheme not in ['https', 'http'] or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use a service base URL without credentials, query or fragment')
        if c.get('kind') == 'cloudflare' and url.scheme != 'https':
            raise ValueError('Cloudflare connections require HTTPS')
        if not c.get('token'):
            c['token'] = previous.get(c.get('id'), {}).get('token', '')
        c['url'] = c['url'].rstrip('/')
    atomic_json(CONFIG, {'connections': connections})

def public_config():
    return {'connections': [{k: v for k, v in c.items() if k != 'token'} |
                            {'has_token': bool(c.get('token'))} for c in load_config().get('connections', [])]}

class Reader:
    def __init__(self):
        self.selected = None
        self.checked_at = 0
        self.probes = []

    async def probe(self):
        candidates = [{'id': 'local', 'kind': 'local', 'url': LOCAL, 'token': ''}]
        candidates += [c for c in load_config().get('connections', []) if c.get('enabled', True)]
        self.probes = []
        self.selected = None
        for c in candidates:
            proxy = 'http://127.0.0.1:1056' if c['kind'] == 'tailscale' else None
            async with httpx.AsyncClient(timeout=4, proxy=proxy, follow_redirects=False, trust_env=False) as client:
                path = '/api/health' if c['kind'] == 'local' else '/workspace/data/health'
                headers = {'Authorization': 'Bearer ' + c['token']} if c.get('token') else {}
                started = time.monotonic()
                try:
                    r = await client.get(c['url'] + path, headers=headers)
                    ok = r.is_success and isinstance(r.json(), dict)
                    if ok:
                        account_path = '/api/chat/accounts' if c['kind'] == 'local' else '/workspace/data/chat/accounts'
                        accounts = await client.get(c['url'] + account_path, headers=headers)
                        payload = accounts.json()
                        values = payload if isinstance(payload, list) else payload.get('accounts', []) if isinstance(payload, dict) else []
                        ok = accounts.is_success and bool(values)
                except (httpx.HTTPError, ValueError):
                    ok = False
                self.probes.append({'id': c['id'], 'kind': c['kind'], 'reachable': ok,
                                    'latency_ms': round((time.monotonic() - started) * 1000)})
                if ok and self.selected is None:
                    self.selected = c
        self.checked_at = time.monotonic()
        return {'selected': self.selected['id'] if self.selected else None, 'probes': self.probes}

    async def get(self, path, params=None, retry=True):
        if not self.selected or time.monotonic() - self.checked_at > 30:
            await self.probe()
        if not self.selected:
            raise RuntimeError('No reachable message service. Check Connections.')
        c = self.selected
        prefix = '/api/' if c['kind'] == 'local' else '/workspace/data/'
        headers = {'Authorization': 'Bearer ' + c['token']} if c.get('token') else {}
        proxy = 'http://127.0.0.1:1056' if c['kind'] == 'tailscale' else None
        async with httpx.AsyncClient(timeout=60, proxy=proxy, trust_env=False) as client:
            try:
                r = await client.get(c['url'] + prefix + path, params=params, headers=headers)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:
                failed = c['id']
                self.selected = None
                if retry:
                    await self.probe()
                    # A health check may succeed while a real request fails.
                    alternatives = [p['id'] for p in self.probes if p['reachable'] and p['id'] != failed]
                    if alternatives:
                        candidates = [{'id':'local','kind':'local','url':LOCAL,'token':''}] + load_config().get('connections', [])
                        self.selected = next(x for x in candidates if x['id'] == alternatives[0])
                        return await self.get(path, params, retry=False)
                raise RuntimeError('Message service request failed; retry after checking connectivity') from exc

    async def get_local(self, path, params=None):
        # Desktop identity and receipts must come from this machine even when
        # concurrent read-only requests select another reachable transport.
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            try:
                r = await client.get(LOCAL + '/api/' + path, params=params)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError('Local desktop message service is unavailable') from exc

    async def sync(self):
        # Only local source refreshes are allowed; credentials never cross to another transport.
        async with httpx.AsyncClient(timeout=600, trust_env=False) as client:
            try:
                r = await client.post(LOCAL + '/api/linux/sync', headers={'X-WeHarbor-Action': 'sync'})
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError('Local desktop message synchronization is unavailable') from exc
