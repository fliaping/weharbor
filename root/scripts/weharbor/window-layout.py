#!/usr/bin/env python3
"""Apply WeHarbor's initial X11 window layout, without policing user changes."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

from Xlib import X, Xutil, display, error
from Xlib.protocol import event

CONFIG = Path('/config/.config/openbox/rc.xml')
RULE_START = ' WeHarbor window defaults: begin '
RULE_END = ' WeHarbor window defaults: end '


def configure_openbox(config=CONFIG):
    if not config.exists():
        return
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(config, parser=parser)
    root = tree.getroot()
    namespace = root.tag.partition('}')[0].lstrip('{') if '}' in root.tag else ''
    if namespace:
        ET.register_namespace('', namespace)
    def tag(name):
        return '{' + namespace + '}' + name if namespace else name
    groups = root.findall(tag('applications'))
    group = groups[-1] if groups else ET.SubElement(root, tag('applications'))
    # Replace only our marked block. Keep unrelated rules, bindings and
    # desktop preferences, including user-defined WeChat/WeFlow rules.
    for existing in groups:
        managed = False
        for rule in list(existing):
            if rule.tag is ET.Comment and rule.text == RULE_START:
                managed = True
            if managed:
                existing.remove(rule)
            if rule.tag is ET.Comment and rule.text == RULE_END:
                managed = False
    group.append(ET.Comment(RULE_START))
    # Override the upstream wildcard maximize rule for all WeChat windows.
    # The helper below maximizes only the identified main window once.
    wechat = ET.SubElement(group, tag('application'), {'class': 'wechat'})
    for name, value in [('focus', 'yes'), ('maximized', 'no')]:
        ET.SubElement(wechat, tag(name)).text = value
    # Restrict to the main WeFlow window; leave settings and dialogs usable.
    weflow = ET.SubElement(group, tag('application'),
                          {'class': 'weflow', 'title': 'WeFlow', 'type': 'normal'})
    ET.SubElement(weflow, tag('focus')).text = 'no'
    ET.SubElement(weflow, tag('iconic')).text = 'yes'
    group.append(ET.Comment(RULE_END))
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    temporary = config.with_suffix('.xml.weharbor-pending')
    temporary.write_bytes(data)
    os.chmod(temporary, config.stat().st_mode & 0o777)
    os.replace(temporary, config)
    subprocess.run(['openbox', '--reconfigure'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Layout:
    def __init__(self):
        self.d = display.Display()
        self.root = self.d.screen().root
        self.states = {}
        self.focus_at = None
        self.main_windows = {}

    def atom(self, name):
        return self.d.intern_atom(name)

    def property(self, window, name):
        return window.get_full_property(self.atom(name), X.AnyPropertyType)

    def send(self, window, kind, data):
        self.root.send_event(event.ClientMessage(
            window=window, client_type=self.atom(kind), data=(32, data)),
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.d.flush()

    def activate(self, window):
        # The layout helper is a pager: request activation without synthetic keys.
        self.send(window, '_NET_ACTIVE_WINDOW', [2, X.CurrentTime, 0, 0, 0])

    def maximize(self, window):
        self.send(window, '_NET_WM_STATE',
                  [1, self.atom('_NET_WM_STATE_MAXIMIZED_VERT'),
                   self.atom('_NET_WM_STATE_MAXIMIZED_HORZ'), 2, 0])

    def normal(self, window):
        kinds = self.property(window, '_NET_WM_WINDOW_TYPE')
        return (not kinds or self.atom('_NET_WM_WINDOW_TYPE_NORMAL') in kinds.value) \
            and window.get_wm_transient_for() is None

    def is_main(self, window):
        # Resizable child windows can be large and non-transient too. Require
        # the application title before considering size or maximize support.
        title = self.property(window, '_NET_WM_NAME')
        name = title.value if title is not None else window.get_wm_name()
        if isinstance(name, bytes):
            name = name.decode('utf-8', errors='replace')
        if name not in {'微信', 'WeChat', 'Weixin'}:
            return False
        # Native login windows have a fixed size. The chat main window is
        # resizable and advertises both maximize operations to the WM.
        hints = window.get_wm_normal_hints()
        if hints and hints.flags & Xutil.PMinSize and hints.flags & Xutil.PMaxSize:
            if hints.min_width == hints.max_width and hints.min_height == hints.max_height:
                return False
        actions = self.property(window, '_NET_WM_ALLOWED_ACTIONS')
        if not actions:
            return False
        if not all(self.atom(name) in actions.value for name in
                   ['_NET_WM_ACTION_MAXIMIZE_HORZ', '_NET_WM_ACTION_MAXIMIZE_VERT']):
            return False
        size = window.get_geometry()
        # Reject small utility windows that some versions expose as normal.
        return size.width >= 600 and size.height >= 450

    def claim_main(self, window):
        if not self.is_main(window):
            return False
        pid = self.property(window, '_NET_WM_PID')
        if pid is None or not len(pid.value):
            return False
        key = int(pid.value[0])
        # Keep this binding while the main window is alive, including after
        # the user manually restores it. Later windows cannot take its place.
        return self.main_windows.setdefault(key, window.id) == window.id

    def tick(self):
        prop = self.property(self.root, '_NET_CLIENT_LIST')
        clients = [int(i) for i in prop.value] if prop else []
        live = set(clients)
        self.main_windows = {pid: wid for pid, wid in self.main_windows.items()
                             if wid in live}
        now = time.monotonic()
        wechat = []
        for wid in clients:
            window = self.d.create_resource_object('window', wid)
            try:
                if not self.normal(window):
                    continue
                classes = tuple((x or '').lower() for x in (window.get_wm_class() or ()))
                state = self.states.setdefault(wid, {'seen': now, 'minimized': False,
                                                     'focused': False, 'maximized': False})
                if 'weflow' in classes:
                    title = self.property(window, '_NET_WM_NAME')
                    name = title.value.decode('utf-8', errors='replace') if title else window.get_wm_name()
                    if name == 'WeFlow' and not state['minimized']:
                        self.send(window, 'WM_CHANGE_STATE', [Xutil.IconicState, 0, 0, 0, 0])
                        state['minimized'] = True
                        self.focus_at = now + 0.3
                        print('WeFlow initial window minimized', flush=True)
                elif 'wechat' in classes:
                    wechat.append(window)
                    if not state['focused']:
                        self.activate(window)
                        state['focused'] = True
                        print('WeChat initial window focused', flush=True)
                    if now - state['seen'] >= 1.0 and not state['maximized'] and self.claim_main(window):
                        self.maximize(window)
                        self.activate(window)
                        state['maximized'] = True
                        print('WeChat resizable main window maximized', flush=True)
            except (error.BadWindow, error.BadDrawable):
                continue
        if self.focus_at is not None and now >= self.focus_at:
            if wechat:
                self.activate(wechat[-1])
            self.focus_at = None
        self.states = {wid: state for wid, state in self.states.items() if wid in live}
        self.d.sync()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if args.configure:
        configure_openbox()
        return
    name = os.environ.get('DISPLAY', ':1').replace('/', '_').replace(':', '_')
    lock = open('/tmp/weharbor-window-layout-' + name + '.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    layout = Layout()
    if args.once:
        layout.tick()
        time.sleep(1.2)
        layout.tick()
        return
    while True:
        layout.tick()
        time.sleep(0.5)


if __name__ == '__main__':
    main()
