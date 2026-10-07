#!/usr/bin/env python3
"""Verify pinned vendor packages; keep the WeFlow ASAR byte-for-byte intact."""
import argparse
import hashlib
import json
import struct
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


def asar_version(path):
    with Path(path).open('rb') as stream:
        prefix = stream.read(16)
        header_size = struct.unpack_from('<I', prefix, 4)[0]
        json_size = struct.unpack_from('<I', prefix, 12)[0]
        entry = json.loads(stream.read(json_size))['files']['package.json']
        stream.seek(8 + header_size + int(entry['offset']))
        return json.loads(stream.read(entry['size']))['version']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=['wechat', 'weflow'])
    parser.add_argument('--lock', required=True, type=Path)
    parser.add_argument('--asset', required=True, type=Path)
    parser.add_argument('--extract', type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    component = json.loads(args.lock.read_text())[args.component]
    verify(args.asset, component['sha256'])
    if args.component == 'wechat':
        for field, expected in [('Package', 'wechat'), ('Version', component['version']), ('Architecture', 'amd64')]:
            actual = subprocess.check_output(['dpkg-deb', '-f', str(args.asset), field], text=True).strip()
            if actual != expected:
                raise ValueError(f'WeChat {field}: expected {expected}, got {actual}')
        if args.install:
            subprocess.run(['dpkg', '-i', str(args.asset)], check=True)
            installed = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'wechat'], text=True)
            if installed != component['version']:
                raise ValueError(f'Installed WeChat version differs: {installed}')
    elif args.extract:
        args.extract.mkdir(parents=True, exist_ok=True)
        subprocess.run(['tar', '-xzf', str(args.asset), '--strip-components=1', '-C', str(args.extract)], check=True)
        asar = args.extract / 'resources/app.asar'
        verify(asar, component['asar_sha256'])
        if asar_version(asar) != component['version']:
            raise ValueError('WeFlow package.json version differs from the lock file')
        if not (args.extract / 'weflow').is_file():
            raise ValueError('WeFlow executable is missing')
    print(f'{args.component}: {component["version"]} verified')


if __name__ == '__main__':
    main()
