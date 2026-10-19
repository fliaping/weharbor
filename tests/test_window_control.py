import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'window_control', ROOT / 'root/scripts/notifications/window_control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class WindowControlTests(unittest.TestCase):
    def desktop(self, snapshot, remembered=None):
        desktop = control.Desktop(Mock(), types.SimpleNamespace(CurrentTime=0),
                                  Mock(), Mock(), Mock(), remembered or {})
        desktop.snapshot = Mock(return_value=snapshot)
        desktop.send = Mock()
        desktop.connection.create_resource_object.side_effect = lambda _kind, wid: wid
        return desktop

    def windows(self, active=11):
        return {'wechat': [{'id': 11, 'active': active == 11, 'minimized': False},
                           {'id': 12, 'active': active == 12, 'minimized': False}],
                'alpha': [{'id': 21, 'active': active == 21, 'minimized': False},
                           {'id': 22, 'active': False, 'minimized': True}]}

    def test_active_app_cycles_and_only_hides_other_app(self):
        desktop = self.desktop(self.windows())
        self.assertEqual(desktop.activate('wechat'), 12)
        self.assertEqual([call.args for call in desktop.send.call_args_list],
                         [(21, 'WM_CHANGE_STATE', [3, 0, 0, 0, 0]),
                          (12, '_NET_ACTIVE_WINDOW', [2, 0, 0, 0, 0])])
        self.assertEqual(desktop.remembered['wechat'], 12)
        desktop.connection.sync.assert_called_once()

    def test_return_to_remembered_window(self):
        desktop = self.desktop(self.windows(active=21), {'wechat': 12})
        self.assertEqual(desktop.activate('wechat'), 12)

    def test_closed_remembered_window_falls_back(self):
        desktop = self.desktop(self.windows(active=21), {'wechat': 999})
        self.assertEqual(desktop.activate('wechat'), 11)

    def test_foreign_or_closed_window_never_changes_desktop(self):
        for wid in (21, 999):
            desktop = self.desktop(self.windows())
            with self.assertRaises(ValueError):
                desktop.activate('wechat', wid)
            desktop.send.assert_not_called()

    def test_explicit_window_does_not_cycle_or_maximize(self):
        desktop = self.desktop(self.windows())
        self.assertEqual(desktop.activate('wechat', 11), 11)
        self.assertEqual(desktop.send.call_args.args[1], '_NET_ACTIVE_WINDOW')

    def test_no_window_does_not_hide_other_app(self):
        desktop = self.desktop({'wechat': [], 'alpha': self.windows()['alpha']})
        self.assertIsNone(desktop.activate('wechat'))
        desktop.send.assert_not_called()

    def test_snapshot_requires_owned_vendor_pid_and_excludes_desktop_surfaces(self):
        connection = Mock()
        connection.intern_atom.side_effect = lambda name: name
        windows = {}
        properties = {'root': {'_NET_ACTIVE_WINDOW': [11], '_NET_CLIENT_LIST': [11, 22, 33, 44]}}
        for wid, pid, kind in [(11, 101, []), (22, 999, []),
                               (33, 101, ['_NET_WM_WINDOW_TYPE_DOCK']), (44, 201, [])]:
            window = Mock()
            window.get_geometry.return_value = types.SimpleNamespace(width=600, height=400)
            window.get_wm_class.return_value = ('wechat',) if pid == 101 else ('alpha-desktop',)
            window.get_wm_name.return_value = 'Window'
            windows[wid] = window
            properties[wid] = {'_NET_WM_PID': [pid], '_NET_WM_WINDOW_TYPE': kind,
                               '_NET_WM_NAME': b'Title', '_NET_WM_STATE': []}
        root = connection.screen.return_value.root
        for key, window in [('root', root), *windows.items()]:
            window.get_full_property.side_effect = lambda name, _type, key=key: (
                types.SimpleNamespace(value=properties[key][name]) if name in properties[key] else None)
        connection.create_resource_object.side_effect = lambda _kind, wid: windows[wid]
        desktop = control.Desktop(connection, types.SimpleNamespace(AnyPropertyType=0),
                                  types.SimpleNamespace(XError=RuntimeError), Mock(),
                                  lambda app: {101: ('1', True)} if app == 'wechat' else {201: ('2', True)}, {})
        result = desktop.snapshot()
        self.assertEqual([w['id'] for w in result['wechat']], [11])
        self.assertEqual([w['id'] for w in result['alpha']], [44])
        self.assertTrue(result['wechat'][0]['active'])
