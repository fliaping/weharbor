"""Browser session, subpath shim and origin contract at the mounted Magpie boundary."""
import http.cookiejar
import json
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
FAKE_MAGPIE = r'''#!/usr/bin/env node
import http from 'node:http';
const args = process.argv.slice(2);
if (args[0] !== 'web' || args[1] !== '--addr' || !args.includes('--no-open')) process.exit(8);
const addr = args[2];
const port = Number(addr.split(':')[1]);
const key = process.env.MAGPIE_WEB_KEY || 'missing_key';
const cookieName = `magpie_web_${port}`;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  if (url.pathname === '/' && url.searchParams.get('k') === key) {
    res.writeHead(303, {
      'set-cookie': `${cookieName}=${key}; Path=/; HttpOnly; SameSite=Lax`,
      location: '/',
    });
    res.end();
    return;
  }
  if (!req.headers.cookie?.includes(`${cookieName}=${key}`)) {
    res.writeHead(401);
    res.end('unauthorized');
    return;
  }
  if (req.method === 'POST' && req.headers.origin && req.headers.origin !== `http://127.0.0.1:${port}`) {
    res.writeHead(403);
    res.end('bad upstream origin');
    return;
  }
  if (url.pathname === '/boot.js') {
    res.setHeader('content-type', 'application/javascript');
    res.end('window.bootPrefs = {"lang":"zh","web":true};');
    return;
  }
  if (url.pathname === '/api/state') {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({
      agents: [{id: 'dsh', name: 'DeepSeek Harness'}],
      settings: {redact: true, redactPersonal: true},
    }));
    return;
  }
  if (url.pathname === '/api/masking/preview' && req.method === 'POST') {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({
      off: false,
      hits: [{kind: 'PHONE', placeholder: '{{PHONE_test}}'}],
      text: '手机号 {{PHONE_test}}',
    }));
    return;
  }
  res.setHeader('content-type', 'text/html');
  res.end('<!doctype html><html><head><title>magpie</title><script src="boot.js"></script></head><body><form action="/_magpie/sign-in"></form></body></html>');
});
server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`magpie web: http://127.0.0.1:${port}/?k=${key}\n`);
});
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@unittest.skipUnless(shutil.which('node'), 'Node runtime required')
class MagpieProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        directory = Path(cls.temp.name)
        fake = directory / 'fake-magpie.mjs'
        fake.write_text(FAKE_MAGPIE)
        fake.chmod(0o755)
        cls.logfile = directory / 'magpie-proxy.log'
        cls.log = cls.logfile.open('w')
        cls.port, upstream = free_port(), free_port()
        cls.origin = f'http://127.0.0.1:{cls.port}'
        cls.base = cls.origin + '/magpie/'
        cls.secret = 'test_magpie_web_key_never_log_12345'
        cls.process = subprocess.Popen(
            ['node', str(ROOT / 'root/scripts/workspace/magpie-proxy.mjs'), '--port', str(cls.port)],
            env=dict(
                os.environ,
                HOME=str(directory),
                MAGPIE_BIN=str(fake),
                MAGPIE_WEB_KEY=cls.secret,
                MAGPIE_WEB_UPSTREAM_PORT=str(upstream),
                MAGPIE_WEB_PROXY_PREFIX='/magpie',
            ),
            stdout=cls.log,
            stderr=cls.log,
            start_new_session=True,
        )
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
            time.sleep(0.05)
        else:
            cls.tearDownClass()
            raise AssertionError('Magpie proxy did not establish a browser session')

    @classmethod
    def tearDownClass(cls):
        os.killpg(cls.process.pid, signal.SIGTERM)
        cls.process.wait(timeout=10)
        cls.log.close()
        cls.temp.cleanup()

    def test_index_bootstraps_scoped_cookie_and_rewrites_sign_in_action(self):
        self.assertIn('<title>magpie</title>', self.html)
        self.assertIn('action="/magpie/_magpie/sign-in"', self.html)
        cookie = next(iter(self.jar))
        self.assertEqual(cookie.path, '/magpie/')
        self.assertTrue(cookie.has_nonstandard_attr('HttpOnly'))
        self.assertNotIn(self.secret, self.logfile.read_text())

    def test_index_reloads_without_url_credentials(self):
        # user:pass@host URLs break relative fetch(); the injected head script drops the userinfo.
        head = self.html[:self.html.index('<title>')]
        self.assertIn('u.username||u.password', head)
        self.assertIn('location.replace(u.href)', head)
        # location.href hides the userinfo in Chrome; document.URL keeps it.
        self.assertIn('new URL(document.URL)', head)

    def test_dsh_model_list_syncs_from_gateway_models(self):
        subprocess.run(['node', str(ROOT / 'tests/magpie-model-sync.mjs'),
                        (ROOT / 'root/scripts/workspace/magpie-model-sync.mjs').as_uri()], check=True)

    def test_boot_shim_prefixes_magpie_routes_only(self):
        with self.browser.open(self.base + 'boot.js') as response:
            boot_js = response.read().decode()
        self.assertIn('window.bootPrefs', boot_js)
        script = f'''
import assert from 'node:assert/strict';
const calls = [];
globalThis.window = {{
  fetch(url) {{ calls.push(url); return Promise.resolve(url); }}
}};
{boot_js}
await globalThis.window.fetch('/api/state');
await globalThis.window.fetch('/plugin-page/demo');
await globalThis.window.fetch('/_magpie/sign-in');
await globalThis.window.fetch('https://api.deepseek.com/v1/models');
assert.deepEqual(calls, [
  '/magpie/api/state',
  '/magpie/plugin-page/demo',
  '/magpie/_magpie/sign-in',
  'https://api.deepseek.com/v1/models',
]);
'''
        subprocess.run(['node', '--input-type=module', '-e', script], check=True, timeout=5)

    def test_api_requires_cookie_and_forwards_post_with_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(self.base + 'api/state')
        self.assertEqual(failure.exception.code, 401)
        with self.browser.open(self.base + 'api/state') as response:
            state = json.load(response)
        self.assertEqual(state['agents'][0]['id'], 'dsh')
        self.assertTrue(state['settings']['redact'])
        request = urllib.request.Request(
            self.base + 'api/masking/preview',
            data=json.dumps({'text': '手机号 13800138000'}).encode(),
            headers={'Content-Type': 'application/json', 'Origin': self.origin},
            method='POST',
        )
        with self.browser.open(request) as response:
            preview = json.load(response)
        self.assertEqual(preview['text'], '手机号 {{PHONE_test}}')

    def test_cross_origin_and_cross_site_cannot_bootstrap(self):
        for headers in [{'Origin': 'https://evil.test'}, {'Sec-Fetch-Site': 'cross-site'}]:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(urllib.request.Request(self.base, headers=headers))
            self.assertEqual(failure.exception.code, 403)
