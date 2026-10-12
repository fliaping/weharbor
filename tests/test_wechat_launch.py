import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'wechat_launch', ROOT / 'root/scripts/weharbor/wechat-launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class WeChatLaunchTests(unittest.TestCase):
    def test_auto_snapshots_desktop_dpi_without_mutating_parent(self):
        env = {'HOME': '/config', 'DISPLAY': ':1'}
        with patch.object(launcher.subprocess, 'run', return_value=SimpleNamespace(
                stdout='Xft.dpi:\t192\n')):
            result = launcher.launch_environment(env)
        self.assertEqual(result['QT_FONT_DPI'], '192')
        self.assertNotIn('QT_FONT_DPI', env)

    def test_explicit_override_and_native_scaling_opt_out(self):
        with patch.object(launcher, 'desktop_dpi') as query:
            self.assertEqual(launcher.launch_environment(
                {'WECHAT_FIXED_DPI': '144'})['QT_FONT_DPI'], '144')
            self.assertNotIn('QT_FONT_DPI', launcher.launch_environment(
                {'WECHAT_FIXED_DPI': 'off'}))
            self.assertEqual(launcher.launch_environment(
                {'QT_FONT_DPI': '120', 'WECHAT_FIXED_DPI': '192'})['QT_FONT_DPI'], '120')
            query.assert_not_called()

    def test_profile_setting_survives_container_restart_and_env_takes_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.config/weharbor/wechat-dpi'
            path.parent.mkdir(parents=True)
            path.write_text('192\n')
            self.assertEqual(launcher.launch_environment(
                {'HOME': temp})['QT_FONT_DPI'], '192')
            self.assertEqual(launcher.launch_environment(
                {'HOME': temp, 'WECHAT_FIXED_DPI': '144'})['QT_FONT_DPI'], '144')

    def test_missing_x_server_falls_back_to_persisted_dpi(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / '.Xresources').write_text('Xft.dpi: 144\n')
            with patch.object(launcher.subprocess, 'run', side_effect=FileNotFoundError):
                self.assertEqual(launcher.desktop_dpi({'HOME': temp}), '144')
            with patch.object(launcher.subprocess, 'run', side_effect=launcher.subprocess.TimeoutExpired('xrdb', 2)):
                self.assertEqual(launcher.desktop_dpi({'HOME': temp}), '144')

    def test_invalid_values_cannot_break_launch(self):
        for value in ['nan', 'inf', '-1', 'oops', '']:
            with self.subTest(value=value), patch.object(launcher, 'desktop_dpi', return_value='96'):
                self.assertEqual(launcher.launch_environment(
                    {'WECHAT_FIXED_DPI': value})['QT_FONT_DPI'], '96')

    def test_exec_preserves_vendor_binary_arguments_and_process_matcher(self):
        with patch.object(launcher.os, 'execve') as execute, \
                patch.object(launcher.sys, 'argv', ['launcher.py', '--example', 'value']), \
                patch.object(launcher, 'launch_environment', return_value={'QT_FONT_DPI': '192'}):
            launcher.main()
        execute.assert_called_once_with('/opt/wechat/wechat',
                                        ['/usr/bin/wechat', '--example', 'value'],
                                        {'QT_FONT_DPI': '192'})
