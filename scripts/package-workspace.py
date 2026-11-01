#!/usr/bin/env python3
"""Package an explicit local analysis checkout without changing pinned inputs."""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_FILES = {'requirements-linux.txt', 'pyproject.toml', 'main.py', 'README.md', 'THIRD_PARTY_NOTICES.md'}


def git_files(root):
    result = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root)
    return sorted(set(Path(p) for p in result.decode().split('\0') if p))


def analysis_archive(source, target):
    """Only source files known to Git; no output, profiles, .env or node_modules."""
    files = []
    for relative in git_files(source):
        if relative.parts[0] not in ('src', 'frontend') and relative.as_posix() not in ANALYSIS_FILES and relative.as_posix() != 'scripts/advanced_mcp_stdio.py':
            continue
        if any(part in ('node_modules', '__pycache__', '.nuxt', '.output', '.git', 'data', 'output') or part.startswith('.env') for part in relative.parts):
            continue
        path = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError('Refusing source symlink: ' + str(relative))
        if path.is_file():
            files.append(relative)
    required = {'requirements-linux.txt', 'src/wechat_decrypt_tool/api.py', 'frontend/package.json', 'frontend/package-lock.json'}
    if required - {p.as_posix() for p in files}:
        raise ValueError('Incomplete analysis checkout')
    with target.open('wb') as output, gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as archive:
        for relative in files:
            path = source / relative
            info = tarfile.TarInfo('analysis/' + relative.as_posix())
            info.size, info.mode = path.stat().st_size, 0o644
            with path.open('rb') as stream:
                archive.addfile(info, stream)
    with target.open('rb') as stream:
        return {'sha256': hashlib.file_digest(stream, 'sha256').hexdigest(), 'files': len(files)}


def package(source, destination):
    source, destination = source.resolve(), destination.resolve()
    if destination.is_relative_to(source) or destination.is_relative_to(ROOT):
        raise ValueError('Build context must be outside both source repositories')
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    for relative in git_files(ROOT):
        if relative.as_posix() not in ('Dockerfile', '.dockerignore', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'scripts/verify-assets.py') and relative.parts[0] != 'root' and not relative.as_posix().startswith(('runtime/harness/', 'skills/weharbor-api/')):
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Refusing integration symlink: ' + str(relative))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    lock = json.loads((ROOT / 'versions.lock.json').read_text())
    assets = destination / 'downloads'
    assets.mkdir()
    for name in ('wechat', 'alpha', 'node', 'tailscale', 'cloudflared', 'magpie'):
        component = lock[name]
        path = ROOT / 'downloads' / component['filename']
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != component['sha256']:
                raise ValueError('Pinned asset checksum mismatch: ' + name)
        shutil.copyfile(path, assets / component['filename'])
    metadata = analysis_archive(source, assets / 'analysis.tar.gz')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    lock['analysis'] = {'version': revision + '+workspace.' + metadata['sha256'][:12],
                        'filename': 'analysis.tar.gz', 'url': 'local-checkout', 'sha256': metadata['sha256']}
    (destination / 'versions.lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    manifest = {'analysis': lock['analysis'], 'source_files': metadata['files'], 'base_image': lock['base_image'],
                'note': 'Explicit local source snapshot; canonical versions.lock.json remains unchanged.'}
    (destination / 'workspace-source.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New persistent build-context directory')
    args = parser.parse_args()
    manifest = package(args.analysis, args.output)
    print(json.dumps({'context': str(args.output.resolve()), **manifest}, indent=2))
    print('Build: docker build --platform linux/amd64 -t weharbor:workspace-local ' + str(args.output.resolve()))


if __name__ == '__main__':
    main()
