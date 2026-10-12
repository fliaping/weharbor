import importlib.util
import signal
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'app_control', ROOT / 'root/scripts/notifications/app_control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class AppControlTests(unittest.TestCase):
    def test_switch_during_window_startup_does_not_launch_duplicate(self):
        manager = control.AppController()
        manager.windows = Mock()
        manager.windows.activate.return_value = None
        with patch.object(control.os, 'getuid', return_value=1000), \
                patch.object(manager, 'processes', return_value={41: ('time', True)}), \
                patch.object(manager, 'launch') as launch:
            manager.switch('wechat')
            launch.assert_not_called()

    def test_switch_stopped_app_launches_and_releases_lock(self):
        manager = control.AppController()
        manager.windows = Mock()
        manager.windows.activate.return_value = None
        with patch.object(control.os, 'getuid', return_value=1000), \
                patch.object(manager, 'processes', return_value={}), \
                patch.object(manager, 'launch') as launch:
            manager.switch('weflow')
            launch.assert_called_once_with('weflow')
        self.assertFalse(manager.locks['weflow'].locked())

    def test_restart_requires_same_origin_json_custom_header(self):
        headers = {'X-WeHarbor-Action': 'restart', 'Origin': 'https://desktop.example:7555'}
        self.assertTrue(control.permitted_request(headers, 'desktop.example:7555', 'application/json'))
        for invalid in [{}, {**headers, 'Origin': 'https://evil.example'},
                        {**headers, 'Origin': 'https://desktop.example:443'},
                        {**headers, 'Origin': 'null'},
                        {**headers, 'Sec-Fetch-Site': 'cross-site'},
                        {**headers, 'Sec-Fetch-Site': 'same-site'}]:
            self.assertFalse(control.permitted_request(invalid, 'desktop.example:7555', 'application/json'))
        self.assertFalse(control.permitted_request(headers, 'desktop.example:7555', 'text/plain'))

    def test_unknown_app_never_launches_and_root_is_rejected(self):
        manager = control.AppController()
        with patch.object(control.subprocess, 'Popen') as launch:
            with self.assertRaises(ValueError):
                manager.restart('../../bin/sh')
            with patch.object(control.os, 'getuid', return_value=0):
                with self.assertRaises(RuntimeError):
                    manager.restart('wechat')
            launch.assert_not_called()

    def test_duplicate_requests_do_not_interrupt_current_restart(self):
        manager = control.AppController()
        manager.locks['wechat'].acquire()
        with patch.object(control.os, 'getuid', return_value=1000):
            with self.assertRaises(control.RestartBusy):
                manager.restart('wechat')
        self.assertTrue(manager.locks['wechat'].locked())
        manager.locks['wechat'].release()

    def test_recycled_pids_are_not_signalled(self):
        manager = control.AppController()
        with patch.object(manager, 'processes', return_value={41: ('new-start', True)}), \
                patch.object(control.os, 'kill') as kill:
            manager.send('wechat', {41: ('old-start', True)}, signal.SIGKILL)
            kill.assert_not_called()
            manager.send('wechat', {41: ('new-start', True)}, signal.SIGTERM)
            kill.assert_called_once_with(41, signal.SIGTERM)

    def test_stop_failure_releases_lock_and_never_starts_second_copy(self):
        manager = control.AppController()
        with patch.object(control.os, 'getuid', return_value=1000), \
                patch.object(manager, 'processes', return_value={41: ('time', True)}), \
                patch.object(manager, 'send') as send, \
                patch.object(manager, 'wait_stopped', return_value=False), \
                patch.object(control.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'did not stop'):
                manager.restart('wechat')
            self.assertEqual([call.args[2] for call in send.call_args_list],
                             [signal.SIGTERM, signal.SIGTERM, signal.SIGKILL])
            launch.assert_not_called()
        self.assertFalse(manager.locks['wechat'].locked())
