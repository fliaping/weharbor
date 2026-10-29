"""Browser session and origin contract at the mounted Harness boundary."""
import http.client
import http.cookiejar
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_JS = '''export const channel = "/api";
export const socketPath = "/api/remote.mux";
export const resolveSocket = base => new URL(socketPath.slice(1), base).href;
export const callPath = endpoint => `${channel}/${endpoint}`.slice(1);
'''
FAKE_DSH = r'''
import http from 'node:http';
const args = process.argv.slice(2);
if (args[0] !== '--profile' || args[1] !== 'web' ||
    args.indexOf('--patch') > args.indexOf('--no-open') && args.includes('--no-open')) process.exit(8);
const port = Number(args[args.lastIndexOf('--port') + 1]);
const token = 'test_launch_token_never_log';
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/' && url.searchParams.get('token') === token) {
    res.writeHead(303, {'set-cookie': 'dsh-auth-test=signed; Path=/; HttpOnly; SameSite=Strict', location: './'});
    res.end(); return;
  }
  if (!req.headers.cookie?.includes('dsh-auth-test=signed')) { res.writeHead(401); res.end(); return; }
  if (url.pathname === '/assets/transport.js') {
    res.setHeader('content-type', 'text/javascript');
    res.end(process.env.TEST_TRANSPORT_JS); return;
  }
  if (url.pathname === '/api/message') {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({text: '/api/private user content'})); return;
  }
  res.setHeader('content-type', 'text/html');
  res.end('<html><head></head><script src="/assets/app.js"></script></html>');
});
server.on('upgrade', (req, socket) => {
  const allowed = req.headers.cookie?.includes('dsh-auth-test=signed') &&
    req.headers.origin === `http://127.0.0.1:${port}`;
  socket.end(`HTTP/1.1 ${allowed ? '101 Switching Protocols' : '401 Unauthorized'}\r\nConnection: close\r\n\r\n`);
});
server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`dsh web: http://127.0.0.1:${port}/?tok`);
  setTimeout(() => process.stdout.write(`en=${token}\n`), 5);
});
'''

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

@unittest.skipUnless(shutil.which('node'), 'Node runtime required')
class HarnessProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        directory = Path(cls.temp.name)
        fake = directory / 'dsh.mjs'
        fake.write_text(FAKE_DSH)
        cls.logfile = directory / 'startup.log'
        cls.log = cls.logfile.open('w')
        cls.port, upstream = free_port(), free_port()
        cls.origin = f'http://127.0.0.1:{cls.port}'
        cls.base = cls.origin + '/assistant/'
        cls.process = subprocess.Popen(
            ['node', str(ROOT / 'root/scripts/workspace/harness-proxy.mjs'),
             '--port', str(cls.port), '--patch', str(directory / 'patch.yml')],
            env=dict(os.environ, DSH_BIN=str(fake), DSH_WORKSPACE=str(directory),
                     TEST_TRANSPORT_JS=TRANSPORT_JS,
                     DSH_WEB_PROXY_PREFIX='/assistant', DSH_WEB_UPSTREAM_PORT=str(upstream)),
            stdout=cls.log, stderr=cls.log, start_new_session=True)
        cls.jar = http.cookiejar.CookieJar()
        cls.browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cls.jar))
        for _ in range(100):
            try:
                with cls.browser.open(cls.base, timeout=1) as response:
                    if response.status == 200:
                        cls.html = response.read().decode()
                        break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.05)
        else:
            cls.tearDownClass()
            raise AssertionError('Harness proxy did not establish a browser session')

    @classmethod
    def tearDownClass(cls):
        os.killpg(cls.process.pid, signal.SIGTERM)
        cls.process.wait(timeout=10)
        cls.log.close()
        cls.temp.cleanup()

    def test_index_bootstraps_scoped_cookie_and_mounted_assets(self):
        self.assertIn('src="/assistant/assets/app.js"', self.html)
        # user:pass@host URLs break relative fetch(); the head script reloads without them.
        self.assertIn('if(u.username||u.password)', self.html[:self.html.index('/assistant/assets/app.js')])
        cookie = next(iter(self.jar))
        self.assertEqual(cookie.path, '/assistant/')
        self.assertTrue(cookie.has_nonstandard_attr('HttpOnly'))
        self.assertNotIn('test_launch_token_never_log', self.logfile.read_text())

    def test_api_requires_cookie_and_preserves_message_content(self):
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(self.base + 'api/message')
        self.assertEqual(failure.exception.code, 401)
        with self.browser.open(self.base + 'api/message') as response:
            self.assertEqual(response.read(), b'{"text":"/api/private user content"}')

    def test_native_transport_keeps_logical_channel_and_resolves_prefix_once(self):
        with self.browser.open(self.base + 'assets/transport.js') as response:
            source = response.read().decode()
        self.assertEqual(source, TRANSPORT_JS)
        # Exercise the DSH browser transport's channel and base-URI contract.
        script = source.replace('export ', '') + f'''
import assert from 'node:assert/strict';
assert.match(channel, /^\\/[A-Za-z0-9._~-]+$/);
assert.equal(resolveSocket({self.base!r}), {self.base + 'api/remote.mux'!r});
assert.equal(new URL(callPath('settings/describe'), {self.base!r}).href,
             {self.base + 'api/settings/describe'!r});
'''
        subprocess.run(['node', '--input-type=module', '-e', script], check=True,
                       capture_output=True, text=True, timeout=5)

    def test_cross_origin_and_cross_site_cannot_bootstrap(self):
        for headers in [{'Origin': 'https://evil.test'}, {'Sec-Fetch-Site': 'cross-site'}]:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(urllib.request.Request(self.base, headers=headers))
            self.assertEqual(failure.exception.code, 403)

    def test_websocket_preserves_auth_and_validates_original_origin(self):
        for cookie, origin, expected in [('', self.origin, 401),
                                       ('dsh-auth-test=signed', self.origin, 101),
                                       ('dsh-auth-test=signed', 'https://evil.test', 403)]:
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
            connection.request('GET', '/assistant/api/socket', headers={
                'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Origin': origin, 'Cookie': cookie})
            self.assertEqual(connection.getresponse().status, expected)
            connection.close()
