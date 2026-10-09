import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

# No X server is needed for policy tests; the image smoke test uses real Xlib.
class BadWindow(Exception):
    pass

xlib = SimpleNamespace(X=SimpleNamespace(AnyPropertyType=0),
                       Xutil=SimpleNamespace(PMinSize=1, PMaxSize=2, IconicState=3),
                       display=SimpleNamespace(),
                       error=SimpleNamespace(BadWindow=BadWindow, BadDrawable=BadWindow))
spec = importlib.util.spec_from_file_location('window_layout', ROOT / 'root/scripts/weharbor/window-layout.py')
layout_module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'Xlib': xlib, 'Xlib.protocol': SimpleNamespace(event=SimpleNamespace())}):
    spec.loader.exec_module(layout_module)


class Window:
    def __init__(self, wid, title='微信', pid=100, app='wechat', fixed=False, transient=None):
        self.id, self.title, self.pid, self.app = wid, title, pid, app
        self.fixed, self.transient = fixed, transient
        self.width, self.height = 1000, 900
        self.actions = ['_NET_WM_ACTION_MAXIMIZE_HORZ', '_NET_WM_ACTION_MAXIMIZE_VERT']

    def get_wm_name(self):
        return self.title

    def get_wm_class(self):
        return (self.app, self.app)

    def get_wm_transient_for(self):
        return self.transient

    def get_wm_normal_hints(self):
        return SimpleNamespace(flags=3, min_width=300, min_height=300,
                               max_width=300 if self.fixed else 2400,
                               max_height=300 if self.fixed else 1800)

    def get_geometry(self):
        return SimpleNamespace(width=self.width, height=self.height)


class WindowLayoutTests(unittest.TestCase):
    def setUp(self):
        self.windows = {}
        self.layout = layout_module.Layout.__new__(layout_module.Layout)
        self.layout.states, self.layout.main_windows = {}, {}
        self.layout.focus_at = None
        self.layout.root = object()
        self.layout.d = SimpleNamespace(create_resource_object=lambda kind, wid: self.windows[wid], sync=Mock())
        self.layout.atom = lambda name: name
        self.layout.property = self.property
        self.layout.send, self.layout.maximize, self.layout.activate = Mock(), Mock(), Mock()

    def property(self, window, name):
        if window is self.layout.root:
            return SimpleNamespace(value=list(self.windows))
        values = {'_NET_WM_NAME': window.title.encode(), '_NET_WM_PID': [window.pid] if window.pid else [],
                  '_NET_WM_ALLOWED_ACTIONS': window.actions, '_NET_WM_WINDOW_TYPE': ['_NET_WM_WINDOW_TYPE_NORMAL']}
        return SimpleNamespace(value=values[name])

    def tick(self, now):
        with patch.object(layout_module.time, 'monotonic', return_value=now):
            self.layout.tick()

    def test_login_becomes_main_once_and_manual_restore_is_respected(self):
        main = self.windows[1] = Window(1, fixed=True)
        self.tick(0)
        self.tick(2)
        self.layout.maximize.assert_not_called()
        main.fixed = False
        self.tick(3)
        self.layout.maximize.assert_called_once_with(main)
        self.tick(10)
        self.layout.maximize.assert_called_once_with(main)

    def test_large_and_same_title_children_cannot_replace_main(self):
        main = self.windows[1] = Window(1)
        self.tick(0)
        self.tick(2)
        self.windows[2] = Window(2, title='聊天详情')
        self.windows[3] = Window(3)
        self.windows[4] = Window(4, title='设置')
        self.tick(3)
        self.tick(5)
        self.layout.maximize.assert_called_once_with(main)
        self.assertEqual(self.layout.main_windows, {100: 1})

    def test_transient_small_fixed_or_unidentified_windows_are_rejected(self):
        self.windows[1] = Window(1, transient=object())
        self.windows[2] = Window(2, fixed=True)
        self.windows[3] = Window(3, pid=None)
        self.windows[4] = Window(4)
        self.windows[4].width = 300
        self.tick(0)
        self.tick(2)
        self.layout.maximize.assert_not_called()

    def test_closed_main_and_restarted_process_are_recognized(self):
        self.windows[1] = Window(1)
        self.tick(0)
        self.tick(2)
        self.windows.clear()
        self.tick(3)
        self.assertEqual(self.layout.main_windows, {})
        main = self.windows[2] = Window(2, pid=200, title='WeChat')
        self.tick(4)
        self.tick(6)
        self.assertEqual(self.layout.maximize.call_count, 2)
        self.layout.maximize.assert_called_with(main)

    def test_weflow_minimized_once_and_its_dialog_is_untouched(self):
        self.windows[1] = Window(1, app='weflow', title='WeFlow')
        self.windows[2] = Window(2, app='weflow', title='Settings')
        self.tick(0)
        self.tick(2)
        self.assertEqual(self.layout.send.call_count, 1)
        self.assertEqual(self.layout.send.call_args.args[0].id, 1)
        self.layout.maximize.assert_not_called()

    def test_openbox_migration_keeps_user_rules_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / 'rc.xml'
            config.write_text('<openbox_config xmlns="http://openbox.org/3.4/rc">'
                              '<keyboard><keybind key="A-F4"/></keyboard><applications>'
                              '<!-- user preference --><application class="*"><maximized>yes</maximized></application>'
                              '<application class="wechat" type="normal"><decor>no</decor></application>'
                              '</applications><applications><application class="weflow" title="Settings">'
                              '<layer>above</layer></application></applications></openbox_config>')
            config.chmod(0o640)
            original = ET.parse(config).getroot()
            user_rules = original.findall('.//{*}application')
            with patch.object(layout_module.subprocess, 'run') as reconfigure:
                layout_module.configure_openbox(config)
                first = config.read_bytes()
                layout_module.configure_openbox(config)
                self.assertEqual(config.read_bytes(), first)
                self.assertEqual(reconfigure.call_count, 2)
            root = ET.parse(config).getroot()
            rules = root.findall('.//{*}application')
            self.assertEqual([ET.tostring(r) for r in rules[:3]], [ET.tostring(r) for r in user_rules])
            self.assertIsNotNone(root.find('.//{*}keybind'))
            self.assertIn(b'user preference', first)
            self.assertEqual(config.stat().st_mode & 0o777, 0o640)
            wechat, weflow = rules[-2:]
            self.assertEqual(wechat.get('class'), 'wechat')
            self.assertEqual(wechat.find('{*}maximized').text, 'no')
            self.assertEqual(weflow.attrib, {'class': 'weflow', 'title': 'WeFlow', 'type': 'normal'})
            self.assertEqual(weflow.find('{*}iconic').text, 'yes')
