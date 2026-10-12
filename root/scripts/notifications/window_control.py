"""EWMH window selection for the web dock; never create an X11 panel."""
from contextlib import contextmanager
import threading


class WindowController:
    def __init__(self, processes):
        self.processes = processes
        self.last_active = {}
        self.lock = threading.Lock()

    @contextmanager
    def session(self):
        # Xlib connections are not shared between HTTP executor threads.
        from Xlib import X, display, error, protocol
        with self.lock:
            connection = display.Display()
            try:
                yield Desktop(connection, X, error, protocol, self.processes, self.last_active)
            finally:
                connection.close()

    def snapshot(self):
        with self.session() as desktop:
            return desktop.snapshot()

    def activate(self, app, window_id=None):
        with self.session() as desktop:
            return desktop.activate(app, window_id)


class Desktop:
    def __init__(self, connection, x, error, protocol, processes, remembered):
        self.connection, self.x, self.error, self.protocol = connection, x, error, protocol
        self.root = connection.screen().root
        self.processes, self.remembered = processes, remembered

    def atom(self, name):
        return self.connection.intern_atom(name)

    def values(self, window, name):
        value = window.get_full_property(self.atom(name), self.x.AnyPropertyType)
        return value.value if value is not None else []

    def snapshot(self):
        owners = {pid: app for app in ('wechat', 'weflow') for pid in self.processes(app)}
        active = self.values(self.root, '_NET_ACTIVE_WINDOW')
        active_id = int(active[0]) if len(active) else None
        clients = self.values(self.root, '_NET_CLIENT_LIST')
        result = {'wechat': [], 'weflow': []}
        for wid in clients:
            try:
                window = self.connection.create_resource_object('window', int(wid))
                pids = self.values(window, '_NET_WM_PID')
                app = owners.get(int(pids[0])) if len(pids) else None
                if app is None:
                    continue
                geometry = window.get_geometry()
                if geometry.width < 160 or geometry.height < 100:
                    continue
                types = self.values(window, '_NET_WM_WINDOW_TYPE')
                if any(self.atom(name) in types for name in (
                        '_NET_WM_WINDOW_TYPE_DOCK', '_NET_WM_WINDOW_TYPE_DESKTOP',
                        '_NET_WM_WINDOW_TYPE_TOOLTIP', '_NET_WM_WINDOW_TYPE_NOTIFICATION')):
                    continue
                title = self.values(window, '_NET_WM_NAME')
                title = bytes(title).decode('utf-8', errors='replace').strip(chr(0)) if len(title) else ''
                title = title or str(window.get_wm_name() or '') or ('微信' if app == 'wechat' else 'WeFlow')
                classes = {str(value).lower() for value in (window.get_wm_class() or ())}
                states = self.values(window, '_NET_WM_STATE')
                result[app].append({'id': int(wid), 'title': title[:200],
                                    'active': int(wid) == active_id,
                                    'minimized': self.atom('_NET_WM_STATE_HIDDEN') in states,
                                    'primary': app in classes})
                if int(wid) == active_id:
                    self.remembered[app] = int(wid)
            except (self.error.XError, OSError, ValueError, TypeError, UnicodeError):
                continue
        for windows in result.values():
            windows.sort(key=lambda item: (not item['primary'], item['id']))
        return result

    def send(self, window, name, values):
        message = self.protocol.event.ClientMessage(
            window=window, client_type=self.atom(name), data=(32, values))
        self.root.send_event(message, event_mask=(self.x.SubstructureRedirectMask |
                                                 self.x.SubstructureNotifyMask))

    def activate(self, app, window_id=None):
        snapshot = self.snapshot()
        windows = snapshot[app]
        ids = [window['id'] for window in windows]
        if window_id is not None:
            if window_id not in ids:
                raise ValueError('Window is closed or does not belong to this application')
            target = window_id
        elif not windows:
            return None
        else:
            active = next((window['id'] for window in windows if window['active']), None)
            if active is not None and len(ids) > 1:
                target = ids[(ids.index(active) + 1) % len(ids)]
            else:
                target = self.remembered.get(app)
                if target not in ids:
                    target = ids[0]
        # Preserve the desktop switcher's explicit minimize-other-app behavior.
        for other_app, other_windows in snapshot.items():
            if other_app == app:
                continue
            for info in other_windows:
                if not info['minimized']:
                    window = self.connection.create_resource_object('window', info['id'])
                    self.send(window, 'WM_CHANGE_STATE', [3, 0, 0, 0, 0])
        window = self.connection.create_resource_object('window', target)
        self.send(window, '_NET_ACTIVE_WINDOW', [2, self.x.CurrentTime, 0, 0, 0])
        self.connection.flush()
        # Complete the request before closing this short-lived X11 connection.
        self.connection.sync()
        self.remembered[app] = target
        return target
