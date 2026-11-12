"""Remote-access settings: env precedence, masking, frp rendering, redaction."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'root/scripts/workspace'))
import remote_access as ra

CLEAN = {k: '' for fields in ra.FIELDS.values() for k in [spec[0] for spec in fields.values()]}

class RemoteAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.patches = [patch.object(ra, 'SETTINGS', root / 'remote-access.json'),
                        patch.object(ra, 'FRP_RAW', root / 'frp/frpc.toml'),
                        patch.object(ra, 'RUNTIME', root / 'remote'),
                        patch.object(ra, 'STATE', root),
                        patch.dict(os.environ, CLEAN)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()
        self.directory.cleanup()

    def test_disabled_by_default(self):
        for name in ra.SERVICES:
            values, locked, source = ra.effective(name)
            self.assertFalse(values['enabled'], name)
            self.assertEqual(locked, [])
            self.assertEqual(source, 'default')

    def test_env_wins_and_locks(self):
        ra.update('cloudflare', {'enabled': False, 'token': 'u' * 40})
        with patch.dict(os.environ, {'CLOUDFLARE_TUNNEL_TOKEN': 'e' * 40}):
            values, locked, source = ra.effective('cloudflare')
            self.assertTrue(values['enabled'])
            self.assertEqual(values['token'], 'e' * 40)
            self.assertEqual(set(locked), {'enabled', 'token'})
            self.assertEqual(source, 'env')
            ra.update('cloudflare', {'token': 'x' * 40})  # ignored: locked
        self.assertEqual(json.loads(ra.SETTINGS.read_text())['cloudflare']['token'], 'u' * 40)

    def test_secret_is_masked_preserved_and_private(self):
        out = ra.update('tailscale', {'enabled': True, 'authkey': 'tskey-auth-abc123', 'hostname': 'harbor'})
        self.assertEqual(out['settings']['authkey'], ra.MASK)
        self.assertNotIn('tskey-auth-abc123', json.dumps(out))
        ra.update('tailscale', {'authkey': ra.MASK, 'hostname': 'harbor2'})
        values, _, _ = ra.effective('tailscale')
        self.assertEqual(values['authkey'], 'tskey-auth-abc123')
        self.assertEqual(stat.S_IMODE(ra.SETTINGS.stat().st_mode), 0o600)
        with self.assertRaises(ValueError): ra.update('tailscale', {'hostname': 'bad host'})
        with self.assertRaises(ValueError): ra.update('tailscale', {'extra_args': '--auth-key=x'})

    def test_frp_simple_config(self):
        ra.update('frp', {'enabled': True, 'server_addr': 'frp.example.com', 'server_port': '7000',
                          'token': 'sekrit-token', 'remote_port': '6001'})
        values, _, _ = ra.effective('frp')
        text = ra.frp_config(values)
        self.assertIn('remotePort = 6001', text)
        self.assertIn('localPort = 3001', text)
        self.assertIn('transport.tls.enable = true', text)
        ra.validate('frp', values)
        self.assertEqual(ra.public('frp')['url'], 'https://frp.example.com:6001')
        values['remote_port'] = 0
        with self.assertRaises(ValueError): ra.frp_config(values)

    def test_frp_raw_masking_round_trip(self):
        raw = 'serverAddr = "a.example"\nauth.token = "very-secret"\n'
        ra.update('frp', {'enabled': True, 'mode': 'raw', 'raw': raw})
        shown = ra.public('frp')['raw']
        self.assertNotIn('very-secret', shown)
        ra.update('frp', {'raw': shown.replace('a.example', 'b.example')})
        self.assertIn('very-secret', ra.FRP_RAW.read_text())
        self.assertIn('b.example', ra.FRP_RAW.read_text())
        with self.assertRaises(ValueError): ra.update('frp', {'raw': 'serverAddr = ['})

    def test_mounted_frpc_toml_enables_raw_mode(self):
        ra.FRP_RAW.parent.mkdir(parents=True)
        ra.FRP_RAW.write_text('serverAddr = "x"\n')
        values, _, _ = ra.effective('frp')
        self.assertTrue(values['enabled']); self.assertEqual(values['mode'], 'raw')

    def test_redaction(self):
        text = ra.redact('key tskey-auth-k1 token=abc eyJ' + 'a' * 30 + ' mine', ['mine'])
        for secret in ['tskey-auth-k1', 'abc', 'eyJ', 'mine']:
            self.assertNotIn(secret, text)

    def test_legacy_migration(self):
        (ra.STATE / 'network.json').write_text(json.dumps({'tailscale': True, 'cloudflare': True}))
        (ra.STATE / 'cloudflare.token').write_text('t' * 40)
        ra.migrate_legacy()
        self.assertTrue(ra.effective('tailscale')[0]['enabled'])
        self.assertEqual(ra.effective('cloudflare')[0]['token'], 't' * 40)

if __name__ == '__main__':
    unittest.main()
