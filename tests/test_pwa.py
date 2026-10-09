import importlib.util
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'root/usr/share/weharbor/pwa'
spec = importlib.util.spec_from_file_location('install_web', ROOT / 'root/scripts/weharbor/install-web.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class PwaTests(unittest.TestCase):
    def test_manifest_icons_and_subpath_identity(self):
        manifest = json.loads((ASSETS / 'weharbor.webmanifest').read_text())
        self.assertEqual(manifest['name'], 'WeHarbor｜微港')
        for key in ['id', 'start_url', 'scope']:
            self.assertEqual(manifest[key], './')
        self.assertEqual(manifest['display'], 'standalone')
        for icon in manifest['icons']:
            content = (ASSETS / icon['src']).read_bytes()
            self.assertEqual(content[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', content[16:24])
            self.assertEqual(icon['sizes'], f'{width}x{height}')
        self.assertTrue(any(i['sizes'] == '512x512' and i['purpose'] == 'maskable'
                            for i in manifest['icons']))

    def test_template_migration_is_repeatable_and_keeps_authentication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nginx = root / 'default.conf'
            original = ('server {\n  auth_basic "Login";\n  auth_basic_user_file /etc/nginx/.htpasswd;\n'
                        '  location SUBFOLDERfiles {\n  }\n}\n') * 2
            nginx.write_text(original)
            shutil.copyfile(ROOT / 'root/defaults/weharbor-pwa.conf', root / 'weharbor-pwa.conf')
            for name in ['selkies-dashboard', 'selkies-dashboard-wish', 'web']:
                dashboard = root / name
                (dashboard / 'assets').mkdir(parents=True)
                html = '<!doctype html><html><body><div id="app"></div></body></html>'
                if name != 'selkies-dashboard-wish':
                    html = html.replace('<body>', '<head><title>Selkies</title><link rel="manifest" href="manifest.json"></head><body>')
                (dashboard / 'index.html').write_text(html)
                (dashboard / 'assets/main.js').write_text('document.title="Selkies";fetch("manifest.json").then(useManifest)')
            web.install(root, ASSETS, nginx)
            first = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            web.install(root, ASSETS, nginx)
            second = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(first, second)
            config = nginx.read_text()
            self.assertEqual(config.count('auth_basic "Login";'), 2)
            self.assertEqual(config.count('location = SUBFOLDERweharbor-sw.js'), 2)
            self.assertNotIn('include /defaults/weharbor-pwa.conf', config)
            # init-nginx strips '#' globally when enabling browser passwords.
            self.assertNotIn('#', config)
            for name in ['selkies-dashboard', 'selkies-dashboard-wish', 'web']:
                dashboard = root / name
                html = (dashboard / 'index.html').read_text()
                self.assertEqual(html.count('rel="manifest"'), 1)
                self.assertEqual(html.count('weharbor-pwa.js'), 1)
                self.assertIn('<title>WeHarbor｜微港</title>', html)
                self.assertEqual((dashboard / 'pwa-icons').stat().st_mode & 0o777, 0o755)
                self.assertEqual((dashboard / 'pwa-icons/icon-512.png').stat().st_mode & 0o777, 0o644)
                self.assertIn('fetch("weharbor.webmanifest",{cache:"no-store"})',
                              (dashboard / 'assets/main.js').read_text())

    @unittest.skipUnless(shutil.which('node'), 'Node needed for Service Worker behavior checks')
    def test_worker_preserves_auth_errors_and_never_handles_api_or_sse(self):
        subprocess.run(['node', str(ROOT / 'tests/pwa-worker.cjs'), str(ASSETS / 'weharbor-sw.js')], check=True)
