"""Workspace view of the optional remote-access services.

The connectors themselves run as s6 services (svc-tailscale, svc-cloudflared,
svc-frpc) supervised by remote_access.py. This module only reads their state
and writes UI settings; saving settings makes the matching service restart.
"""
import asyncio
import json
import os
from pathlib import Path
import remote_access
from remote_access import TS_SOCKET as SOCKET

ROOT = Path(os.environ.get('WEHARBOR_NETWORK_ROOT', '/opt/weharbor/network'))
TS = str(ROOT / 'tailscale')
CF = str(ROOT / 'cloudflared')
FRPC = str(ROOT / 'frpc')

class Network:
    async def start(self):
        try: remote_access.migrate_legacy()
        except OSError: pass

    async def command(self, *args):
        p = await asyncio.create_subprocess_exec(TS, '--socket='+str(SOCKET), *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(p.communicate(), timeout=15)
        except asyncio.TimeoutError:
            p.kill(); await p.wait(); raise ValueError('Tailscale command timed out')
        return p.returncode, out.decode(errors='replace'), err.decode(errors='replace')

    async def tailscale_status(self):
        ts = {'installed': Path(TS).is_file(), 'running': False, 'state': 'Stopped', 'ips': []}
        if SOCKET.exists() and ts['installed']:
            try:
                code, out, _ = await self.command('status', '--json')
                if out.lstrip().startswith('{'):
                    data = json.loads(out)
                    dns = ((data.get('Self') or {}).get('DNSName') or '').rstrip('.')
                    ts.update(running=True, state=data.get('BackendState'), ips=data.get('TailscaleIPs') or [],
                              auth_url=data.get('AuthURL') or None, dns=dns or None)
            except (OSError, ValueError): pass
        return ts

    async def login(self):
        """Enable Tailscale from the UI and return its interactive login URL."""
        _, locked, _ = remote_access.effective('tailscale')
        if 'enabled' not in locked:
            remote_access.update('tailscale', {'enabled': True})
        for _ in range(40):
            ts = await self.tailscale_status()
            if ts['state'] == 'Running': return {'login_url': None, 'connected': True}
            if ts.get('auth_url'): return {'login_url': ts['auth_url'], 'connected': False}
            await asyncio.sleep(.5)
        return {'login_url': None, 'connected': False}

    async def status(self):
        cf = remote_access.read_status('cloudflare')
        frp = remote_access.read_status('frp')
        cf_values, _, _ = remote_access.effective('cloudflare')
        return {'tailscale': await self.tailscale_status(),
                'cloudflare': {'installed': Path(CF).is_file(), 'configured': bool(cf_values['token']),
                               'running': cf.get('state') in ('running', 'connected'), 'state': cf.get('state')},
                'frp': {'installed': Path(FRPC).is_file(), 'running': frp.get('state') in ('running', 'connected'),
                        'state': frp.get('state')}}

    async def remote(self):
        result = {}
        ts = await self.tailscale_status()
        for name in remote_access.SERVICES:
            result[name] = remote_access.public(name)
        result['tailscale']['live'] = ts
        return result

    async def update(self, name, body):
        remote_access.update(name, body)
        return (await self.remote())[name]

    async def cloudflare(self, token):
        remote_access.update('cloudflare', {'enabled': True, 'token': token})
        values, _, _ = remote_access.effective('cloudflare')
        remote_access.validate('cloudflare', values)
        return await self.status()

    async def close(self):
        pass
