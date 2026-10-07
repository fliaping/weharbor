#!/usr/bin/env python3
"""Check the desktop and enabled helpers without requiring WeChat login."""
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


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
    if enabled('AUTO_START_WEFLOW'):
        subprocess.run(['pgrep', '-x', 'weflow'], check=True, stdout=subprocess.DEVNULL)
    if enabled('AUTO_START_WECHAT'):
        subprocess.run(['pgrep', '-x', 'wechat'], check=True, stdout=subprocess.DEVNULL)
    if enabled('ENABLE_APP_SWITCHER'):
        subprocess.run(['pgrep', '-f', '/scripts/app-switcher/app-switcher.py'],
                       check=True, stdout=subprocess.DEVNULL)
    if enabled('ENABLE_BROWSER_NOTIFICATIONS'):
        status = json.loads(get('http://127.0.0.1:8765/health'))
        if status.get('status') != 'ok':
            raise ValueError('Notification bridge is not healthy')
    # The API is optional on first launch. If explicitly enabled, check it too.
    config_path = Path('/config/.config/weflow/WeFlow-config.json')
    if enabled('AUTO_START_WEFLOW') and config_path.exists():
        config = json.loads(config_path.read_text())
        if config.get('httpApiEnabled'):
            port = int(config.get('httpApiPort', 5031))
            if json.loads(get(f'http://127.0.0.1:{port}/health')).get('status') != 'ok':
                raise ValueError('WeFlow API is not healthy')
    print('WeHarbor: healthy')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'WeHarbor: {type(error).__name__}', file=sys.stderr)
        sys.exit(1)
