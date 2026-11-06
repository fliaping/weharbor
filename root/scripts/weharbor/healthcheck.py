#!/usr/bin/env python3
"""Check the desktop and enabled helpers without requiring WeChat login."""
import base64
import json
import os
import subprocess
import sys
import urllib.request


def enabled(name):
    return os.environ.get(name, 'true').lower() in {'true', '1', 'yes', 'on'}


def get(url, authenticated=False):
    headers = {}
    if authenticated and os.environ.get('PASSWORD'):
        value = os.environ.get('CUSTOM_USER', 'abc') + ':' + os.environ['PASSWORD']
        headers['Authorization'] = 'Basic ' + base64.b64encode(value.encode()).decode()
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=4) as response:
        return response.read()


def main():
    get('http://127.0.0.1:3000/', authenticated=True)
    if enabled('AUTO_START_WECHAT'):
        subprocess.run(['pgrep', '-x', 'wechat'], check=True, stdout=subprocess.DEVNULL)
    if enabled('ENABLE_MAGPIE'):
        subprocess.run(['pgrep', '-x', 'magpie'], check=True, stdout=subprocess.DEVNULL)
    if enabled('ENABLE_APP_SWITCHER') and os.environ.get('APP_SWITCHER_MODE', 'web') == 'desktop':
        subprocess.run(['pgrep', '-f', '/scripts/app-switcher/app-switcher.py'],
                       check=True, stdout=subprocess.DEVNULL)
    status = json.loads(get('http://127.0.0.1:8765/health'))
    if status.get('status') != 'ok':
        raise ValueError('Application/notification bridge is not healthy')
    if enabled('ENABLE_APP_SWITCHER'):
        apps = json.loads(get('http://127.0.0.1:8765/apps'))
        if 'wechat' not in apps:
            raise ValueError('Application controls are not healthy')
        if os.environ.get('APP_SWITCHER_MODE', 'web') != 'desktop':
            script = get('http://127.0.0.1:3000/weharbor-apps.js', authenticated=True)
            if b'weharbor-apps-button' not in script:
                raise ValueError('Web application controls are not available')
    print('WeHarbor: healthy')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'WeHarbor: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
