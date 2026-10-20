"""Local OCR for WeChat's painted Send control, scoped to a verified composer."""
import csv
import io
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualSend:
    x: int
    y: int
    width: int
    height: int
    window: int
    geometry: tuple


def send_label(tsv):
    """Accept one complete, confident line; never match '发送文件'."""
    lines = {}
    try:
        for row in csv.DictReader(io.StringIO(tsv), delimiter='	'):
            if row['level'] != '5' or not row['text'].strip():
                continue
            key = tuple(row[k] for k in ['page_num', 'block_num', 'par_num', 'line_num'])
            lines.setdefault(key, []).append((row['text'].strip(), float(row['conf'])))
        matches = [words for words in lines.values()
                   if ''.join(word for word, _ in words) in ['发送', 'Send']
                   and all(conf >= 80 for _, conf in words)]
        return len(matches) == 1 and len(lines) == 1
    except (KeyError, TypeError, ValueError):
        return False


def active_window(connection):
    from Xlib import X
    root = connection.screen().root
    prop = root.get_full_property(connection.intern_atom('_NET_ACTIVE_WINDOW'), X.AnyPropertyType)
    if prop is None or not len(prop.value):
        raise ValueError('No active window')
    window = connection.create_resource_object('window', int(prop.value[0]))
    geometry = window.get_geometry()
    position = root.translate_coords(window, 0, 0)
    return window.id, (position.x, position.y, geometry.width, geometry.height)


def find_send(driver, editor, pane):
    from PIL import Image, ImageGrab, ImageOps
    from Xlib import display
    frame = editor
    while frame is not None and frame.get_role_name() != 'frame':
        frame = frame.get_parent()
    if frame is None:
        raise ValueError('No chat frame')
    bounds = driver.a.Component.get_extents(frame, driver.a.CoordType.SCREEN)
    connection = display.Display()
    try:
        window, geometry = active_window(connection)
    finally:
        connection.close()
    x, y, width, height = geometry
    sx, sy = width / bounds.width, height / bounds.height
    if not (.5 <= sx <= 4 and abs(sx - sy) < .02):
        raise ValueError('Inconsistent desktop scaling')
    eb = driver.a.Component.get_extents(editor, driver.a.CoordType.SCREEN)
    regions = set()
    for toolbar in driver._subtree(pane):
        if toolbar.get_role_name() != 'tool bar' or not driver._visible(toolbar):
            continue
        tb = driver.a.Component.get_extents(toolbar, driver.a.CoordType.SCREEN)
        if tb.y < eb.y + eb.height - 2 or tb.width < eb.width * .8:
            continue
        for node in driver._subtree(toolbar):
            if node.get_role_name() != 'filler' or not driver._visible(node):
                continue
            r = driver.a.Component.get_extents(node, driver.a.CoordType.SCREEN)
            if (20 <= r.width < tb.width / 3 and r.x > tb.x + tb.width * .6
                    and tb.y <= r.y and r.y + r.height <= tb.y + tb.height
                    and r.x + r.width <= tb.x + tb.width):
                regions.add((r.x, r.y, r.width, r.height))
    screenshot = ImageGrab.grab()
    candidates = []
    for rx, ry, rw, rh in regions:
        box = (round(x + (rx - bounds.x) * sx), round(y + (ry - bounds.y) * sy),
               round(x + (rx + rw - bounds.x) * sx), round(y + (ry + rh - bounds.y) * sy))
        if (box[0] < 0 or box[1] < 0 or box[2] > screenshot.width or box[3] > screenshot.height
                or not (0 < box[2] - box[0] <= 1000 and 0 < box[3] - box[1] <= 300)):
            continue
        image = screenshot.crop(box).convert('RGB')
        pixels = image.tobytes()
        mask = Image.new('L', image.size)
        mask.putdata([255 if g > 100 and g > r * 1.3 and g > b * 1.15 else 0
                      for r, g, b in zip(pixels[::3], pixels[1::3], pixels[2::3])])
        green = mask.getbbox()
        if green is None:
            continue
        left, top, right, bottom = green
        bw, bh = right - left, bottom - top
        if not (1.2 <= bw / bh <= 4 and bw >= 30 * sx and bh >= 18 * sy):
            continue
        # Trim rounded corners before thresholding the white button caption.
        inset = max(2, round(4 * sx))
        caption = image.crop((left + inset, top + inset, right - inset, bottom - inset))
        caption = caption.convert('L').point(lambda p: 0 if p > 210 else 255)
        caption = ImageOps.expand(caption, border=12, fill=255)
        caption = caption.resize((caption.width * 2, caption.height * 2))
        encoded = io.BytesIO()
        caption.save(encoded, format='PNG')
        result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'chi_sim+eng', '--psm', '6', 'tsv'],
                                input=encoded.getvalue(), capture_output=True, check=True, timeout=5)
        if send_label(result.stdout.decode()):
            candidates.append(VisualSend(box[0] + left, box[1] + top, bw, bh, window, geometry))
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        raise ValueError('No unique visible Send caption')
    return candidates[0]


def click_send(target):
    from Xlib import X, display
    from Xlib.ext import xtest
    connection = display.Display()
    try:
        if active_window(connection) != (target.window, target.geometry):
            raise ValueError('Chat window moved or changed')
        xtest.fake_input(connection, X.MotionNotify, x=target.x + target.width // 2, y=target.y + target.height // 2)
        xtest.fake_input(connection, X.ButtonPress, 1)
        xtest.fake_input(connection, X.ButtonRelease, 1)
        connection.sync()
    finally:
        connection.close()
