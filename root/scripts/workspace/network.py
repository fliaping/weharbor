"""Optional userspace Tailscale and named Cloudflare Tunnel connectors."""
import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from reader import STATE, atomic_json

ROOT = Path(os.environ.get('WEHARBOR_NETWORK_ROOT', '/opt/weharbor/network'))
SOCKET = STATE / 'tailscale.sock'
TS = str(ROOT / 'tailscale')
TSD = str(ROOT / 'tailscaled')
CF = str(ROOT / 'cloudflared')

class Network:
    def __init__(self):
        self.children = {}
        self.logs = []
        self.config_path = STATE / 'network.json'

    def config(self):
        try: return json.loads(self.config_path.read_text())
        except (OSError, ValueError): return {}

    async def start(self):
        config = self.config()
        # Optional connector failures must not prevent local messages/UI booting.
        try:
            if config.get('tailscale'): await self.ensure_tailscale()
            if config.get('cloudflare') and (STATE / 'cloudflare.token').is_file():
                await self.spawn('cloudflare', [CF, 'tunnel', '--no-autoupdate', 'run', '--token-file', str(STATE / 'cloudflare.token')])
        except (OSError, ValueError):
            pass

    async def spawn(self, name, args):
        if name in self.children and self.children[name].returncode is None: return
        if not Path(args[0]).is_file(): raise ValueError(name + ' runtime is not installed')
        log = open(STATE / (name + '.log'), 'ab', buffering=0)
        os.chmod(log.name, 0o600)
        self.logs.append(log)
        self.children[name] = await asyncio.create_subprocess_exec(*args, stdout=log, stderr=log)

    async def ensure_tailscale(self):
        await self.spawn('tailscale', [TSD, '--tun=userspace-networking', '--state='+str(STATE/'tailscale.state'),
            '--socket='+str(SOCKET), '--outbound-http-proxy-listen=127.0.0.1:1056'])
        for _ in range(30):
            if SOCKET.exists(): return
            await asyncio.sleep(.1)
        raise ValueError('Tailscale daemon did not start')

    async def command(self, *args):
        p = await asyncio.create_subprocess_exec(TS, '--socket='+str(SOCKET), *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(p.communicate(), timeout=15)
        except asyncio.TimeoutError:
            p.kill(); await p.wait(); raise ValueError('Tailscale command timed out')
        return p.returncode, out.decode(errors='replace'), err.decode(errors='replace')

    async def login(self):
        await self.ensure_tailscale()
        config = self.config(); config['tailscale'] = True; atomic_json(self.config_path, config)
        code, out, err = await self.command('up', '--accept-dns=false', '--hostname=weharbor', '--timeout=3s')
        urls = re.findall(r'https://login\.tailscale\.com/[A-Za-z0-9/_-]+', out + err)
        return {'login_url': urls[0] if urls else None, 'connected': code == 0}

    async def status(self):
        ts = {'installed': Path(TS).is_file(), 'running': False, 'state': 'Stopped', 'ips': []}
        if SOCKET.exists() and ts['installed']:
            try:
                code, out, _ = await self.command('status', '--json')
                if code == 0:
                    data = json.loads(out)
                    ts.update(running=True, state=data.get('BackendState'), ips=data.get('TailscaleIPs', []))
            except (OSError, ValueError): pass
        cf = self.children.get('cloudflare')
        return {'tailscale': ts, 'cloudflare': {'installed': Path(CF).is_file(),
            'configured': (STATE/'cloudflare.token').exists(), 'running': cf is not None and cf.returncode is None}}

    async def cloudflare(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_+=/.-]{30,4096}', token):
            raise ValueError('Invalid tunnel token')
        path = STATE / 'cloudflare.token'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(token)
        await self.stop('cloudflare')
        config = self.config(); config['cloudflare'] = True; atomic_json(self.config_path, config)
        await self.start()
        return await self.status()

    async def stop(self, name):
        child = self.children.pop(name, None)
        if child and child.returncode is None:
            child.terminate()
            try: await asyncio.wait_for(child.wait(), 5)
            except asyncio.TimeoutError: child.kill(); await child.wait()

    async def close(self):
        for name in list(self.children): await self.stop(name)
        for log in self.logs: log.close()
