"""Independent AT-SPI WeChat driver. No app patching or proprietary offsets."""
import os
import time
from pathlib import Path

class DesktopError(RuntimeError):
    pass

def session_environment():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() != 'openbox' or proc.stat().st_uid != os.getuid():
                continue
            env = dict(x.split('=', 1) for x in (proc / 'environ').read_bytes().decode().split(chr(0)) if '=' in x)
            for key in ['DBUS_SESSION_BUS_ADDRESS', 'DISPLAY', 'XAUTHORITY']:
                if env.get(key):
                    os.environ[key] = env[key]
            return
        except (OSError, ValueError):
            continue

class Desktop:
    def __init__(self):
        session_environment()
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        self.a = Atspi

    def nodes(self):
        root = self.a.get_desktop(0)
        apps = []
        for i in range(root.get_child_count()):
            app = root.get_child_at_index(i)
            if app.get_name().lower() in ['wechat', 'weixin', '微信']:
                apps.append(app)
        if len(apps) != 1:
            raise DesktopError('WECHAT_ACCESSIBILITY_UNAVAILABLE: enable AT-SPI before starting WeChat')
        result, queue = [], [(apps[0], 0)]
        while queue and len(result) < 2000:
            node, depth = queue.pop(0)
            try:
                state = node.get_state_set()
                if state.contains(self.a.StateType.DEFUNCT):
                    continue
                result.append(node)
                if depth < 20:
                    queue.extend((node.get_child_at_index(i), depth + 1) for i in range(min(node.get_child_count(), 500)))
            except Exception:
                continue
        return result

    def inspect(self):
        return [{'role': n.get_role_name(), 'name': n.get_name(),
                 'editable': n.get_state_set().contains(self.a.StateType.EDITABLE),
                 'focused': n.get_state_set().contains(self.a.StateType.FOCUSED)} for n in self.nodes()]

    def _account(self, account):
        accounts = set()
        for proc in Path('/proc').iterdir():
            try:
                if not proc.name.isdigit() or proc.stat().st_uid != os.getuid() or (proc/'comm').read_text().strip().lower() not in ['wechat', 'weixin']:
                    continue
                for fd in (proc/'fd').iterdir():
                    try:
                        path = Path(os.readlink(fd))
                        parts = path.parts
                        if 'db_storage' in parts:
                            accounts.add(parts[parts.index('db_storage')-1])
                    except OSError:
                        continue
            except OSError:
                continue
        if accounts != {account}:
            raise DesktopError('ACTIVE_ACCOUNT_UNVERIFIED: the running WeChat must open this account database')

    def _visible(self, node):
        return node.get_state_set().contains(self.a.StateType.SHOWING)

    def _subtree(self, chat):
        subtree, queue = [], [chat]
        while queue and len(subtree) < 1000:
            n = queue.pop(0); subtree.append(n)
            queue.extend(n.get_child_at_index(i) for i in range(min(n.get_child_count(), 300)))
        return subtree

    def _controls(self, binding):
        self._account(binding['account'])
        nodes = self.nodes()
        editors = [n for n in nodes if n.get_state_set().contains(self.a.StateType.EDITABLE)
                   and n.get_state_set().contains(self.a.StateType.MULTI_LINE)
                   and self._visible(n)]
        sends = [n for n in nodes if n.get_name() in ['发送', 'Send'] and n.get_role_name() in ['button', 'push button'] and self._visible(n)]
        if len(editors) != 1 or len(sends) != 1:
            raise DesktopError('CHAT_CONTROLS_AMBIGUOUS')
        # Use the chat pane containing the editor, not the contact sidebar or
        # invisible cached Qt widgets. DB uniqueness plus visible message
        # fingerprints bind a display name to the exact database username.
        pane = editors[0].get_parent()
        for _ in range(8):
            if pane is None or pane.get_role_name() in ['application', 'frame']:
                break
            subtree = self._subtree(pane)
            names = {n.get_name().strip() for n in subtree if self._visible(n) and n.get_name()}
            title = any(name in names for name in binding['names'])
            identity = any(v and (v in names or '微信号：'+v in names or 'WeChat ID: '+v in names) for v in [binding['username'], binding.get('alias')])
            fingerprints = sum(text in names for text in binding['messages'])
            if sends[0] in subtree and title and (identity or fingerprints >= 2):
                self._foreground(editors[0])
                return editors[0], sends[0]
            pane = pane.get_parent()
        raise DesktopError('CHAT_IDENTITY_UNVERIFIED: open the target chat; a unique contact title and exact ID or two matching recent messages are required')

    def _foreground(self, editor):
        from Xlib import X, display
        d = display.Display()
        try:
            atom = d.intern_atom('_NET_ACTIVE_WINDOW')
            prop = d.screen().root.get_full_property(atom, X.AnyPropertyType)
            if prop is None or not len(prop.value):
                raise DesktopError('WECHAT_NOT_FOREGROUND')
            window = d.create_resource_object('window', int(prop.value[0]))
            pid = window.get_full_property(d.intern_atom('_NET_WM_PID'), X.AnyPropertyType)
            if pid is None or not len(pid.value) or Path('/proc/'+str(int(pid.value[0]))+'/comm').read_text().strip().lower() not in ['wechat', 'weixin']:
                raise DesktopError('WECHAT_NOT_FOREGROUND')
            child = window
            for _ in range(8):
                pointer = child.query_pointer()
                if pointer.mask & (X.Button1Mask | X.Button2Mask | X.Button3Mask | X.ShiftMask | X.ControlMask | X.Mod1Mask):
                    raise DesktopError('MANUAL_INPUT_ACTIVE')
                break
        finally:
            d.close()

    def ready(self, binding):
        editor, _ = self._controls(binding)
        text = editor.get_text_iface()
        if text.get_text(0, -1):
            raise DesktopError('EXISTING_DRAFT: preserve the user draft')
        return True

    def send(self, binding, text, before_click):
        editor, _ = self._controls(binding)
        if editor.get_text_iface().get_text(0, -1):
            raise DesktopError('EXISTING_DRAFT')
        if not editor.get_component_iface().grab_focus():
            raise DesktopError('EDITOR_FOCUS_FAILED')
        editor.get_editable_text_iface().set_text_contents(text)
        editor2, send = self._controls(binding)
        if editor2 != editor or editor.get_text_iface().get_text(0, -1) != text:
            raise DesktopError('CHAT_OR_DRAFT_CHANGED')
        # Persist submitted before any action can reach WeChat. An interrupted
        # click is uncertain and must never be retried automatically.
        before_click()
        action = send.get_action_iface()
        if action and action.get_n_actions() == 1:
            if not action.do_action(0):
                raise DesktopError('SEND_ACTION_UNCERTAIN')
        else:
            from Xlib import X, display
            from Xlib.ext import xtest
            box = send.get_component_iface().get_extents(self.a.CoordType.SCREEN)
            if box.width <= 0 or box.height <= 0:
                raise DesktopError('SEND_BOUNDS_INVALID')
            d = display.Display()
            try:
                xtest.fake_input(d, X.MotionNotify, x=box.x + box.width // 2, y=box.y + box.height // 2)
                xtest.fake_input(d, X.ButtonPress, 1); xtest.fake_input(d, X.ButtonRelease, 1); d.sync()
            finally:
                d.close()
        return {'submitted': True}
