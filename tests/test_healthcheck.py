import importlib.util
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('healthcheck', ROOT / 'root/scripts/weharbor/healthcheck.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class HealthcheckTests(unittest.TestCase):
    def test_blank_alpha_window_is_unhealthy_without_native_hosts(self):
        hosts = ('alpha-engine', 'alpha-security-host', 'alpha-data-host')
        for missing in hosts:
            def run(args, **kwargs):
                return subprocess.CompletedProcess(args, int(missing in args[-1]))

            with self.subTest(missing=missing), \
                    patch.dict(os.environ, {'AUTO_START_ALPHA': 'true'}, clear=True), \
                    patch.object(health, 'get', return_value=b'<html></html>'), \
                    patch.object(health.subprocess, 'run', side_effect=run):
                with self.assertRaisesRegex(ValueError, missing):
                    health.main()

    def test_native_hosts_are_checked_without_requiring_first_run_api(self):
        def get(url, authenticated=False):
            if ':5031/' in url:
                raise ConnectionRefusedError()
            return b'{"status":"ok"}'

        with patch.dict(os.environ, {'AUTO_START_ALPHA': 'true', 'AUTO_START_WECHAT': 'false',
                                    'ENABLE_APP_SWITCHER': 'false'}, clear=True), \
                patch.object(health, 'get', side_effect=get), \
                patch.object(health.subprocess, 'run',
                             return_value=subprocess.CompletedProcess([], 0)) as run:
            health.main()
            for name in ('alpha-engine', 'alpha-security-host', 'alpha-data-host'):
                self.assertTrue(any(call.args[0] ==
                                    ['pgrep', '-f', f'^/opt/Alpha/resources/bin/{name}( |$)']
                                    for call in run.call_args_list))

    def check(self, asset, mode='web', enabled='true'):
        def get(url, authenticated=False):
            if url.endswith('/weharbor-apps.js'):
                self.assertTrue(authenticated)
                if isinstance(asset, Exception):
                    raise asset
                return asset
            if url.endswith('/health'):
                return b'{"status":"ok"}'
            if url.endswith('/apps'):
                return b'{"wechat":{},"alpha":{}}'
            return b'<html></html>'
        with patch.dict(os.environ, {'AUTO_START_WECHAT': 'false', 'AUTO_START_ALPHA': 'false',
                                     'ENABLE_APP_SWITCHER': enabled, 'APP_SWITCHER_MODE': mode}, clear=True), \
                patch.object(health, 'get', side_effect=get) as mock_get, \
                patch.object(health.subprocess, 'run'):
            health.main()
            return [call.args[0] for call in mock_get.call_args_list]

    def test_web_dock_asset_is_checked(self):
        self.assertIn('http://127.0.0.1:3000/weharbor-apps.js', self.check(b'weharbor-apps-button'))

    def test_unreadable_asset_fails_health_even_when_page_and_api_work(self):
        with self.assertRaises(HTTPError):
            self.check(HTTPError('http://127.0.0.1:3000/weharbor-apps.js', 403, 'Forbidden', {}, None))

    def test_invalid_asset_fails_health(self):
        with self.assertRaises(ValueError):
            self.check(b'<html>Error</html>')

    def test_desktop_or_disabled_dock_does_not_require_web_asset(self):
        for mode, enabled in [('desktop', 'true'), ('web', 'false')]:
            self.assertNotIn('http://127.0.0.1:3000/weharbor-apps.js', self.check(b'', mode, enabled))
