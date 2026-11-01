"""A local source build must include new code and exclude private runtime data."""
import importlib.util
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('workspace_package', Path(__file__).resolve().parents[1] / 'scripts/package-workspace.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class SourceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        for name in ['requirements-linux.txt', 'src/wechat_decrypt_tool/api.py', 'frontend/package.json', 'frontend/package-lock.json', 'src/wechat_decrypt_tool/advanced/new.py']:
            self.write(name, 'source')
        self.write('.gitignore', '.env*\nnode_modules/\noutput/\n')

    def write(self, name, text):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_source_snapshot_includes_untracked_implementation_and_excludes_state(self):
        for name in ['frontend/.env.local', 'frontend/node_modules/secret', 'output/messages.db', 'private.token']:
            self.write(name, 'private')
        target = self.root / 'analysis.tar.gz'
        first = package.analysis_archive(self.source, target)
        with tarfile.open(target) as archive:
            names = archive.getnames()
            self.assertIn('analysis/src/wechat_decrypt_tool/advanced/new.py', names)
            self.assertFalse(any('secret' in name or '.env' in name or '.token' in name or '/output/' in name for name in names))
        self.assertEqual(first, package.analysis_archive(self.source, target))

    def test_symlink_to_private_files_is_rejected(self):
        private = self.write('private.token', 'secret')
        (self.source / 'frontend/link').symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            package.analysis_archive(self.source, self.root / 'analysis.tar.gz')
