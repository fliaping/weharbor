import hashlib
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_assets', ROOT / 'scripts/prepare-assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.data = b'verified vendor package'
        self.config = {'filename': 'package.tar.gz', 'version': '1.0.0',
                       'original_filename': 'vendor-1.0.0.tar.gz',
                       'sha256': hashlib.sha256(self.data).hexdigest(),
                       'url': 'https://example.invalid/package.tar.gz'}

    def test_verified_cache_works_offline(self):
        (self.directory / self.config['filename']).write_bytes(self.data)
        with patch.object(assets.urllib.request, 'urlopen', side_effect=AssertionError('must stay offline')):
            assets.prepare('weflow', self.config, self.directory)

    def test_corrupted_cache_is_rejected(self):
        destination = self.directory / self.config['filename']
        destination.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            assets.prepare('weflow', self.config, self.directory)
        self.assertEqual(destination.read_bytes(), b'corrupt')

    def test_wrong_download_is_never_cached(self):
        response = BytesIO(b'wrong version')
        response.geturl = lambda: self.config['url']
        with patch.dict(os.environ, {}, clear=True), patch.object(assets.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                assets.prepare('weflow', self.config, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_valid_download_is_cached(self):
        response = BytesIO(self.data)
        response.geturl = lambda: self.config['url']
        with patch.dict(os.environ, {}, clear=True), patch.object(assets.urllib.request, 'urlopen', return_value=response):
            assets.prepare('weflow', self.config, self.directory)
        self.assertEqual((self.directory / self.config['filename']).read_bytes(), self.data)

    def test_missing_source_fails_with_instructions(self):
        self.config['url'] = None
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'WEFLOW_DOWNLOAD_URL'):
                assets.prepare('weflow', self.config, self.directory)

    def test_http_source_is_rejected(self):
        self.config['url'] = 'http://example.invalid/package.tar.gz'
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                assets.prepare('weflow', self.config, self.directory)


class InitializationTests(unittest.TestCase):
    def test_password_is_private_random_and_existing_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copy2(ROOT / 'scripts/init.sh', root / 'scripts/init.sh')
            shutil.copy2(ROOT / '.env.example', root / '.env.example')
            command = ['bash', str(root / 'scripts/init.sh')]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            env_path = root / '.env'
            original = env_path.read_bytes()
            values = dict(line.split('=', 1) for line in original.decode().splitlines()
                          if line and not line.startswith('#'))
            self.assertGreaterEqual(len(values['PASSWORD']), 24)
            self.assertEqual(values['PUID'], str(os.getuid()))
            self.assertEqual(values['PGID'], str(os.getgid()))
            self.assertEqual(values['BIND_ADDRESS'], '127.0.0.1')
            self.assertEqual(env_path.stat().st_mode & 0o777, 0o600)
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            self.assertEqual(env_path.read_bytes(), original)
