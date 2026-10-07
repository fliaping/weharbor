#!/usr/bin/env python3
"""Validate source files without downloading vendor software."""
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / 'versions.lock.json').read_text())
    assert lock['schema'] == 1 and lock['platform'] == 'linux/amd64'
    assert re.fullmatch(r'\d+\.\d+\.\d+', lock['project_version'])
    assert re.search(r'@sha256:[0-9a-f]{64}$', lock['base_image'])
    for name in ['wechat', 'weflow']:
        assert re.fullmatch(r'[0-9a-f]{64}', lock[name]['sha256'])
    assert re.fullmatch(r'[0-9a-f]{64}', lock['weflow']['asar_sha256'])
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert f'ARG BASE_IMAGE={lock["base_image"]}\n' in dockerfile
    assert f'ARG PROJECT_VERSION={lock["project_version"]}\n' in dockerfile
    for directory in ['scripts', 'root', 'skills']:
        for path in (ROOT / directory).rglob('*'):
            if not path.is_file():
                continue
            if path.suffix == '.py':
                ast.parse(path.read_text(), filename=str(path))
            elif path.suffix == '.sh' or path.read_bytes().startswith(b'#!/usr/bin/env bash') or path.read_bytes().startswith(b'#!/usr/bin/with-contenv bash'):
                subprocess.run(['bash', '-n', str(path)], check=True)
            elif path.suffix == '.js' and shutil.which('node'):
                subprocess.run(['node', '--check', str(path)], check=True)
    subprocess.run(['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, check=True)
    print('WeHarbor source validation passed')


if __name__ == '__main__':
    main()
