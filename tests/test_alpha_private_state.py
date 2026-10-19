import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'alpha_private_state', ROOT / 'root/scripts/alpha/prepare-private-state.py')
private_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(private_state)


class AlphaPrivateStateTests(unittest.TestCase):
    def test_repairs_existing_state_and_preserves_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            for relative in private_state.PRIVATE_PATHS:
                directory = home / relative / 'existing-profile'
                directory.mkdir(parents=True)
                directory.chmod(0o705)
                directory.parent.chmod(0o705)
                secret = directory / 'state'
                secret.write_bytes(b'keep existing state')
                secret.chmod(0o644)
            # Repeat to verify that startup remains safe on existing profiles.
            private_state.prepare(home)
            private_state.prepare(home)
            for relative in private_state.PRIVATE_PATHS:
                root = home / relative
                for path in (root, *root.rglob('*')):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode),
                                     0o700 if path.is_dir() else 0o600)
                self.assertEqual((root / 'existing-profile/state').read_bytes(),
                                 b'keep existing state')

    def test_new_roots_are_private_even_when_mkdir_inherits_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = Path.mkdir

            def inherited_mode(path, *args, **kwargs):
                original(path, *args, **kwargs)
                path.chmod(0o705)

            with patch.object(Path, 'mkdir', inherited_mode):
                private_state.prepare(Path(temporary))
            for relative in private_state.PRIVATE_PATHS:
                self.assertEqual(stat.S_IMODE((Path(temporary) / relative).stat().st_mode), 0o700)

    def test_does_not_follow_links_or_change_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            outside = home / 'other-app'
            outside.mkdir(mode=0o755)
            outside.chmod(0o755)
            file = outside / 'unchanged'
            file.write_bytes(b'unrelated')
            file.chmod(0o644)
            root = home / private_state.PRIVATE_PATHS[0]
            root.mkdir(parents=True)
            (root / 'directory-link').symlink_to(outside, target_is_directory=True)
            (root / 'file-link').symlink_to(file)
            (root / 'broken-link').symlink_to(home / 'missing')
            private_state.prepare(home)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o644)
            self.assertEqual(file.read_bytes(), b'unrelated')

    def test_rejects_a_symlink_as_private_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            outside = home / 'other-app'
            outside.mkdir(mode=0o755)
            outside.chmod(0o755)
            root = home / private_state.PRIVATE_PATHS[0]
            root.parent.mkdir(parents=True)
            root.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(OSError):
                private_state.prepare(home)
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)
