"""Optional remote access: Tailscale, Cloudflare Tunnel and frp.

Settings come from environment variables (which always win and are shown as
locked in the UI) and from a private JSON file edited in the web UI. Each
method runs under its own s6 longrun service as the abc user:

    python remote_access.py supervise tailscale|cloudflare|frp

The supervisor stays idle when the method is disabled, restarts its child
with backoff on failure (never crash-looping the container), redacts secrets
from every log line, and exits when its effective settings change so s6
restarts the service with the new configuration.
"""
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    tomllib = None

STATE = Path(os.environ.get('WEHARBOR_WORKSPACE_STATE', '/config/.local/share/weharbor/workspace'))
SETTINGS = Path(os.environ.get('WEHARBOR_REMOTE_SETTINGS', '/config/.config/weharbor/remote-access.json'))
FRP_RAW = Path(os.environ.get('WEHARBOR_FRP_CONFIG', '/config/frp/frpc.toml'))
RUNTIME = Path(os.environ.get('WEHARBOR_REMOTE_RUNTIME', str(STATE / 'remote')))
BIN = Path(os.environ.get('WEHARBOR_NETWORK_ROOT', '/opt/weharbor/network'))
TS_SOCKET = STATE / 'tailscale.sock'
TS_STATE = STATE / 'tailscale.state'
TS_PROXY = '127.0.0.1:1056'
MASK = '••••••••'
SERVICES = ('tailscale', 'cloudflare', 'frp')
LOG_LINES = 200
SECRET_KEYS = re.compile(r'(?i)(token|secret|password|passwd|authkey|auth_key|privatekey|private_key)')

# field -> (environment variable, kind, default)
FIELDS = {
    'tailscale': {
        'enabled': ('TAILSCALE_ENABLE', 'bool', False),
        'authkey': ('TAILSCALE_AUTHKEY', 'secret', ''),
        'hostname': ('TAILSCALE_HOSTNAME', 'hostname', 'weharbor'),
        'login_server': ('TAILSCALE_LOGIN_SERVER', 'url', ''),
        'serve': ('TAILSCALE_SERVE', 'bool', False),
        'extra_args': ('TAILSCALE_EXTRA_ARGS', 'args', ''),
    },
    'cloudflare': {
        'enabled': ('CLOUDFLARE_TUNNEL_ENABLE', 'bool', False),
        'token': ('CLOUDFLARE_TUNNEL_TOKEN', 'secret', ''),
    },
    'frp': {
        'enabled': ('FRP_ENABLE', 'bool', False),
        'mode': ('FRP_MODE', 'mode', 'simple'),
        'server_addr': ('FRP_SERVER_ADDR', 'host', ''),
        'server_port': ('FRP_SERVER_PORT', 'port', 7000),
        'token': ('FRP_TOKEN', 'secret', ''),
        'proxy_type': ('FRP_PROXY_TYPE', 'proxy', ''),
        'remote_port': ('FRP_REMOTE_PORT', 'port', 0),
        'custom_domain': ('FRP_CUSTOM_DOMAIN', 'host', ''),
        'proxy_name': ('FRP_PROXY_NAME', 'name', 'weharbor'),
        'tls': ('FRP_TLS', 'bool', True),
    },
}
# Setting this environment variable implies the method is enabled (and locked).
IMPLIES = {'tailscale': 'TAILSCALE_AUTHKEY', 'cloudflare': 'CLOUDFLARE_TUNNEL_TOKEN', 'frp': 'FRP_SERVER_ADDR'}
TRUE = {'1', 'true', 'yes', 'on'}
FALSE = {'0', 'false', 'no', 'off'}


def env(name):
    value = os.environ.get(name, '')
    return value.strip() if value.strip() else None


def coerce(kind, value):
    """Validate one setting; raises ValueError with a user-facing message."""
    if kind == 'bool':
        if isinstance(value, bool): return value
        text = str(value).strip().lower()
        if text in TRUE: return True
        if text in FALSE or text == '': return False
        raise ValueError('需要 true 或 false')
    if kind == 'port':
        if value in ('', None): return 0
        try: port = int(value)
        except (TypeError, ValueError): raise ValueError('端口必须是数字') from None
        if not 0 <= port <= 65535: raise ValueError('端口范围 1-65535')
        return port
    value = '' if value is None else str(value).strip()
    if kind == 'secret':
        if len(value) > 4096 or re.search(r'[\s"\'\\]', value): raise ValueError('密钥格式无效')
        return value
    if not value: return value
    patterns = {
        'hostname': r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',
        'host': r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\]|[0-9A-Fa-f:]+',
        'url': r'https?://[A-Za-z0-9.-]+(?::\d{1,5})?(?:/[A-Za-z0-9._~/-]*)?',
        'name': r'[A-Za-z0-9_.-]{1,64}',
        'mode': r'simple|raw',
        'proxy': r'tcp|http|https',
    }
    if kind == 'args':
        if len(value) > 1024: raise ValueError('参数过长')
        try: parts = shlex.split(value)
        except ValueError: raise ValueError('参数格式无效') from None
        for part in parts:
            if not part.startswith('--') or part.split('=')[0] in ('--auth-key', '--authkey', '--socket'):
                raise ValueError('仅支持 --flag=value 形式，且不能包含 --auth-key')
        return value
    if not re.fullmatch(patterns[kind], value): raise ValueError('格式无效')
    return value


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name('.' + path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream: stream.write(text)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_raw():
    try: return FRP_RAW.read_text()
    except OSError: return None


def effective(name, stored=None):
    """Merge environment over UI settings. Returns (values, locked fields, source)."""
    stored = (load_settings() if stored is None else stored).get(name) or {}
    values, locked = {}, []
    for field, (variable, kind, default) in FIELDS[name].items():
        raw = env(variable)
        if raw is not None:
            try: values[field] = coerce(kind, raw)
            except ValueError: values[field] = default
            locked.append(field)
        else:
            try: values[field] = coerce(kind, stored.get(field, default))
            except ValueError: values[field] = default
    implied = env(IMPLIES[name])
    if 'enabled' not in locked and implied is not None:
        values['enabled'] = True
        locked.append('enabled')
    if name == 'frp' and not stored and 'server_addr' not in locked and read_raw() is not None:
        # A mounted /config/frp/frpc.toml enables frp until the UI says otherwise.
        if 'mode' not in locked: values['mode'] = 'raw'
        if 'enabled' not in locked: values['enabled'] = True
    if name == 'frp' and 'server_addr' in locked and 'mode' not in locked:
        values['mode'] = 'simple'; locked.append('mode')
    source = 'env' if 'enabled' in locked else 'ui' if stored else 'default'
    return values, sorted(locked), source


def secrets_of(name, values):
    found = [values[f] for f, spec in FIELDS[name].items() if spec[1] == 'secret' and values.get(f)]
    if name == 'frp' and values.get('mode') == 'raw':
        for line in (read_raw() or '').splitlines():
            key, _, rest = line.partition('=')
            if rest and SECRET_KEYS.search(key):
                value = rest.strip().strip('"\'')
                if len(value) >= 4: found.append(value)
    return found


ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
GENERIC = [re.compile(p) for p in (r'tskey-[A-Za-z0-9_-]+', r'eyJ[A-Za-z0-9_+/=-]{20,}',
    r'(?i)((?:token|authkey|auth-key|secret|password)["\']?\s*[=:]\s*["\']?)[^\s"\',]+')]


def redact(text, secrets=()):
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret: text = text.replace(secret, '[REDACTED]')
    text = GENERIC[0].sub('[REDACTED]', text)
    text = GENERIC[1].sub('[REDACTED]', text)
    return GENERIC[2].sub(lambda m: m.group(1) + '[REDACTED]', text)


def mask_raw(text):
    """Show frpc.toml with secret values replaced by MASK."""
    def line(value):
        key, sep, rest = value.partition('=')
        if sep and SECRET_KEYS.search(key) and rest.strip():
            return key + '= "' + MASK + '"'
        return value
    return '\n'.join(line(v) for v in text.splitlines()) + ('\n' if text.endswith('\n') else '')


def unmask_raw(new, old):
    previous = {}
    for value in (old or '').splitlines():
        key, sep, rest = value.partition('=')
        if sep: previous[key.strip()] = rest
    out = []
    for value in new.splitlines():
        key, sep, rest = value.partition('=')
        if sep and MASK in rest:
            if key.strip() not in previous: raise ValueError(key.strip() + ' 需要填写真实值')
            value = key + '=' + previous[key.strip()]
        out.append(value)
    return '\n'.join(out) + '\n'


def frp_config(values):
    """Render frpc.toml for the simple form; returns text."""
    if not values['server_addr']: raise ValueError('未设置 frp 服务器地址')
    kind = values['proxy_type'] or ('tcp' if values['remote_port'] else 'https')
    lines = ['# Generated by WeHarbor from FRP_* settings; do not edit.',
             'serverAddr = ' + json.dumps(values['server_addr']),
             'serverPort = %d' % (values['server_port'] or 7000),
             'loginFailExit = false',
             'transport.tls.enable = ' + ('true' if values['tls'] else 'false'),
             'log.to = "console"', 'log.level = "info"', 'log.disablePrintColor = true']
    if values['token']:
        lines += ['auth.method = "token"', 'auth.token = ' + json.dumps(values['token'])]
    lines += ['', '[[proxies]]', 'name = ' + json.dumps(values['proxy_name'] or 'weharbor'),
              'type = ' + json.dumps(kind), 'localIP = "127.0.0.1"',
              'localPort = %d' % (3000 if kind == 'http' else 3001)]
    if kind == 'tcp':
        if not values['remote_port']: raise ValueError('tcp 模式需要远程端口 FRP_REMOTE_PORT')
        lines.append('remotePort = %d' % values['remote_port'])
    else:
        if not values['custom_domain']: raise ValueError(kind + ' 模式需要自定义域名 FRP_CUSTOM_DOMAIN')
        lines.append('customDomains = [' + json.dumps(values['custom_domain']) + ']')
    return '\n'.join(lines) + '\n'


def validate(name, values):
    if name == 'cloudflare' and not values['token']:
        raise ValueError('未设置 Cloudflare Tunnel Token')
    if name == 'cloudflare' and not re.fullmatch(r'[A-Za-z0-9_+=/.-]{30,4096}', values['token']):
        raise ValueError('Cloudflare Tunnel Token 格式无效')
    if name == 'frp':
        if values['mode'] == 'raw':
            text = read_raw()
            if text is None: raise ValueError('未找到 ' + str(FRP_RAW))
            if tomllib:
                try: tomllib.loads(text)
                except tomllib.TOMLDecodeError as error: raise ValueError('frpc.toml 语法错误：' + str(error)) from None
        else:
            frp_config(values)


# ---------------------------------------------------------------- UI / API

def public(name):
    values, locked, source = effective(name)
    out = {}
    for field, (variable, kind, _) in FIELDS[name].items():
        value = values[field]
        if kind == 'secret': value = MASK if value else ''
        out[field] = value
    env_names = {field: spec[0] for field, spec in FIELDS[name].items()}
    result = {'settings': out, 'locked': locked, 'env': env_names, 'source': source,
              'status': read_status(name), 'log': read_log(name)}
    if name == 'frp':
        raw = read_raw()
        result['raw'] = mask_raw(raw) if raw is not None else ''
        result['raw_path'] = str(FRP_RAW)
        kind = values['proxy_type'] or ('tcp' if values['remote_port'] else 'https')
        if values['mode'] == 'simple' and values['server_addr']:
            if kind == 'tcp' and values['remote_port']:
                result['url'] = 'https://%s:%d' % (values['server_addr'], values['remote_port'])
            elif values['custom_domain']:
                result['url'] = ('http://' if kind == 'http' else 'https://') + values['custom_domain']
    return result


def update(name, body):
    """Save UI settings for one method. Locked (env) fields are ignored."""
    if name not in SERVICES: raise ValueError('未知的远程访问方式')
    if not isinstance(body, dict): raise ValueError('需要 JSON 对象')
    data = load_settings()
    current = dict(data.get(name) or {})
    _, locked, _ = effective(name, data)
    for field, (variable, kind, default) in FIELDS[name].items():
        if field not in body or field in locked: continue
        value = body[field]
        if kind == 'secret' and value == MASK: continue
        try: current[field] = coerce(kind, value)
        except ValueError as error: raise ValueError('%s：%s' % (field, error)) from None
    if name == 'frp' and isinstance(body.get('raw'), str) and 'mode' not in locked:
        text = body['raw']
        if len(text) > 65536: raise ValueError('frpc.toml 过大')
        if text.strip():
            text = unmask_raw(text, read_raw())
            if tomllib:
                try: tomllib.loads(text)
                except tomllib.TOMLDecodeError as error: raise ValueError('frpc.toml 语法错误：' + str(error)) from None
            private_write(FRP_RAW, text)
    data[name] = current
    private_write(SETTINGS, json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    return public(name)


def read_status(name):
    try: return json.loads((RUNTIME / (name + '.json')).read_text())
    except (OSError, ValueError): return {'state': 'unknown', 'message': '服务状态未知'}


def read_log(name, lines=40):
    try: return (RUNTIME / (name + '.log')).read_text(errors='replace').splitlines()[-lines:]
    except OSError: return []


# ---------------------------------------------------------------- supervisor

class Supervisor:
    def __init__(self, name):
        self.name = name
        self.values, self.locked, self.source = effective(name)
        self.digest = self.fingerprint()
        self.secrets = secrets_of(name, self.values)
        self.children = []
        self.lines = deque(maxlen=LOG_LINES)
        self.lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.stopping = False
        self.status = {}
        RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)

    def fingerprint(self):
        values, locked, _ = effective(self.name)
        extra = read_raw() if self.name == 'frp' and values.get('mode') == 'raw' else ''
        return hashlib.sha256(json.dumps([values, locked, extra], sort_keys=True).encode()).hexdigest()

    def log(self, text):
        text = ANSI.sub('', text)
        line = time.strftime('%H:%M:%S ') + redact(text.rstrip(), self.secrets)
        print('[remote-access:%s] %s' % (self.name, line[9:]), flush=True)
        with self.lock:
            self.lines.append(line)
            path = RUNTIME / (self.name + '.log')
            private_write(path, '\n'.join(self.lines) + '\n')
        self.watch(text)

    def set(self, state, message, **extra):
        with self.status_lock:
            self.status = {'state': state, 'message': message, 'source': self.source,
                           'updated': int(time.time()), **extra}
            private_write(RUNTIME / (self.name + '.json'), json.dumps(self.status, ensure_ascii=False))

    def watch(self, text):
        """Promote the status when a child reports a successful connection."""
        markers = {'cloudflare': 'Registered tunnel connection', 'frp': 'start proxy success'}
        if markers.get(self.name) and markers[self.name] in text and self.status.get('state') != 'connected':
            self.set('connected', '已连接')
        text = redact(ANSI.sub('', text).strip(), self.secrets)
        if self.name == 'tailscale' and text.startswith('up: ') and ('error' in text or 'invalid' in text):
            self.up_error = text[4:][-300:]
        if self.name == 'frp' and ('login to server failed' in text or 'connect to server error' in text):
            self.set('error', '连接 frps 失败，正在重试：' + text[-240:])
        if self.name == 'frp' and 'start error' in text:
            hint = '（代理名已被占用，请修改 FRP_PROXY_NAME）' if 'already exists' in text else ''
            self.set('error', '代理启动失败' + hint + '：' + text[-200:])
        if self.name == 'cloudflare' and ' ERR ' in text and self.status.get('state') != 'connected':
            self.set('running', '尚未连上 Cloudflare，正在重试：' + text[-240:])

    def spawn(self, args, env_extra=None, label=None):
        environment = {k: v for k, v in os.environ.items() if k not in
                       {spec[0] for fields in FIELDS.values() for spec in fields.values()}}
        environment.update(env_extra or {})
        child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 env=environment, text=True, errors='replace', start_new_session=True)
        def pump():
            for text in child.stdout:
                self.log(((label + ': ') if label else '') + text)
        threading.Thread(target=pump, daemon=True).start()
        self.children.append(child)
        return child

    def stop_children(self):
        for child in reversed(self.children):
            if child.poll() is None:
                try: os.killpg(child.pid, signal.SIGTERM)
                except OSError: pass
        deadline = time.time() + 8
        for child in self.children:
            try: child.wait(max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid, signal.SIGKILL)
                except OSError: pass
        self.children = []

    def terminate(self, *_):
        self.stopping = True

    def changed(self):
        return self.fingerprint() != self.digest

    def idle(self, seconds=None):
        """Sleep until settings change (True), stop requested or timeout (False)."""
        end = time.time() + seconds if seconds else None
        while not self.stopping and (end is None or time.time() < end):
            if self.changed(): return True
            time.sleep(2)
        return False

    def run(self):
        signal.signal(signal.SIGTERM, self.terminate)
        signal.signal(signal.SIGINT, self.terminate)
        if not self.values['enabled']:
            self.set('disabled', '未启用')
            self.idle()
            return 0
        try:
            validate(self.name, self.values)
        except ValueError as error:
            self.set('error', str(error))
            self.log('配置无效：' + str(error))
            self.idle()
            return 0
        delay = 5
        while not self.stopping:
            started = time.time()
            self.set('starting', '正在启动')
            try:
                main = getattr(self, 'start_' + self.name)()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                main = None
                self.log('启动失败：' + str(error))
                self.set('error', redact(str(error), self.secrets))
            while main is not None and main.poll() is None and not self.stopping and not self.changed():
                self.tick()
                time.sleep(2)
            if self.stopping or self.changed(): break
            code = main.returncode if main is not None else None
            self.stop_children()
            if time.time() - started > 120: delay = 5
            message = '进程退出（代码 %s），%d 秒后重试' % (code, delay)
            self.log(message)
            self.set('error', message, exit_code=code, retry_in=delay)
            if self.idle(delay): break
            delay = min(delay * 2, 300)
        self.stop_children()
        if not self.stopping: self.log('配置已更改，重新启动服务')
        return 0

    def tick(self):
        if self.name == 'tailscale': self.tailscale_tick()

    # -- Cloudflare Tunnel
    def start_cloudflare(self):
        self.log('启动 cloudflared tunnel run（Token 通过环境变量传入，不会写入日志）')
        child = self.spawn([str(BIN / 'cloudflared'), 'tunnel', '--no-autoupdate', 'run'],
                           {'TUNNEL_TOKEN': self.values['token']})
        self.set('running', '进程运行中，等待 Cloudflare 注册连接')
        return child

    # -- frp
    def start_frp(self):
        if self.values['mode'] == 'raw':
            path = FRP_RAW
        else:
            path = RUNTIME / 'frpc.toml'
            private_write(path, frp_config(self.values))
        check = subprocess.run([str(BIN / 'frpc'), 'verify', '-c', str(path)], capture_output=True, text=True, timeout=20)
        if check.returncode != 0:
            raise ValueError('frpc.toml 校验失败：' + redact((check.stdout + check.stderr).strip(), self.secrets)[-400:])
        self.log('启动 frpc（%s）' % ('自定义 frpc.toml' if self.values['mode'] == 'raw' else '表单配置'))
        child = self.spawn([str(BIN / 'frpc'), '-c', str(path)])
        self.set('running', '进程运行中，等待连接 frps')
        return child

    # -- Tailscale (userspace networking: no TUN device or NET_ADMIN needed)
    def start_tailscale(self):
        TS_SOCKET.unlink(missing_ok=True)
        daemon = self.spawn([str(BIN / 'tailscaled'), '--tun=userspace-networking', '--state=' + str(TS_STATE),
                             '--socket=' + str(TS_SOCKET), '--outbound-http-proxy-listen=' + TS_PROXY], label='tailscaled')
        for _ in range(100):
            if TS_SOCKET.exists() or daemon.poll() is not None: break
            time.sleep(.1)
        if daemon.poll() is not None: return daemon
        args = [str(BIN / 'tailscale'), '--socket=' + str(TS_SOCKET), 'up', '--reset', '--accept-dns=false',
                '--hostname=' + (self.values['hostname'] or 'weharbor')]
        if self.values['login_server']: args.append('--login-server=' + self.values['login_server'])
        key = RUNTIME / 'tailscale.authkey'
        if self.values['authkey']:
            private_write(key, self.values['authkey'])
            args.append('--auth-key=file:' + str(key))
        args += shlex.split(self.values['extra_args'] or '')
        self.up = self.spawn(args, label='up')
        self.serve_applied = False
        self.set('starting', '正在登录 tailnet' if self.values['authkey'] else '等待交互式登录（见登录链接）')
        return daemon

    def tailscale_tick(self):
        up = getattr(self, 'up', None)
        if up is not None and up.poll() is not None:
            (RUNTIME / 'tailscale.authkey').unlink(missing_ok=True)
            if up.returncode != 0 and self.status.get('state') != 'error':
                self.set('error', 'tailscale up 失败：' + (getattr(self, 'up_error', None) or '代码 %s，请查看日志' % up.returncode))
            self.up = None
        try:
            out = subprocess.run([str(BIN / 'tailscale'), '--socket=' + str(TS_SOCKET), 'status', '--json'],
                                 capture_output=True, text=True, timeout=10)
            data = json.loads(out.stdout) if out.returncode == 0 or out.stdout.startswith('{') else {}
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        state = data.get('BackendState')
        if state == 'Running':
            dns = ((data.get('Self') or {}).get('DNSName') or '').rstrip('.')
            if not self.serve_applied:
                self.apply_serve()
            if self.status.get('state') != 'connected':
                self.set('connected', '已加入 tailnet', ips=data.get('TailscaleIPs') or [], dns=dns,
                         url=('https://' + dns) if self.values['serve'] and dns else None)
        elif state == 'NeedsLogin' and data.get('AuthURL') and self.status.get('state') != 'needs_login':
            self.set('needs_login', '需要在浏览器完成 Tailscale 登录', auth_url=data.get('AuthURL'))

    def apply_serve(self):
        self.serve_applied = True
        base = [str(BIN / 'tailscale'), '--socket=' + str(TS_SOCKET), 'serve']
        marker = RUNTIME / 'tailscale.serve'
        if self.values['serve']:
            result = subprocess.run(base + ['--bg', '--https=443', 'https+insecure://127.0.0.1:3001'],
                                    capture_output=True, text=True, timeout=30)
            self.log('tailscale serve: ' + ((result.stdout + result.stderr).strip() or 'ok'))
            if result.returncode == 0: marker.write_text('1')
        elif marker.exists():
            subprocess.run(base + ['reset'], capture_output=True, timeout=30)
            marker.unlink(missing_ok=True)
            self.log('已关闭 tailscale serve')


def migrate_legacy():
    """Fold the pre-service network.json / cloudflare.token into UI settings once."""
    if SETTINGS.exists(): return
    legacy = {}
    try: legacy = json.loads((STATE / 'network.json').read_text())
    except (OSError, ValueError): pass
    data = {}
    if legacy.get('tailscale'): data['tailscale'] = {'enabled': True}
    try:
        token = (STATE / 'cloudflare.token').read_text().strip()
        if legacy.get('cloudflare') and token: data['cloudflare'] = {'enabled': True, 'token': token}
    except OSError: pass
    if data: private_write(SETTINGS, json.dumps(data, indent=2) + '\n')


def main(argv):
    if len(argv) == 3 and argv[1] == 'supervise' and argv[2] in SERVICES:
        migrate_legacy()
        return Supervisor(argv[2]).run()
    print('usage: remote_access.py supervise ' + '|'.join(SERVICES), file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
