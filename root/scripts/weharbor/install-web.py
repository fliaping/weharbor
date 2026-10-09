#!/usr/bin/env python3
"""Add WeHarbor branding and PWA assets to upstream dashboard templates."""
import argparse
import hashlib
import re
import shutil
from pathlib import Path

TITLE = 'WeHarbor｜微港'


def install(selkies, assets, nginx):
    revision = hashlib.sha256((assets / 'weharbor-pwa.js').read_bytes()).hexdigest()[:12]
    installed = 0
    for name in ['selkies-dashboard', 'selkies-dashboard-wish', 'web']:
        dashboard = selkies / name
        index = dashboard / 'index.html'
        if not index.is_file():
            continue
        for asset in assets.iterdir():
            target = dashboard / asset.name
            if asset.is_dir():
                shutil.copytree(asset, target, dirs_exist_ok=True)
            else:
                shutil.copyfile(asset, target)
            # Downloaded/private checkouts may carry restrictive directory modes.
            for copied in [target] + (list(target.rglob('*')) if target.is_dir() else []):
                copied.chmod(0o755 if copied.is_dir() else 0o644)
        html = index.read_text()
        html = re.sub(r'<title\b[^>]*>.*?</title>', '', html, flags=re.I | re.S)
        html = re.sub(r'<link\b[^>]*rel=["\'](?:manifest|apple-touch-icon)["\'][^>]*>', '', html, flags=re.I)
        html = re.sub(r'<meta\b[^>]*name=["\'](?:theme-color|apple-mobile-web-app-title)["\'][^>]*>', '', html, flags=re.I)
        html = re.sub(r'<script\b[^>]*src=["\'][^"\']*weharbor-pwa\.js[^"\']*["\'][^>]*>\s*</script>', '', html, flags=re.I)
        tags = (f'<title>{TITLE}</title>'
                '<link rel="manifest" href="./weharbor.webmanifest" crossorigin="use-credentials">'
                '<meta name="theme-color" content="#101c2d">'
                f'<meta name="apple-mobile-web-app-title" content="{TITLE}">'
                '<link rel="apple-touch-icon" href="./pwa-icons/apple-touch-icon.png">'
                f'<script defer src="./weharbor-pwa.js?v={revision}"></script>')
        if re.search(r'</head\s*>', html, re.I):
            html = re.sub(r'</head\s*>', lambda _: tags + '</head>', html, count=1, flags=re.I)
        else:
            html = re.sub(r'(<html\b[^>]*>)', lambda m: m[1] + '<head><meta charset="utf-8">' + tags + '</head>', html, count=1, flags=re.I)
        index.write_text(html)
        # Selkies updates document.title after fetching its generated manifest.
        for directory in ['assets', 'src']:
            for script in (dashboard / directory).rglob('*.js'):
                original = script.read_text()
                source = re.sub(r'document\.title\s*=\s*(["\'])Selkies\1', f'document.title="{TITLE}"', original)
                source = re.sub(r'fetch\((["\'])manifest\.json(?:\?[^"\']*)?\1(?:,\s*\{cache:\s*["\']no-store["\']\})?\)', 'fetch("weharbor.webmanifest",{cache:"no-store"})', source)
                if source != original:
                    script.write_text(source)
        installed += 1
    if not installed:
        raise RuntimeError('No supported Selkies dashboard template found')
    config = nginx.read_text()
    # Inline routes: init-nginx substitutes SUBFOLDER only in the main config.
    # No comments here: upstream enables Basic Auth by stripping every '#'.
    block = (nginx.parent / 'weharbor-pwa.conf').read_text().rstrip() + '\n'
    config = re.sub(r'location = SUBFOLDERweharbor\.webmanifest \{.*?'
                    r'location = SUBFOLDERweharbor-pwa\.js \{.*?\}\n?', '', config, flags=re.S)
    if '  location SUBFOLDERfiles {' not in config:
        raise RuntimeError('Unsupported nginx template: no files location')
    config = config.replace('  location SUBFOLDERfiles {', block + '  location SUBFOLDERfiles {')
    nginx.write_text(config)
    print(f'WeHarbor web integration installed in {installed} dashboards')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selkies', type=Path, default=Path('/usr/share/selkies'))
    parser.add_argument('--assets', type=Path, default=Path('/usr/share/weharbor/pwa'))
    parser.add_argument('--nginx', type=Path, default=Path('/defaults/default.conf'))
    args = parser.parse_args()
    install(args.selkies, args.assets, args.nginx)
