#!/lsiopy/bin/python3
"""Tiny X11 task switcher for the WeChat + WeFlow Selkies desktop.

This intentionally uses only python-xlib, which is already present in the
upstream image. It is a draggable floating window, not a desktop panel.
"""

import json
import os
import select
import subprocess
import sys
import time

from Xlib import X, Xatom, display, error, protocol

sys.path.insert(0, "/scripts/notifications")
from notification_config import load_settings, save_settings


PANEL_HEIGHT = 44
PANEL_WIDTH = 354
DRAG_HANDLE_WIDTH = 36
TRAY_GAP = 4
TRAY_DEFAULT_WIDTH = 40
BUTTON_WIDTH = 132
BUTTON_HEIGHT = 34
BUTTON_GAP = 8
NOTIFICATION_BUTTON_WIDTH = 28
NOTIFICATION_BUTTON_GAP = 4
NOTIFICATION_MENU_WIDTH = 142
NOTIFICATION_MENU_HEIGHT = 92
NOTIFICATION_MENU_ROW_HEIGHT = 28
NOTIFICATION_MENU_TIMEOUT = 10
CONTEXT_MENU_WIDTH = 320
CONTEXT_MENU_MAX_ROWS = 7
CONTEXT_MENU_ROW_HEIGHT = 28
CONTEXT_MENU_MAX_HEIGHT = (
    8 + CONTEXT_MENU_MAX_ROWS * CONTEXT_MENU_ROW_HEIGHT
)
AUTO_HIDE_DELAY_SECONDS = 1.2
PANEL_OPACITY = 0.92
POLL_SECONDS = 0.5
RAISE_INTERVAL_SECONDS = 1.0
POSITION_FILE = "/config/.config/weflow/app-switcher-position"
SWITCHER_SETTINGS_FILE = (
    "/config/.config/weflow/app-switcher-settings.json"
)

APPS = (
    {
        "label": "WeChat",
        "classes": {"wechat", "wechatappex"},
        "primary_classes": {"wechat"},
        "process_names": {"wechat", "wechatappex"},
        "executable_prefixes": ("/usr/bin/wechat", "/opt/wechat/"),
        "command": ["/scripts/wechat/wechat-start.sh"],
    },
    {
        "label": "WeFlow",
        "classes": {"weflow"},
        "primary_classes": {"weflow"},
        "process_names": {"weflow"},
        "executable_prefixes": ("/opt/weflow/",),
        "command": ["/scripts/weflow/weflow-start.sh"],
    },
)


class AppSwitcher:
    def __init__(self):
        self.display = display.Display()
        self.screen = self.display.screen()
        self.root = self.screen.root
        self.atoms = {
            name: self.display.intern_atom(name)
            for name in (
                "_NET_ACTIVE_WINDOW",
                "_NET_CLIENT_LIST",
                "_NET_CLIENT_LIST_STACKING",
                "_NET_WM_NAME",
                "_NET_WM_PID",
                "_NET_WM_STATE",
                "_NET_WM_STATE_ABOVE",
                "_NET_WM_STATE_HIDDEN",
                "_NET_WM_STATE_STICKY",
                "_NET_WM_STATE_SKIP_TASKBAR",
                "_NET_WM_STATE_SKIP_PAGER",
                "_NET_WM_WINDOW_TYPE",
                "_NET_WM_WINDOW_TYPE_DOCK",
                "_NET_WM_WINDOW_OPACITY",
                "WM_CHANGE_STATE",
            )
        }
        self.colors = {
            "panel": self.color("#171a20"),
            "button": self.color("#292e38"),
            "active": self.color("#1677ff"),
            "hover": self.color("#374151"),
            "text": self.color("#f8fafc"),
            "available": self.color("#43cf7c"),
            "unavailable": self.color("#94a3b8"),
            "disabled": self.color("#64748b"),
        }
        self.button_rects = []
        self.notification_rect = None
        self.hovered = None
        self.menu_hovered = None
        self.notification_menu_open = False
        self.notification_menu_last_interaction = 0.0
        self.context_menu_open = False
        self.context_menu_mode = None
        self.context_menu_app_index = None
        self.context_menu_entries = []
        self.context_menu_hovered = None
        self.context_menu_height = 0
        self.context_menu_last_interaction = 0.0
        self.last_active_by_app = {}
        self.last_launch_attempt = {}
        self.pending_activation_id = None
        self.pending_activation_deadline = 0.0
        self.process_info_cache = {}
        self.auto_hide_enabled = self.load_switcher_settings()[
            "auto_hide"
        ]
        self.auto_hide_deadline = None
        self.collapsed = False
        self.last_raise = 0.0
        self.drag_origin = None
        self.dragging = False
        self.tray_width = TRAY_DEFAULT_WIDTH
        self.tray_height = TRAY_DEFAULT_WIDTH
        self.tray_window = None
        self.tray_frame = None
        self.tray_inset_x = 0
        self.tray_inset_y = 0
        self.last_tray_refresh = 0.0
        self.last_visual_state = None
        self.last_managed_state = None
        root_geometry = self.root.get_geometry()
        self.last_screen_size = (root_geometry.width, root_geometry.height)
        self.preferred_x, self.preferred_y = self.load_position()
        self.panel_x, self.panel_y = self.clamp_position(
            self.preferred_x, self.preferred_y
        )

        self.window = self.create_panel()
        self.notification_menu = self.create_notification_menu()
        self.context_menu = self.create_context_menu()
        self.buffer = self.window.create_pixmap(
            PANEL_WIDTH, PANEL_HEIGHT, self.screen.root_depth
        )
        self.notification_menu_buffer = self.notification_menu.create_pixmap(
            NOTIFICATION_MENU_WIDTH,
            NOTIFICATION_MENU_HEIGHT,
            self.screen.root_depth,
        )
        self.context_menu_buffer = self.context_menu.create_pixmap(
            CONTEXT_MENU_WIDTH,
            CONTEXT_MENU_MAX_HEIGHT,
            self.screen.root_depth,
        )
        self.font = self.display.open_font("fixed")
        self.text_gc = self.window.create_gc(
            foreground=self.colors["text"],
            background=self.colors["panel"],
            font=self.font,
        )
        self.panel_gc = self.window.create_gc(foreground=self.colors["panel"])
        self.button_gc = self.window.create_gc(foreground=self.colors["button"])
        self.available_gc = self.window.create_gc(
            foreground=self.colors["available"]
        )
        self.unavailable_gc = self.window.create_gc(
            foreground=self.colors["unavailable"]
        )
        self.active_gc = self.window.create_gc(foreground=self.colors["active"])
        self.hover_gc = self.window.create_gc(foreground=self.colors["hover"])
        self.disabled_gc = self.window.create_gc(
            foreground=self.colors["disabled"]
        )
        self.copy_gc = self.window.create_gc()

        self.root.change_attributes(event_mask=X.PropertyChangeMask)
        self.window.map()
        self.display.flush()

    def color(self, value):
        return self.screen.default_colormap.alloc_named_color(value).pixel

    def set_window_opacity(self, window):
        opacity = max(
            0,
            min(0xFFFFFFFF, int(PANEL_OPACITY * 0xFFFFFFFF)),
        )
        window.change_property(
            self.atoms["_NET_WM_WINDOW_OPACITY"],
            Xatom.CARDINAL,
            32,
            [opacity],
        )

    def create_panel(self):
        window = self.root.create_window(
            self.panel_x,
            self.panel_y,
            PANEL_WIDTH,
            PANEL_HEIGHT,
            0,
            self.screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=self.colors["panel"],
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.ButtonReleaseMask
                | X.PointerMotionMask
                | X.EnterWindowMask
                | X.LeaveWindowMask
                | X.StructureNotifyMask
            ),
            override_redirect=True,
        )
        window.set_wm_name("Application Switcher")
        window.set_wm_class("app-switcher", "AppSwitcher")
        window.change_property(
            self.atoms["_NET_WM_WINDOW_TYPE"],
            Xatom.ATOM,
            32,
            [self.atoms["_NET_WM_WINDOW_TYPE_DOCK"]],
        )
        window.change_property(
            self.atoms["_NET_WM_STATE"],
            Xatom.ATOM,
            32,
            [
                self.atoms["_NET_WM_STATE_ABOVE"],
                self.atoms["_NET_WM_STATE_STICKY"],
                self.atoms["_NET_WM_STATE_SKIP_TASKBAR"],
                self.atoms["_NET_WM_STATE_SKIP_PAGER"],
            ],
        )
        self.set_window_opacity(window)
        return window

    def create_notification_menu(self):
        window = self.root.create_window(
            self.panel_x,
            self.panel_y + PANEL_HEIGHT + 4,
            NOTIFICATION_MENU_WIDTH,
            NOTIFICATION_MENU_HEIGHT,
            0,
            self.screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=self.colors["panel"],
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.PointerMotionMask
                | X.LeaveWindowMask
            ),
            override_redirect=True,
        )
        window.set_wm_name("Notification Controls")
        window.set_wm_class("notification-controls", "AppSwitcher")
        window.change_property(
            self.atoms["_NET_WM_WINDOW_TYPE"],
            Xatom.ATOM,
            32,
            [self.atoms["_NET_WM_WINDOW_TYPE_DOCK"]],
        )
        window.change_property(
            self.atoms["_NET_WM_STATE"],
            Xatom.ATOM,
            32,
            [
                self.atoms["_NET_WM_STATE_ABOVE"],
                self.atoms["_NET_WM_STATE_STICKY"],
                self.atoms["_NET_WM_STATE_SKIP_TASKBAR"],
                self.atoms["_NET_WM_STATE_SKIP_PAGER"],
            ],
        )
        self.set_window_opacity(window)
        return window

    def create_context_menu(self):
        window = self.root.create_window(
            self.panel_x,
            self.panel_y + PANEL_HEIGHT + 4,
            CONTEXT_MENU_WIDTH,
            CONTEXT_MENU_MAX_HEIGHT,
            0,
            self.screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=self.colors["panel"],
            event_mask=(
                X.ExposureMask
                | X.ButtonPressMask
                | X.PointerMotionMask
                | X.EnterWindowMask
                | X.LeaveWindowMask
            ),
            override_redirect=True,
        )
        window.set_wm_name("Application Switcher Menu")
        window.set_wm_class("app-switcher-menu", "AppSwitcher")
        window.change_property(
            self.atoms["_NET_WM_WINDOW_TYPE"],
            Xatom.ATOM,
            32,
            [self.atoms["_NET_WM_WINDOW_TYPE_DOCK"]],
        )
        window.change_property(
            self.atoms["_NET_WM_STATE"],
            Xatom.ATOM,
            32,
            [
                self.atoms["_NET_WM_STATE_ABOVE"],
                self.atoms["_NET_WM_STATE_STICKY"],
                self.atoms["_NET_WM_STATE_SKIP_TASKBAR"],
                self.atoms["_NET_WM_STATE_SKIP_PAGER"],
            ],
        )
        self.set_window_opacity(window)
        return window

    @staticmethod
    def load_switcher_settings():
        settings = {"auto_hide": True}
        try:
            with open(
                SWITCHER_SETTINGS_FILE, "r", encoding="utf-8"
            ) as settings_file:
                loaded = json.load(settings_file)
        except (OSError, ValueError, TypeError):
            return settings
        if isinstance(loaded, dict) and isinstance(
            loaded.get("auto_hide"), bool
        ):
            settings["auto_hide"] = loaded["auto_hide"]
        return settings

    def save_switcher_settings(self):
        try:
            os.makedirs(
                os.path.dirname(SWITCHER_SETTINGS_FILE), exist_ok=True
            )
            temporary = f"{SWITCHER_SETTINGS_FILE}.tmp"
            with open(temporary, "w", encoding="utf-8") as settings_file:
                json.dump(
                    {"auto_hide": self.auto_hide_enabled},
                    settings_file,
                    indent=2,
                )
                settings_file.write("\n")
                settings_file.flush()
                os.fsync(settings_file.fileno())
            os.replace(temporary, SWITCHER_SETTINGS_FILE)
        except OSError as exc:
            print(
                f"app-switcher: cannot save settings: {exc}",
                flush=True,
            )

    def visible_panel_width(self):
        return DRAG_HANDLE_WIDTH if self.collapsed else PANEL_WIDTH

    def clamp_position(self, x, y):
        geometry = self.root.get_geometry()
        # Keep the handle at the same coordinates when expanding so it cannot
        # jump out from under the pointer near the right screen edge.
        group_width = PANEL_WIDTH + TRAY_GAP + self.tray_width
        max_x = max(0, geometry.width - group_width)
        max_y = max(0, geometry.height - PANEL_HEIGHT)
        return max(0, min(x, max_x)), max(0, min(y, max_y))

    def load_position(self):
        try:
            with open(POSITION_FILE, "r", encoding="utf-8") as position_file:
                x_text, y_text = position_file.read().strip().split()
                return int(x_text), int(y_text)
        except (OSError, TypeError, ValueError):
            geometry = self.root.get_geometry()
            return (
                (geometry.width - PANEL_WIDTH) // 2,
                12,
            )

    def save_position(self):
        try:
            os.makedirs(os.path.dirname(POSITION_FILE), exist_ok=True)
            temporary = f"{POSITION_FILE}.tmp"
            with open(temporary, "w", encoding="utf-8") as position_file:
                position_file.write(
                    f"{self.preferred_x} {self.preferred_y}\n"
                )
            os.replace(temporary, POSITION_FILE)
        except OSError as exc:
            print(f"app-switcher: cannot save position: {exc}", flush=True)

    def notification_menu_position(self):
        geometry = self.root.get_geometry()
        notification_x = (
            DRAG_HANDLE_WIDTH
            + 4
            + len(APPS) * (BUTTON_WIDTH + BUTTON_GAP)
            - BUTTON_GAP
            + NOTIFICATION_BUTTON_GAP
        )
        x = self.panel_x + notification_x + NOTIFICATION_BUTTON_WIDTH
        x -= NOTIFICATION_MENU_WIDTH
        x = max(0, min(x, geometry.width - NOTIFICATION_MENU_WIDTH))
        below_y = self.panel_y + PANEL_HEIGHT + 4
        if below_y + NOTIFICATION_MENU_HEIGHT <= geometry.height:
            y = below_y
        else:
            y = max(0, self.panel_y - NOTIFICATION_MENU_HEIGHT - 4)
        return x, y

    def move_notification_menu(self):
        if not self.notification_menu_open:
            return
        x, y = self.notification_menu_position()
        self.notification_menu.configure(x=x, y=y, stack_mode=X.Above)

    def open_notification_menu(self):
        self.close_context_menu()
        self.set_collapsed(False)
        self.notification_menu_open = True
        self.notification_menu_last_interaction = time.monotonic()
        self.move_notification_menu()
        self.notification_menu.map()
        self.paint_notification_menu(force=True)
        self.paint(force=True)

    def close_notification_menu(self):
        if not self.notification_menu_open:
            return
        self.notification_menu_open = False
        self.menu_hovered = None
        self.notification_menu.unmap()
        self.paint(force=True)

    def toggle_notification_menu(self):
        if self.notification_menu_open:
            self.close_notification_menu()
        else:
            self.open_notification_menu()

    def context_menu_position(self):
        geometry = self.root.get_geometry()
        if (
            self.context_menu_mode == "windows"
            and self.context_menu_app_index is not None
        ):
            anchor_x = (
                self.panel_x
                + DRAG_HANDLE_WIDTH
                + 4
                + self.context_menu_app_index
                * (BUTTON_WIDTH + BUTTON_GAP)
            )
        else:
            anchor_x = self.panel_x
        x = max(
            0,
            min(anchor_x, geometry.width - CONTEXT_MENU_WIDTH),
        )
        below_y = self.panel_y + PANEL_HEIGHT + 4
        if below_y + self.context_menu_height <= geometry.height:
            y = below_y
        else:
            y = max(
                0,
                self.panel_y - self.context_menu_height - 4,
            )
        return x, y

    def move_context_menu(self):
        if not self.context_menu_open:
            return
        x, y = self.context_menu_position()
        self.context_menu.configure(
            x=x,
            y=y,
            width=CONTEXT_MENU_WIDTH,
            height=self.context_menu_height,
            stack_mode=X.Above,
        )

    def open_window_menu(self, app_index):
        windows = self.find_windows(APPS[app_index])
        if not windows:
            return
        self.close_notification_menu()
        self.set_collapsed(False)
        self.context_menu_mode = "windows"
        self.context_menu_app_index = app_index
        self.context_menu_entries = windows[:CONTEXT_MENU_MAX_ROWS]
        self.context_menu_hovered = None
        self.context_menu_height = (
            8
            + len(self.context_menu_entries) * CONTEXT_MENU_ROW_HEIGHT
        )
        self.context_menu_last_interaction = time.monotonic()
        self.context_menu_open = True
        self.move_context_menu()
        self.context_menu.map()
        self.paint_context_menu()

    def open_switcher_settings_menu(self):
        self.close_notification_menu()
        self.context_menu_mode = "settings"
        self.context_menu_app_index = None
        self.context_menu_entries = []
        self.context_menu_hovered = None
        self.context_menu_height = 8 + CONTEXT_MENU_ROW_HEIGHT
        self.context_menu_last_interaction = time.monotonic()
        self.context_menu_open = True
        self.move_context_menu()
        self.context_menu.map()
        self.paint_context_menu()

    def close_context_menu(self):
        if not self.context_menu_open:
            return
        self.context_menu_open = False
        self.context_menu_mode = None
        self.context_menu_app_index = None
        self.context_menu_entries = []
        self.context_menu_hovered = None
        self.context_menu.unmap()

    def toggle_switcher_settings_menu(self):
        if (
            self.context_menu_open
            and self.context_menu_mode == "settings"
        ):
            self.close_context_menu()
        else:
            self.close_context_menu()
            self.open_switcher_settings_menu()

    def close_all_menus(self):
        self.close_notification_menu()
        self.close_context_menu()

    def set_collapsed(self, collapsed):
        collapsed = bool(collapsed and self.auto_hide_enabled)
        if collapsed == self.collapsed:
            return
        if collapsed:
            self.close_all_menus()
        self.collapsed = collapsed
        target_x, target_y = self.clamp_position(
            self.preferred_x,
            self.preferred_y,
        )
        self.panel_x, self.panel_y = target_x, target_y
        self.window.configure(
            x=target_x,
            y=target_y,
            width=self.visible_panel_width(),
        )
        self.move_notification_menu()
        self.move_context_menu()
        self.hovered = None
        self.last_visual_state = None
        self.move_tray()
        self.paint(force=True)

    @staticmethod
    def point_in_rect(x, y, left, top, width, height):
        return (
            left <= x < left + width
            and top <= y < top + height
        )

    def pointer_over_group(self):
        try:
            pointer = self.root.query_pointer()
        except (error.BadWindow, error.XError):
            return False
        x = pointer.root_x
        y = pointer.root_y
        if self.point_in_rect(
            x,
            y,
            self.panel_x,
            self.panel_y,
            self.visible_panel_width(),
            PANEL_HEIGHT,
        ):
            return True
        if not self.collapsed and self.tray_frame is not None:
            tray_x = self.panel_x + PANEL_WIDTH + TRAY_GAP
            tray_y = self.panel_y + max(
                0,
                (PANEL_HEIGHT - self.tray_height) // 2,
            )
            if self.point_in_rect(
                x,
                y,
                tray_x,
                tray_y,
                self.tray_width,
                self.tray_height,
            ):
                return True
        if self.notification_menu_open:
            menu_x, menu_y = self.notification_menu_position()
            if self.point_in_rect(
                x,
                y,
                menu_x,
                menu_y,
                NOTIFICATION_MENU_WIDTH,
                NOTIFICATION_MENU_HEIGHT,
            ):
                return True
        if self.context_menu_open:
            menu_x, menu_y = self.context_menu_position()
            if self.point_in_rect(
                x,
                y,
                menu_x,
                menu_y,
                CONTEXT_MENU_WIDTH,
                self.context_menu_height,
            ):
                return True
        return False

    def update_auto_hide(self):
        if not self.auto_hide_enabled:
            self.auto_hide_deadline = None
            self.set_collapsed(False)
            return
        if (
            self.drag_origin is not None
            or self.notification_menu_open
            or self.context_menu_open
            or self.pointer_over_group()
        ):
            self.auto_hide_deadline = None
            return
        now = time.monotonic()
        if self.auto_hide_deadline is None:
            self.auto_hide_deadline = now + AUTO_HIDE_DELAY_SECONDS
        elif now >= self.auto_hide_deadline:
            self.set_collapsed(True)
            self.auto_hide_deadline = None

    def keep_on_screen(self):
        geometry = self.root.get_geometry()
        screen_size = (geometry.width, geometry.height)
        if screen_size != self.last_screen_size:
            self.last_screen_size = screen_size
            x, y = self.clamp_position(
                self.preferred_x, self.preferred_y
            )
        else:
            x, y = self.clamp_position(self.panel_x, self.panel_y)
        if (x, y) != (self.panel_x, self.panel_y):
            self.panel_x, self.panel_y = x, y
            self.window.configure(x=x, y=y)
            self.move_notification_menu()
            self.move_context_menu()

    def find_tray_window(self):
        # dockapp-mode trays may not be listed in _NET_CLIENT_LIST. Openbox
        # reparents them as root -> frame -> client, so inspect only a few
        # shallow levels rather than walking every application child window.
        try:
            level = list(self.root.query_tree().children)
        except (error.BadWindow, error.XError):
            return None
        for _ in range(3):
            next_level = []
            for window in level:
                try:
                    if "stalonetray" in self.window_classes(window):
                        return window
                    next_level.extend(window.query_tree().children)
                except (error.BadWindow, error.XError):
                    continue
            level = next_level
        return None

    def clear_tray_cache(self):
        self.tray_window = None
        self.tray_frame = None
        self.tray_width = TRAY_DEFAULT_WIDTH
        self.tray_height = TRAY_DEFAULT_WIDTH

    def refresh_tray_cache(self):
        tray = self.find_tray_window()
        if tray is None:
            self.clear_tray_cache()
            return False
        try:
            geometry = tray.get_geometry()
            self.tray_width = max(TRAY_DEFAULT_WIDTH, geometry.width)
            self.tray_height = geometry.height
            # Openbox reparents utility windows. Move its frame while deriving
            # the current frame inset dynamically, so tray icon input stays
            # with stalonetray and no XEmbed behavior has to be reimplemented.
            parent = tray.query_tree().parent
            self.tray_window = tray
            self.tray_frame = parent
            if parent.id == self.root.id:
                self.tray_inset_x = 0
                self.tray_inset_y = 0
            else:
                absolute = self.root.translate_coords(tray, 0, 0)
                frame_geometry = parent.get_geometry()
                self.tray_inset_x = absolute.x - frame_geometry.x
                self.tray_inset_y = absolute.y - frame_geometry.y
            return True
        except (error.BadWindow, error.XError):
            self.clear_tray_cache()
            return False

    def move_tray(self):
        if self.tray_frame is None:
            return
        if self.collapsed:
            geometry = self.root.get_geometry()
            target_x = geometry.width + self.tray_width + 16
            target_y = self.panel_y
        else:
            target_x = self.panel_x + PANEL_WIDTH + TRAY_GAP
            target_y = self.panel_y + max(
                0, (PANEL_HEIGHT - self.tray_height) // 2
            )
        try:
            self.tray_frame.configure(
                x=target_x - self.tray_inset_x,
                y=target_y - self.tray_inset_y,
                stack_mode=X.Above,
            )
        except (error.BadWindow, error.XError):
            self.clear_tray_cache()

    def sync_tray_position(self):
        now = time.monotonic()
        if (
            self.tray_window is None
            or now - self.last_tray_refresh >= 2.0
        ):
            self.last_tray_refresh = now
            self.refresh_tray_cache()
            self.keep_on_screen()
        self.move_tray()

    def client_ids(self):
        prop = self.root.get_full_property(
            self.atoms["_NET_CLIENT_LIST_STACKING"], X.AnyPropertyType
        )
        if prop is None:
            prop = self.root.get_full_property(
                self.atoms["_NET_CLIENT_LIST"], X.AnyPropertyType
            )
        return list(prop.value) if prop is not None else []

    @staticmethod
    def window_classes(window):
        values = window.get_wm_class() or ()
        return {str(value).lower() for value in values}

    def window_pid(self, window):
        try:
            prop = window.get_full_property(
                self.atoms["_NET_WM_PID"],
                X.AnyPropertyType,
            )
            if prop is None or prop.value is None or not len(prop.value):
                return None
            return int(prop.value[0])
        except (error.BadWindow, error.XError, TypeError, ValueError):
            return None

    def process_info(self, pid):
        now = time.monotonic()
        cached = self.process_info_cache.get(pid)
        if cached is not None and now - cached[0] < 5:
            return cached[1]

        info = None
        try:
            name = ""
            parent_pid = 0
            with open(
                f"/proc/{pid}/status", "r", encoding="utf-8"
            ) as status_file:
                for line in status_file:
                    if line.startswith("Name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("PPid:"):
                        parent_pid = int(line.split(":", 1)[1].strip())
            executable = os.path.realpath(f"/proc/{pid}/exe")
            with open(f"/proc/{pid}/cmdline", "rb") as cmdline_file:
                command = (
                    cmdline_file.read().split(b"\0", 1)[0]
                    .decode("utf-8", errors="replace")
                    .strip()
                )
            info = {
                "name": name.lower(),
                "parent_pid": parent_pid,
                "executable": executable,
                "command": command,
            }
        except (FileNotFoundError, OSError, TypeError, ValueError):
            pass
        self.process_info_cache[pid] = (now, info)
        return info

    def process_belongs_to_app(self, pid, app):
        visited = set()
        for _depth in range(8):
            if pid is None or pid <= 1 or pid in visited:
                break
            visited.add(pid)
            info = self.process_info(pid)
            if info is None:
                break
            identities = {
                info["name"],
                os.path.basename(info["executable"]).lower(),
                os.path.basename(info["command"]).lower(),
            }
            if identities.intersection(app["process_names"]):
                return True
            if any(
                info["executable"].startswith(prefix)
                or info["command"].startswith(prefix)
                for prefix in app["executable_prefixes"]
            ):
                return True
            pid = info["parent_pid"]
        return False

    def window_matches_app(self, window, app):
        try:
            classes = self.window_classes(window)
        except (error.BadWindow, error.XError):
            return False
        if classes.intersection(app["classes"]):
            return True
        return self.process_belongs_to_app(
            self.window_pid(window),
            app,
        )

    def window_title(self, window):
        try:
            prop = window.get_full_property(
                self.atoms["_NET_WM_NAME"],
                X.AnyPropertyType,
            )
            if prop is not None and prop.value is not None:
                value = prop.value
                if isinstance(value, bytes):
                    return value.decode("utf-8", errors="replace").strip()
                try:
                    return bytes(value).decode(
                        "utf-8", errors="replace"
                    ).strip("\x00 ")
                except (TypeError, ValueError):
                    text = str(value).strip()
                    if text:
                        return text
            return str(window.get_wm_name() or "").strip()
        except (error.BadWindow, error.XError):
            return ""

    @staticmethod
    def safe_display_text(value):
        return (
            str(value)
            .encode("latin-1", errors="replace")
            .decode("latin-1")
        )

    def find_windows(self, app):
        candidates = []
        for window_id in self.client_ids():
            if window_id in {
                self.window.id,
                self.notification_menu.id,
                self.context_menu.id,
            }:
                continue
            try:
                window = self.display.create_resource_object("window", window_id)
                if not self.window_matches_app(window, app):
                    continue
                geometry = window.get_geometry()
                title = self.window_title(window)
                # WeChat creates several tiny helper/clipboard windows. Only
                # expose normal user-facing top-level windows.
                if (
                    geometry.width < 160
                    or geometry.height < 100
                ):
                    continue
                classes = self.window_classes(window)
                primary = int(
                    not classes.intersection(app["primary_classes"])
                )
                candidates.append((primary, window.id, window))
            except (error.BadWindow, error.XError):
                continue
        candidates.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in candidates]

    def find_window(self, app):
        windows = self.find_windows(app)
        if not windows:
            return None
        remembered_id = self.last_active_by_app.get(app["label"])
        for window in windows:
            if window.id == remembered_id:
                return window
        return windows[0]

    def app_for_window_id(self, window_id, windows_by_app=None):
        if window_id is None:
            return None
        if windows_by_app is None:
            windows_by_app = {
                app["label"]: self.find_windows(app) for app in APPS
            }
        for app in APPS:
            if any(
                window.id == window_id
                for window in windows_by_app[app["label"]]
            ):
                return app
        return None

    def active_window_id(self):
        prop = self.root.get_full_property(
            self.atoms["_NET_ACTIVE_WINDOW"], X.AnyPropertyType
        )
        if prop is None or not len(prop.value):
            return None
        return int(prop.value[0])

    def window_is_hidden(self, window):
        try:
            state = window.get_full_property(
                self.atoms["_NET_WM_STATE"],
                X.AnyPropertyType,
            )
            return bool(
                state is not None
                and self.atoms["_NET_WM_STATE_HIDDEN"] in state.value
            )
        except (error.BadWindow, error.XError):
            return True

    def iconify(self, window):
        try:
            # Do not ask Openbox to iconify a window that is already hidden.
            # A redundant WM_CHANGE_STATE request can briefly disturb the
            # active-window state; the visibility synchronizer may then see
            # the other app as active and iconify the window we just restored.
            if self.window_is_hidden(window):
                return
            message = protocol.event.ClientMessage(
                window=window,
                client_type=self.atoms["WM_CHANGE_STATE"],
                data=(32, [3, 0, 0, 0, 0]),  # ICCCM IconicState
            )
            self.root.send_event(
                message,
                event_mask=(
                    X.SubstructureRedirectMask
                    | X.SubstructureNotifyMask
                ),
            )
        except (error.BadWindow, error.XError):
            return

    def sync_managed_app_visibility(self):
        active_id = self.active_window_id()
        if self.pending_activation_id is not None:
            if active_id == self.pending_activation_id:
                self.pending_activation_id = None
                self.pending_activation_deadline = 0.0
            elif time.monotonic() < self.pending_activation_deadline:
                return
            else:
                self.pending_activation_id = None
                self.pending_activation_deadline = 0.0
        windows_by_app = {
            app["label"]: self.find_windows(app) for app in APPS
        }
        managed_state = (
            active_id,
            tuple(
                (
                    app["label"],
                    tuple(
                        window.id
                        for window in windows_by_app[app["label"]]
                    ),
                )
                for app in APPS
            ),
        )
        if managed_state == self.last_managed_state:
            return
        active_app = self.app_for_window_id(active_id, windows_by_app)
        if active_app is None:
            self.last_managed_state = managed_state
            return
        self.last_active_by_app[active_app["label"]] = active_id
        # Do not iconify windows from the passive state synchronizer. Openbox
        # publishes short-lived active-window transitions while restoring an
        # iconic Qt window; acting on those snapshots can minimize the window
        # that has just become active. Explicit switcher actions already hide
        # the other managed application in activate(), where the intended
        # target is known and protected by pending_activation_id.
        self.last_managed_state = managed_state

    def activate(self, app, target_window=None):
        windows = self.find_windows(app)
        if not windows:
            now = time.monotonic()
            if (
                now - self.last_launch_attempt.get(app["label"], 0)
                < 3
            ):
                return
            # Re-read the EWMH list immediately before launching. This closes
            # the race where a just-created window appears between the click
            # and the application start branch.
            self.display.sync()
            windows = self.find_windows(app)
        if not windows:
            self.last_launch_attempt[app["label"]] = time.monotonic()
            subprocess.Popen(
                app["command"],
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        self.last_launch_attempt.pop(app["label"], None)

        active_id = self.active_window_id()
        window_ids = [window.id for window in windows]
        if target_window is None:
            if active_id in window_ids and len(windows) > 1:
                current_index = window_ids.index(active_id)
                target_window = windows[
                    (current_index + 1) % len(windows)
                ]
            else:
                remembered_id = self.last_active_by_app.get(app["label"])
                target_window = next(
                    (
                        window
                        for window in windows
                        if window.id == remembered_id
                    ),
                    windows[0],
                )

        try:
            target_id = (
                target_window.id if target_window is not None else None
            )
            refreshed_windows = self.find_windows(app)
            if target_id is not None:
                target_window = next(
                    (
                        window
                        for window in refreshed_windows
                        if window.id == target_id
                    ),
                    None,
                )
            if target_window is None:
                target_window = (
                    refreshed_windows[0] if refreshed_windows else None
                )
            if target_window is None:
                return
            self.pending_activation_id = target_window.id
            self.pending_activation_deadline = time.monotonic() + 2
            # A raised-but-covered Qt window is still "visible" to the
            # application. WeChat suppresses its native message popup in that
            # state, so make this a real app switch by iconifying the other
            # managed app before activating the requested one.
            for other_app in APPS:
                if other_app is app:
                    continue
                for other_window in self.find_windows(other_app):
                    self.iconify(other_window)
            # Let the window manager perform the complete uniconify/focus/
            # raise transition. Mapping the client window directly races with
            # Openbox's IconicState bookkeeping (most visibly on WeChat's
            # login window), causing it to flash and immediately hide again.
            message = protocol.event.ClientMessage(
                window=target_window,
                client_type=self.atoms["_NET_ACTIVE_WINDOW"],
                data=(32, [2, X.CurrentTime, 0, 0, 0]),
            )
            self.root.send_event(
                message,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )
            self.last_active_by_app[app["label"]] = target_window.id
            self.display.flush()
        except (error.BadWindow, error.XError):
            return

    def paint(self, force=False):
        start_x = DRAG_HANDLE_WIDTH + 4
        y = (PANEL_HEIGHT - BUTTON_HEIGHT) // 2
        active_id = self.active_window_id()
        app_windows = [self.find_windows(app) for app in APPS]
        notification_settings = load_settings()
        visual_state = (
            active_id,
            tuple(
                tuple(window.id for window in windows)
                for windows in app_windows
            ),
            self.hovered,
            notification_settings["enabled"],
            tuple(
                notification_settings["apps"].get(app["label"].lower(), True)
                for app in APPS
            ),
            self.notification_menu_open,
            self.context_menu_open,
            self.auto_hide_enabled,
            self.collapsed,
        )
        if not force and visual_state == self.last_visual_state:
            return
        self.last_visual_state = visual_state
        self.button_rects = []
        self.notification_rect = None

        # Render into a pixmap and copy once. Selkies never observes the
        # intermediate clear/button/text operations, which prevents flicker.
        self.buffer.fill_rectangle(
            self.panel_gc, 0, 0, PANEL_WIDTH, PANEL_HEIGHT
        )
        self.buffer.draw_text(self.text_gc, 12, 26, "::")

        for index, (app, windows) in enumerate(zip(APPS, app_windows)):
            x = start_x + index * (BUTTON_WIDTH + BUTTON_GAP)
            is_active = any(
                window.id == active_id for window in windows
            )
            gc = self.active_gc if is_active else self.button_gc
            if self.hovered == index and not is_active:
                gc = self.hover_gc

            self.buffer.fill_rectangle(gc, x, y, BUTTON_WIDTH, BUTTON_HEIGHT)
            status_gc = (
                self.available_gc if windows else self.unavailable_gc
            )
            self.buffer.fill_rectangle(status_gc, x + 10, y + 14, 6, 6)

            label = app["label"]
            if len(windows) > 1:
                label = f"{label} [{len(windows)}]"
            text_width = len(label) * 6
            text_x = x + (BUTTON_WIDTH - text_width) // 2 + 4
            self.buffer.draw_text(
                self.text_gc, text_x, y + 22, label
            )
            self.button_rects.append((x, y, BUTTON_WIDTH, BUTTON_HEIGHT))

        notification_x = (
            start_x
            + len(APPS) * (BUTTON_WIDTH + BUTTON_GAP)
            - BUTTON_GAP
            + NOTIFICATION_BUTTON_GAP
        )
        notification_gc = (
            self.active_gc
            if notification_settings["enabled"]
            else self.button_gc
        )
        if self.hovered == "notifications":
            notification_gc = self.hover_gc
        self.buffer.fill_rectangle(
            notification_gc,
            notification_x,
            y,
            NOTIFICATION_BUTTON_WIDTH,
            BUTTON_HEIGHT,
        )
        # Compact bell glyph drawn with X11 primitives, avoiding an icon/font
        # dependency. The status dot reflects the global notification switch.
        bell_x = notification_x + 8
        bell_y = y + 9
        self.buffer.arc(self.text_gc, bell_x, bell_y, 12, 12, 0, 180 * 64)
        self.buffer.line(
            self.text_gc, bell_x, bell_y + 6, bell_x, bell_y + 15
        )
        self.buffer.line(
            self.text_gc,
            bell_x + 12,
            bell_y + 6,
            bell_x + 12,
            bell_y + 15,
        )
        self.buffer.line(
            self.text_gc,
            bell_x - 2,
            bell_y + 15,
            bell_x + 14,
            bell_y + 15,
        )
        self.buffer.line(
            self.text_gc,
            bell_x + 5,
            bell_y + 18,
            bell_x + 7,
            bell_y + 18,
        )
        status_gc = (
            self.available_gc
            if notification_settings["enabled"]
            else self.disabled_gc
        )
        self.buffer.fill_rectangle(
            status_gc, notification_x + 20, y + 5, 4, 4
        )
        self.notification_rect = (
            notification_x,
            y,
            NOTIFICATION_BUTTON_WIDTH,
            BUTTON_HEIGHT,
        )

        self.window.copy_area(
            self.copy_gc,
            self.buffer,
            0,
            0,
            self.visible_panel_width(),
            PANEL_HEIGHT,
            0,
            0,
        )
        self.display.flush()
        if self.notification_menu_open:
            self.paint_notification_menu()
        if self.context_menu_open:
            self.paint_context_menu()

    def paint_notification_menu(self, force=False):
        del force
        settings = load_settings()
        rows = (
            ("All", settings["enabled"]),
            ("WeChat", settings["apps"]["wechat"]),
            ("WeFlow", settings["apps"]["weflow"]),
        )
        self.notification_menu_buffer.fill_rectangle(
            self.panel_gc,
            0,
            0,
            NOTIFICATION_MENU_WIDTH,
            NOTIFICATION_MENU_HEIGHT,
        )
        for index, (label, enabled) in enumerate(rows):
            top = 4 + index * NOTIFICATION_MENU_ROW_HEIGHT
            if self.menu_hovered == index:
                self.notification_menu_buffer.fill_rectangle(
                    self.hover_gc,
                    4,
                    top,
                    NOTIFICATION_MENU_WIDTH - 8,
                    NOTIFICATION_MENU_ROW_HEIGHT - 2,
                )
            self.notification_menu_buffer.draw_text(
                self.text_gc,
                12,
                top + 18,
                label,
            )
            toggle_x = NOTIFICATION_MENU_WIDTH - 40
            toggle_y = top + 8
            track_gc = self.active_gc if enabled else self.disabled_gc
            self.notification_menu_buffer.fill_rectangle(
                track_gc, toggle_x, toggle_y, 28, 12
            )
            knob_x = toggle_x + (17 if enabled else 1)
            self.notification_menu_buffer.fill_rectangle(
                self.text_gc, knob_x, toggle_y + 1, 10, 10
            )
        self.notification_menu.copy_area(
            self.copy_gc,
            self.notification_menu_buffer,
            0,
            0,
            NOTIFICATION_MENU_WIDTH,
            NOTIFICATION_MENU_HEIGHT,
            0,
            0,
        )
        self.display.flush()

    def paint_context_menu(self, force=False):
        del force
        if not self.context_menu_open:
            return
        self.context_menu_buffer.fill_rectangle(
            self.panel_gc,
            0,
            0,
            CONTEXT_MENU_WIDTH,
            CONTEXT_MENU_MAX_HEIGHT,
        )
        if self.context_menu_mode == "settings":
            rows = [("Auto hide", self.auto_hide_enabled, None)]
        else:
            active_id = self.active_window_id()
            rows = []
            for index, window in enumerate(self.context_menu_entries):
                title = self.safe_display_text(
                    self.window_title(window)
                )
                if not title or title.replace("?", "").strip() == "":
                    app = APPS[self.context_menu_app_index]
                    title = f"{app['label']} window {index + 1}"
                title = title[:46]
                rows.append((title, window.id == active_id, window))

        for index, (label, selected, _value) in enumerate(rows):
            top = 4 + index * CONTEXT_MENU_ROW_HEIGHT
            if self.context_menu_hovered == index:
                self.context_menu_buffer.fill_rectangle(
                    self.hover_gc,
                    4,
                    top,
                    CONTEXT_MENU_WIDTH - 8,
                    CONTEXT_MENU_ROW_HEIGHT - 2,
                )
            prefix = "> " if selected else "  "
            self.context_menu_buffer.draw_text(
                self.text_gc,
                12,
                top + 18,
                f"{prefix}{label}",
            )
            if self.context_menu_mode == "settings":
                toggle_x = CONTEXT_MENU_WIDTH - 40
                toggle_y = top + 8
                track_gc = (
                    self.active_gc if selected else self.disabled_gc
                )
                self.context_menu_buffer.fill_rectangle(
                    track_gc,
                    toggle_x,
                    toggle_y,
                    28,
                    12,
                )
                knob_x = toggle_x + (17 if selected else 1)
                self.context_menu_buffer.fill_rectangle(
                    self.text_gc,
                    knob_x,
                    toggle_y + 1,
                    10,
                    10,
                )

        self.context_menu.copy_area(
            self.copy_gc,
            self.context_menu_buffer,
            0,
            0,
            CONTEXT_MENU_WIDTH,
            self.context_menu_height,
            0,
            0,
        )
        self.display.flush()

    def button_at(self, x, y):
        for index, (left, top, width, height) in enumerate(self.button_rects):
            if left <= x < left + width and top <= y < top + height:
                return index
        return None

    def notification_button_at(self, x, y):
        if self.notification_rect is None:
            return False
        left, top, width, height = self.notification_rect
        return left <= x < left + width and top <= y < top + height

    @staticmethod
    def handle_at(x, y):
        return 0 <= x < DRAG_HANDLE_WIDTH and 0 <= y < PANEL_HEIGHT

    @staticmethod
    def notification_menu_row_at(x, y):
        if not 4 <= x < NOTIFICATION_MENU_WIDTH - 4:
            return None
        row = (y - 4) // NOTIFICATION_MENU_ROW_HEIGHT
        if 0 <= row < 3:
            return int(row)
        return None

    def context_menu_row_at(self, x, y):
        if not 4 <= x < CONTEXT_MENU_WIDTH - 4:
            return None
        row = (y - 4) // CONTEXT_MENU_ROW_HEIGHT
        if self.context_menu_mode == "settings":
            row_count = 1
        else:
            row_count = len(self.context_menu_entries)
        if 0 <= row < row_count:
            return int(row)
        return None

    def toggle_notification_setting(self, row):
        settings = load_settings()
        if row == 0:
            settings["enabled"] = not settings["enabled"]
        elif row == 1:
            settings["apps"]["wechat"] = not settings["apps"]["wechat"]
        elif row == 2:
            settings["apps"]["weflow"] = not settings["apps"]["weflow"]
        save_settings(settings)
        self.notification_menu_last_interaction = time.monotonic()
        self.last_visual_state = None
        self.paint(force=True)
        self.paint_notification_menu(force=True)

    def update_drag(self, root_x, root_y):
        if self.drag_origin is None:
            return
        origin_x, origin_y, panel_x, panel_y = self.drag_origin
        delta_x = root_x - origin_x
        delta_y = root_y - origin_y
        if abs(delta_x) > 2 or abs(delta_y) > 2:
            if not self.dragging:
                self.close_all_menus()
            self.dragging = True
        if not self.dragging:
            return
        self.panel_x, self.panel_y = self.clamp_position(
            panel_x + delta_x,
            panel_y + delta_y,
        )
        self.window.configure(x=self.panel_x, y=self.panel_y)
        self.move_notification_menu()
        self.move_context_menu()
        self.move_tray()
        self.display.flush()

    def handle_notification_menu_event(self, event):
        if event.type == X.ButtonPress and event.detail == 1:
            row = self.notification_menu_row_at(event.event_x, event.event_y)
            if row is not None:
                self.toggle_notification_setting(row)
        elif event.type == X.MotionNotify:
            hovered = self.notification_menu_row_at(
                event.event_x, event.event_y
            )
            if hovered != self.menu_hovered:
                self.menu_hovered = hovered
                self.paint_notification_menu()
        elif event.type == X.LeaveNotify:
            if self.menu_hovered is not None:
                self.menu_hovered = None
                self.paint_notification_menu()
        elif event.type == X.Expose:
            self.paint_notification_menu(force=True)

    def handle_context_menu_event(self, event):
        self.context_menu_last_interaction = time.monotonic()
        if event.type == X.ButtonPress and event.detail == 1:
            row = self.context_menu_row_at(
                event.event_x,
                event.event_y,
            )
            if row is None:
                return
            if self.context_menu_mode == "settings":
                self.auto_hide_enabled = not self.auto_hide_enabled
                self.save_switcher_settings()
                self.auto_hide_deadline = None
                if not self.auto_hide_enabled:
                    self.set_collapsed(False)
                self.paint_context_menu(force=True)
                self.last_visual_state = None
                self.paint(force=True)
            elif row < len(self.context_menu_entries):
                app = APPS[self.context_menu_app_index]
                target_window = self.context_menu_entries[row]
                self.close_context_menu()
                self.activate(app, target_window)
        elif event.type == X.MotionNotify:
            hovered = self.context_menu_row_at(
                event.event_x,
                event.event_y,
            )
            if hovered != self.context_menu_hovered:
                self.context_menu_hovered = hovered
                self.paint_context_menu()
        elif event.type == X.LeaveNotify:
            if self.context_menu_hovered is not None:
                self.context_menu_hovered = None
                self.paint_context_menu()
        elif event.type == X.EnterNotify:
            self.auto_hide_deadline = None
        elif event.type == X.Expose:
            self.paint_context_menu(force=True)

    def handle_event(self, event):
        event_window = getattr(event, "window", None)
        if (
            event_window is not None
            and event_window.id == self.notification_menu.id
        ):
            self.handle_notification_menu_event(event)
            return
        if (
            event_window is not None
            and event_window.id == self.context_menu.id
        ):
            self.handle_context_menu_event(event)
            return

        if event.type == X.ButtonPress and event.detail == 1:
            index = self.button_at(event.event_x, event.event_y)
            if index is not None:
                self.close_all_menus()
                self.activate(APPS[index])
            elif self.notification_button_at(event.event_x, event.event_y):
                self.toggle_notification_menu()
            else:
                self.close_all_menus()
                self.drag_origin = (
                    event.root_x,
                    event.root_y,
                    self.panel_x,
                    self.panel_y,
                )
                self.dragging = False
                self.window.grab_pointer(
                    False,
                    X.PointerMotionMask | X.ButtonReleaseMask,
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                    X.NONE,
                    X.NONE,
                    X.CurrentTime,
                )
        elif event.type == X.ButtonPress and event.detail == 3:
            index = self.button_at(event.event_x, event.event_y)
            if index is not None:
                self.open_window_menu(index)
            elif self.handle_at(event.event_x, event.event_y):
                self.toggle_switcher_settings_menu()
        elif event.type == X.MotionNotify:
            if self.drag_origin is not None:
                self.update_drag(event.root_x, event.root_y)
            else:
                hovered = self.button_at(event.event_x, event.event_y)
                if (
                    hovered is None
                    and self.notification_button_at(
                        event.event_x, event.event_y
                    )
                ):
                    hovered = "notifications"
                if hovered != self.hovered:
                    self.hovered = hovered
                    self.paint()
        elif event.type == X.EnterNotify:
            self.auto_hide_deadline = None
            self.set_collapsed(False)
        elif event.type == X.ButtonRelease and event.detail == 1:
            self.update_drag(event.root_x, event.root_y)
            if self.dragging:
                self.preferred_x = self.panel_x
                self.preferred_y = self.panel_y
                self.save_position()
            self.display.ungrab_pointer(X.CurrentTime)
            self.drag_origin = None
            self.dragging = False
        elif event.type == X.LeaveNotify:
            if self.drag_origin is None and self.hovered is not None:
                self.hovered = None
                self.paint()
            if self.auto_hide_enabled:
                self.auto_hide_deadline = (
                    time.monotonic() + AUTO_HIDE_DELAY_SECONDS
                )
        elif event.type == X.Expose:
            self.paint(force=True)
        elif event.type == X.PropertyNotify:
            self.paint()

    def run(self):
        self.keep_on_screen()
        self.sync_tray_position()
        self.sync_managed_app_visibility()
        self.paint(force=True)
        while True:
            readable, _, _ = select.select(
                [self.display.fileno()], [], [], POLL_SECONDS
            )
            if readable:
                pending_motion = None
                while self.display.pending_events():
                    event = self.display.next_event()
                    if event.type == X.MotionNotify:
                        pending_motion = event
                        continue
                    if pending_motion is not None:
                        self.handle_event(pending_motion)
                        pending_motion = None
                    self.handle_event(event)
                if pending_motion is not None:
                    self.handle_event(pending_motion)
            else:
                self.keep_on_screen()
                self.sync_tray_position()
                self.paint()
                if (
                    self.notification_menu_open
                    and time.monotonic()
                    - self.notification_menu_last_interaction
                    >= NOTIFICATION_MENU_TIMEOUT
                ):
                    self.close_notification_menu()
                if (
                    self.context_menu_open
                    and time.monotonic()
                    - self.context_menu_last_interaction
                    >= NOTIFICATION_MENU_TIMEOUT
                ):
                    self.close_context_menu()
            self.sync_managed_app_visibility()
            self.update_auto_hide()
            now = time.monotonic()
            if now - self.last_raise >= RAISE_INTERVAL_SECONDS:
                self.window.configure(stack_mode=X.Above)
                if self.notification_menu_open:
                    self.notification_menu.configure(stack_mode=X.Above)
                if self.context_menu_open:
                    self.context_menu.configure(stack_mode=X.Above)
                self.last_raise = now
            self.display.flush()


def main():
    while True:
        try:
            AppSwitcher().run()
        except (
            error.ConnectionClosedError,
            error.DisplayConnectionError,
            ConnectionError,
            OSError,
        ) as exc:
            print(f"app-switcher: X11 unavailable: {exc}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
