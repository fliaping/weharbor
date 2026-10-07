#!/usr/bin/env python3
"""Download or verify vendor archives using versions.lock.json."""
import argparse
import importlib.util
import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('asset_verifier', ROOT / 'scripts/verify-assets.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def prepare(component, config, directory, check_only=False):
    destination = directory / config['filename']
    if destination.exists():
        verifier.verify(destination, config['sha256'])
        print(f'{component}: cached {config["version"]} verified')
        return
    if check_only:
        raise ValueError(f'Missing {destination}; prepare this asset before building')
    url = os.environ.get(f'{component.upper()}_DOWNLOAD_URL') or config.get('url')
    if not url:
        raise ValueError(f'{component}: place {config["original_filename"]} at {destination}, '
                         f'or set {component.upper()}_DOWNLOAD_URL to the trusted upstream asset URL')
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError(f'{component}: download URL must use HTTPS')
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f'.{component}-', suffix='.partial', dir=directory)
    temporary = Path(temporary_name)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'WeHarbor/0.1'})
        print(f'{component}: downloading pinned {config["version"]}', flush=True)
        with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(request, timeout=120) as response:
            if urllib.parse.urlparse(response.geturl()).scheme != 'https':
                raise ValueError('Download redirected to an insecure URL')
            shutil.copyfileobj(response, output)
        verifier.verify(temporary, config['sha256'])
        temporary.replace(destination)
        print(f'{component}: downloaded and verified')
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'versions.lock.json').read_text())
    # Check WeFlow first: its historical public release URL is not yet confirmed.
    for component in ['weflow', 'wechat']:
        prepare(component, lock[component], ROOT / 'downloads', args.check_only)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
