"""Independent AT-SPI WeChat driver. No app patching or proprietary offsets."""
import os
import json
import subprocess
import time
from pathlib import Path

RECOVERY = {
    'ACTION_EXPIRED': ('操作已过期', '核对当前会话后重新准备需要执行的操作。', False),
    'WECHAT_ACCESSIBILITY_UNAVAILABLE': ('微信辅助功能不可用', '启动微信并确认已启用辅助功能。', False),
    'ACTIVE_ACCOUNT_UNVERIFIED': ('微信账号未就绪', '登录与请求匹配的本地微信账号。', True),
    'CHAT_IDENTITY_UNAVAILABLE': ('无法核验当前会话', '确认微信已解锁；不支持的版本布局需更新驱动。', False),
    'CHAT_IDENTITY_UNVERIFIED': ('当前聊天与目标不匹配', '使用打开聊天操作重新定位并核验目标。', True),
    'WECHAT_NOT_FOREGROUND': ('微信不在前台', '切回微信桌面后重试。', True),
    'WECHAT_WINDOW_UNVERIFIED': ('微信窗口不唯一或不可见', '恢复微信主窗口并关闭额外窗口后重试。', True),
    'WECHAT_LOCKED': ('微信已锁定', '手动解锁微信后重试。', True),
    'WECHAT_LOGIN_REQUIRED': ('微信尚未登录', '在微信中完成登录或手机确认后重试。', True),
    'WECHAT_DIALOG_OPEN': ('微信存在弹窗或菜单', '手动处理弹窗或关闭菜单后重试。', True),
    'EXISTING_DRAFT': ('聊天中有未发送草稿', '先发送或自行保存、清空草稿；系统不会覆盖它。', True),
    'MANUAL_INPUT_ACTIVE': ('检测到键鼠操作', '松开按键并暂停手动操作后重试。', True),
    'SEARCH_INPUT_BUSY': ('微信搜索框正在使用', '先结束或清空当前搜索后重试。', True),
    'SEARCH_INPUT_CHANGED': ('搜索内容被改动', '结束手动操作并清空搜索后重试。', True),
    'CHAT_SEARCH_UNAVAILABLE': ('找不到唯一的联系人搜索框', '切回微信聊天主界面后重试。', True),
    'CHAT_TARGET_NOT_FOUND': ('没有找到可核验的目标聊天', '确认联系人存在，或手动打开准确的目标聊天。', True),
    'CHAT_SEARCH_AMBIGUOUS': ('搜索结果过多，无法准确定位', '手动打开目标聊天后重试。', True),
    'CHAT_NAVIGATION_TIMEOUT': ('定位聊天超时', '确认微信响应正常后重试。', True),
    'LOCAL_READER_UNAVAILABLE': ('本地消息服务暂不可用', '等待本地消息服务恢复后重试。', True),
    'SEND_VISUAL_UNVERIFIED': ('无法核验发送按钮', '检查窗口、主题和微信版本；不要重复提交结果不确定的消息。', False),
}


class DesktopError(RuntimeError):
    def __init__(self, message, *, retry_safe=True):
        super().__init__(message)
        self.retry_safe = retry_safe

    @property
    def code(self):
        return str(self).split(':', 1)[0]

    def public(self):
        message, recovery, retryable = RECOVERY.get(self.code,
            ('微信操作检查未通过', '检查微信窗口与操作记录后再决定下一步。', False))
        return {'code': self.code, 'message': message, 'recovery': recovery,
                'retryable': retryable and self.retry_safe}

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

    def _identity(self, binding):
        try:
            result = subprocess.run(
                ['sudo', '-n', '/usr/local/bin/weharbor-capture-key'],
                input=json.dumps({'mode': 'session', 'account': binding['account']}),
                text=True, capture_output=True, check=True, timeout=20)
            evidence = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            raise DesktopError('CHAT_IDENTITY_UNAVAILABLE: current-session memory could not be verified') from None
        if (not isinstance(evidence, dict) or evidence.get('verified') is not True or evidence.get('account') != binding['account']
                or evidence.get('username') != binding['username']):
            raise DesktopError('CHAT_IDENTITY_UNVERIFIED: unlock WeChat and open the exact target chat')

    def _controls(self, binding, require_send=False):
        self._account(binding['account'])
        nodes = self.nodes()
        editors = [n for n in nodes if n.get_state_set().contains(self.a.StateType.EDITABLE)
                   and n.get_state_set().contains(self.a.StateType.MULTI_LINE)
                   and self._visible(n)]
        sends = [n for n in nodes if n.get_name() in ['发送', 'Send'] and n.get_role_name() in ['button', 'push button'] and self._visible(n)]
        self._identity(binding)
        # Use the chat pane containing the editor, not the contact sidebar or
        # invisible cached Qt widgets. The read-only Qt session identity must
        # match the exact account/username as well as a unique visible DB title.
        matches = []
        for editor in editors:
            pane = editor.get_parent()
            for _ in range(8):
                if pane is None or pane.get_role_name() in ['application', 'frame']:
                    break
                subtree = self._subtree(pane)
                names = {n.get_name().strip() for n in subtree if self._visible(n) and n.get_name()}
                title = any(name in names for name in binding['names'])
                pane_editors = [n for n in editors if n in subtree]
                pane_sends = [n for n in sends if n in subtree]
                # Qt marks the search box MULTI_LINE too, and omits the disabled
                # Send control while the composer is empty. A unique editor in
                # the titled chat pane plus its composer toolbar is required.
                toolbar = {'发送收藏', '发送文件'} <= names or {'Send Favorites', 'Send File'} <= names
                if title and len(pane_editors) == 1 and (len(pane_sends) == 1 or (not require_send and not pane_sends and toolbar)):
                    matches.append((editor, pane_sends[0] if pane_sends else None))
                    break
                if title and len(pane_editors) == 1 and not pane_sends and toolbar and require_send:
                    self._foreground(editor)
                    try:
                        from visual_send import find_send
                        matches.append((editor, find_send(self, editor, pane)))
                    except Exception:
                        raise DesktopError('SEND_VISUAL_UNVERIFIED: no unique visible Send button') from None
                    break
                pane = pane.get_parent()
        if len(matches) == 1:
            self._foreground(matches[0][0])
            return matches[0]
        raise DesktopError('CHAT_IDENTITY_UNVERIFIED: the verified session needs its unique contact title in the visible chat pane')

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
            if any(d.query_keymap()):
                raise DesktopError('MANUAL_INPUT_ACTIVE')
        finally:
            d.close()

    def status(self, binding=None):
        try:
            from desktop_navigation import guard, search_control
            nodes = self.nodes()
            main = guard(self, nodes)
            self._foreground(main)
            search_control(self, nodes)
            if binding:
                self._account(binding['account'])
                self.ready(binding)
            return {'state': 'ready', 'code': 'READY', 'message': '微信桌面就绪',
                    'recovery': '', 'retryable': False, 'chat_verified': binding is not None}
        except DesktopError as exc:
            return {'state': 'blocked', 'chat_verified': False, **exc.public()}

    def open_chat(self, binding):
        from desktop_navigation import open_chat
        return open_chat(self, binding)

    def ready(self, binding):
        editor, _ = self._controls(binding)
        if self.a.Text.get_text(editor, 0, -1):
            raise DesktopError('EXISTING_DRAFT: preserve the user draft')
        return True

    def send(self, binding, text, before_click):
        self.open_chat(binding)
        editor, _ = self._controls(binding)
        if self.a.Text.get_text(editor, 0, -1):
            raise DesktopError('EXISTING_DRAFT')
        if not self.a.Component.grab_focus(editor):
            raise DesktopError('EDITOR_FOCUS_FAILED')
        self._not_expired(binding)
        try:
            return self._submit(editor, binding, text, before_click)
        except DesktopError as exc:
            # Once any editor write was attempted, preserve the draft and
            # require inspection. A transient UI fault cannot authorize retry.
            exc.retry_safe = False
            raise

    def _not_expired(self, binding):
        if binding.get('expires_at') is not None and time.time() > binding['expires_at']:
            raise DesktopError('ACTION_EXPIRED', retry_safe=False)

    def _submit(self, editor, binding, text, before_click):
        if not self.a.EditableText.set_text_contents(editor, text):
            raise DesktopError('EDITOR_WRITE_FAILED')
        editor2, send = self._controls(binding, require_send=True)
        if editor2 != editor or self.a.Text.get_text(editor, 0, -1) != text:
            raise DesktopError('CHAT_OR_DRAFT_CHANGED')
        self._not_expired(binding)
        # Persist submitted before any action can reach WeChat. An interrupted
        # click is uncertain and must never be retried automatically.
        before_click()
        from visual_send import VisualSend, click_send
        if isinstance(send, VisualSend):
            self._foreground(editor)
            click_send(send)
            return {'submitted': True}
        action = send.get_action_iface()
        if action and self.a.Action.get_n_actions(send) == 1:
            if not self.a.Action.do_action(send, 0):
                raise DesktopError('SEND_ACTION_UNCERTAIN')
        else:
            from Xlib import X, display
            from Xlib.ext import xtest
            box = self.a.Component.get_extents(send, self.a.CoordType.SCREEN)
            if box.width <= 0 or box.height <= 0:
                raise DesktopError('SEND_BOUNDS_INVALID')
            d = display.Display()
            try:
                xtest.fake_input(d, X.MotionNotify, x=box.x + box.width // 2, y=box.y + box.height // 2)
                xtest.fake_input(d, X.ButtonPress, 1); xtest.fake_input(d, X.ButtonRelease, 1); d.sync()
            finally:
                d.close()
        return {'submitted': True}
