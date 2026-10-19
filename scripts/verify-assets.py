#!/usr/bin/env python3
"""Verify pinned vendor packages before they are installed unmodified."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def verify(path, expected):
    if digest(path) != expected:
        raise ValueError(f'SHA256 mismatch: {Path(path).name}; refusing this package')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=['wechat', 'alpha'])
    parser.add_argument('--lock', required=True, type=Path)
    parser.add_argument('--asset', required=True, type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    component = json.loads(args.lock.read_text())[args.component]
    verify(args.asset, component['sha256'])
    package = {'wechat': 'wechat', 'alpha': 'alpha'}[args.component]
    label = {'wechat': 'WeChat', 'alpha': 'Alpha'}[args.component]
    for field, expected in [('Package', package), ('Version', component['version']), ('Architecture', 'amd64')]:
        actual = subprocess.check_output(['dpkg-deb', '-f', str(args.asset), field], text=True).strip()
        if actual != expected:
            raise ValueError(f'{label} {field}: expected {expected}, got {actual}')
    if args.install:
        # apt resolves the package's declared runtime dependencies from Debian.
        subprocess.run(['apt-get', 'install', '-y', '--no-install-recommends', str(args.asset.resolve())],
                       check=True)
        installed = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', package], text=True)
        if installed != component['version']:
            raise ValueError(f'Installed {label} version differs: {installed}')
    print(f'{args.component}: {component["version"]} verified')


if __name__ == '__main__':
    main()
