import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('healthcheck', ROOT / 'root/scripts/weharbor/healthcheck.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class HealthcheckTests(unittest.TestCase):
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
                return b'{"wechat":{},"weflow":{}}'
            return b'<html></html>'
        with patch.dict(os.environ, {'AUTO_START_WECHAT': 'false', 'AUTO_START_WEFLOW': 'false',
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
