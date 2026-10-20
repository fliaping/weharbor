"""Bounded navigation through WeChat's accessible contact search results."""
import time

from desktop import DesktopError

SEARCH = {'搜索', 'Search'}
SECTIONS = {'联系人', 'Contacts', '群聊', 'Group Chats', 'Groups'}


def text(driver, node):
    return driver.a.Text.get_text(node, 0, -1)


def frame(driver, nodes):
    frames = [n for n in nodes if n.get_role_name() == 'frame' and driver._visible(n)]
    if len(frames) != 1:
        raise DesktopError('WECHAT_WINDOW_UNVERIFIED')
    return frames[0]


def is_search(node):
    return node.get_name().strip() in SEARCH


def guard(driver, nodes, owned_query=None):
    """Never dismiss arbitrary UI or overwrite user input to make progress."""
    for n in nodes:
        if not driver._visible(n):
            continue
        role, name = n.get_role_name(), n.get_name().strip()
        if role in ['dialog', 'alert', 'menu']:
            raise DesktopError('WECHAT_DIALOG_OPEN')
        if role in ['button', 'push button'] and name in ['解锁', 'Unlock']:
            raise DesktopError('WECHAT_LOCKED')
        if role in ['button', 'push button'] and name in ['登录', 'Log In', 'Log in', '登录微信', '进入微信']:
            raise DesktopError('WECHAT_LOGIN_REQUIRED')
        if n.get_state_set().contains(driver.a.StateType.EDITABLE):
            value = text(driver, n)
            if value and (not is_search(n) or value != owned_query):
                raise DesktopError('SEARCH_INPUT_BUSY' if is_search(n) else 'EXISTING_DRAFT')
    return frame(driver, nodes)


def search_control(driver, nodes):
    result = [n for n in nodes if driver._visible(n) and is_search(n)
              and n.get_state_set().contains(driver.a.StateType.EDITABLE)]
    if len(result) != 1:
        raise DesktopError('CHAT_SEARCH_UNAVAILABLE')
    return result[0]


def candidates(driver, nodes, names):
    """Only popup Contacts/Groups rows; never chat-history or message matches."""
    matches = []
    for parent in nodes:
        if parent.get_role_name() != 'list' or not driver._visible(parent):
            continue
        ancestor = parent.get_parent()
        in_frame = False
        while ancestor is not None and ancestor.get_role_name() != 'application':
            if ancestor.get_role_name() == 'frame':
                in_frame = True
                break
            ancestor = ancestor.get_parent()
        if in_frame:
            continue
        header_height = None
        for index in range(min(parent.get_child_count(), 100)):
            child = parent.get_child_at_index(index)
            if not driver._visible(child) or child.get_role_name() != 'list item':
                continue
            label = child.get_name().strip()
            box = driver.a.Component.get_extents(child, driver.a.CoordType.SCREEN)
            if label in SECTIONS:
                header_height = box.height
                continue
            # This Qt search popup uses shorter rows for section headers and
            # history results. A new section must have a recognized heading.
            if header_height is not None and box.height <= header_height * 1.25:
                header_height = None
            if header_height and label in names:
                matches.append(child)
    return matches[:6]


def click_control(driver, node, main):
    """Scale the identified accessible row against a stable active X11 frame."""
    from Xlib import display
    from visual_send import VisualSend, active_window, click_send
    driver._foreground(node)
    bounds = driver.a.Component.get_extents(main, driver.a.CoordType.SCREEN)
    box = driver.a.Component.get_extents(node, driver.a.CoordType.SCREEN)
    connection = display.Display()
    try:
        window, geometry = active_window(connection)
    finally:
        connection.close()
    x, y, width, height = geometry
    sx, sy = width / bounds.width, height / bounds.height
    if not (.5 <= sx <= 4 and abs(sx - sy) < .02 and box.width > 0 and box.height > 0
            and bounds.x <= box.x and bounds.y <= box.y
            and box.x + box.width <= bounds.x + bounds.width
            and box.y + box.height <= bounds.y + bounds.height):
        raise DesktopError('NAVIGATION_BOUNDS_UNVERIFIED')
    target = VisualSend(round(x + (box.x - bounds.x) * sx), round(y + (box.y - bounds.y) * sy),
                        round(box.width * sx), round(box.height * sy), window, geometry)
    driver._foreground(node)
    click_send(target)


def clear_owned_search(driver, query):
    nodes = driver.nodes()
    search = search_control(driver, nodes)
    value = text(driver, search)
    if not value:
        return
    if value != query:
        raise DesktopError('SEARCH_INPUT_CHANGED')
    guard(driver, nodes, query)
    driver._foreground(search)
    if not driver.a.EditableText.set_text_contents(search, ''):
        raise DesktopError('SEARCH_CLEAR_FAILED')


def open_chat(driver, binding):
    driver._account(binding['account'])
    nodes = driver.nodes()
    guard(driver, nodes)
    try:
        driver._controls(binding)
        return {'verified': True, 'navigated': False}
    except DesktopError as exc:
        if exc.code != 'CHAT_IDENTITY_UNVERIFIED':
            raise
    names = set(binding['names']) | {binding['username']}
    if binding.get('alias'):
        names.add(binding['alias'])
    queries = binding.get('search_queries') or binding['names']
    queries = list(dict.fromkeys(q for q in queries if isinstance(q, str) and 0 < len(q) <= 256
                                and not any(ord(c) < 32 for c in q)))[:4]
    if not queries:
        raise DesktopError('CHAT_SEARCH_NAME_UNAVAILABLE')
    deadline = time.monotonic() + 60
    for query in queries:
        attempted = 0
        for ordinal in range(5):
            if time.monotonic() >= deadline:
                raise DesktopError('CHAT_NAVIGATION_TIMEOUT')
            nodes = driver.nodes()
            main = guard(driver, nodes)
            search = search_control(driver, nodes)
            driver._foreground(search)
            if not driver.a.Component.grab_focus(search):
                raise DesktopError('SEARCH_FOCUS_FAILED')
            if not driver.a.EditableText.set_text_contents(search, query):
                raise DesktopError('SEARCH_WRITE_FAILED')
            try:
                if text(driver, search) != query:
                    raise DesktopError('SEARCH_INPUT_CHANGED')
                # Search results are asynchronous. Read twice after a bounded
                # settling interval, and select from the fresh tree only.
                time.sleep(.4)
                until = min(deadline, time.monotonic() + 2)
                found = []
                while time.monotonic() < until:
                    nodes = driver.nodes()
                    main = guard(driver, nodes, query)
                    if text(driver, search_control(driver, nodes)) != query:
                        raise DesktopError('SEARCH_INPUT_CHANGED')
                    found = candidates(driver, nodes, names)
                    if len(found) > ordinal:
                        break
                    time.sleep(.15)
                if len(found) <= ordinal:
                    break
                # A broad ambiguous result set is not permission to browse it.
                if len(found) > 5:
                    raise DesktopError('CHAT_SEARCH_AMBIGUOUS')
                driver._account(binding['account'])
                click_control(driver, found[ordinal], main)
                attempted += 1
                time.sleep(.3)
                clear_owned_search(driver, query)
                try:
                    driver.ready(binding)
                    return {'verified': True, 'navigated': True}
                except DesktopError as exc:
                    if exc.code != 'CHAT_IDENTITY_UNVERIFIED':
                        raise
            finally:
                clear_owned_search(driver, query)
        if not attempted:
            continue
    raise DesktopError('CHAT_TARGET_NOT_FOUND')
