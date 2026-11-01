#!/usr/bin/env python3
"""Keep WeChat's Qt DPI stable across login/logout window recreation."""
import math
import os
from pathlib import Path
import re
import subprocess
import sys


def valid_dpi(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return format(number, 'g')


def desktop_dpi(env):
    try:
        result = subprocess.run(['xrdb', '-query'], env=env, capture_output=True,
                                text=True, timeout=2, check=False)
        match = re.search(r'^Xft\.dpi:\s*(\S+)', result.stdout, re.MULTILINE)
        if match and valid_dpi(match[1]):
            return valid_dpi(match[1])
    except (OSError, subprocess.TimeoutExpired):
        pass
    # The persisted resource also works before the desktop's xrdb is ready.
    try:
        resources = (Path(env.get('HOME', '/config')) / '.Xresources').read_text()
        match = re.search(r'^Xft\.dpi:\s*(\S+)', resources, re.MULTILINE)
        if match and valid_dpi(match[1]):
            return valid_dpi(match[1])
    except OSError:
        pass
    return '96'


def launch_environment(original):
    env = original.copy()
    env.update(QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1', QT_ACCESSIBILITY='1', NO_AT_BRIDGE='0')
    if env.get('QT_FONT_DPI'):
        return env
    setting = env.get('WECHAT_FIXED_DPI')
    if setting is None:
        try:
            setting = (Path(env.get('HOME', '/config')) /
                       '.config/weharbor/wechat-dpi').read_text().strip()
        except OSError:
            setting = 'auto'
    setting = setting.strip().lower()
    if setting in {'off', 'false', '0'}:
        return env
    if setting == 'auto':
        dpi = desktop_dpi(env)
    else:
        dpi = valid_dpi(setting)
        if dpi is None:
            print('WeHarbor: invalid WECHAT_FIXED_DPI; using desktop DPI', file=sys.stderr)
            dpi = desktop_dpi(env)
    env['QT_FONT_DPI'] = dpi
    return env


def main():
    # Keep argv[0] compatible with the upstream stop/restart process matcher.
    os.execve('/opt/wechat/wechat', ['/usr/bin/wechat', *sys.argv[1:]],
              launch_environment(os.environ))


if __name__ == '__main__':
    main()
