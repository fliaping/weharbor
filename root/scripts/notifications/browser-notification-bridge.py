#!/usr/bin/env python3
"""Forward freedesktop desktop notifications to Selkies browser clients."""

import asyncio
import html
import json
import logging
import os
import re
import threading
import time
from itertools import count

import dbus
from dbus import lowlevel
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from aiohttp import web

from notification_config import ensure_settings, load_settings
from app_control import register_routes


LOGGER = logging.getLogger("browser-notification-bridge")
NOTIFICATION_INTERFACE = "org.freedesktop.Notifications"
OBJECT_PATH = "/org/freedesktop/Notifications"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8765
SUPPORTED_APPS = {"wechat"}


def env_enabled(name, default=True):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def plain_text(value):
    value = re.sub(r"<[^>]*>", "", str(value or ""))
    return html.unescape(value).strip()


def hint_text(hints, name):
    value = hints.get(name)
    if value is None:
        return ""
    return str(value)


def classify_app(app_name, summary, hints):
    identity = " ".join(
        (
            str(app_name or ""),
            hint_text(hints, "desktop-entry"),
            hint_text(hints, "x-canonical-private-synchronous"),
            str(summary or ""),
        )
    ).lower()
    if any(value in identity for value in ("wechat", "weixin", "微信")):
        return "wechat"
    return None


class NotificationRelay:
    def __init__(self):
        self.loop = None
        self.clients = set()
        self.browser_status = {}

    def attach_loop(self, loop):
        self.loop = loop

    def publish(self, event):
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._publish_now, event)

    def _publish_now(self, event):
        for queue in tuple(self.clients):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    async def config(self, _request):
        settings = load_settings()
        settings["available"] = env_enabled(
            "ENABLE_BROWSER_NOTIFICATIONS", True
        )
        settings["appSwitcherEnabled"] = (
            env_enabled("ENABLE_APP_SWITCHER", True)
            and os.environ.get("APP_SWITCHER_MODE", "web") != "desktop"
        )
        return web.json_response(settings)

    async def health(self, _request):
        return web.json_response(
            {
                "status": "ok",
                "clients": len(self.clients),
                "browser_status": list(self.browser_status.values()),
            }
        )

    async def client_status(self, request):
        try:
            payload = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            raise web.HTTPBadRequest(text="invalid JSON")
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="expected an object")

        client_id = str(payload.get("clientId", ""))[:80]
        if not client_id:
            raise web.HTTPBadRequest(text="clientId is required")
        allowed_fields = (
            "clientId",
            "stage",
            "supported",
            "permission",
            "secureContext",
            "visibility",
            "error",
        )
        status = {
            field: payload[field]
            for field in allowed_fields
            if field in payload
            and isinstance(payload[field], (str, bool, int, float))
        }
        status["lastSeen"] = int(time.time())
        self.browser_status[client_id] = status
        LOGGER.info(
            "browser client=%r stage=%r permission=%r secure=%r error=%r",
            client_id,
            status.get("stage"),
            status.get("permission"),
            status.get("secureContext"),
            status.get("error"),
        )
        return web.json_response({"ok": True})

    async def events(self, request):
        queue = asyncio.Queue(maxsize=100)
        self.clients.add(queue)
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)
        await response.write(b"retry: 3000\n\n")
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    payload = json.dumps(
                        event, ensure_ascii=False, separators=(",", ":")
                    )
                    await response.write(
                        f"event: notification\ndata: {payload}\n\n".encode()
                    )
                except asyncio.TimeoutError:
                    await response.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            self.clients.discard(queue)
        return response


class FreedesktopNotificationMonitor:
    def __init__(self, relay):
        self.relay = relay
        self.ids = count(1)
        self.bus = dbus.bus.BusConnection(
            os.environ["DBUS_SESSION_BUS_ADDRESS"]
        )
        self.bus.add_message_filter(self._on_message)
        self.bus.call_blocking(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus.Monitoring",
            "BecomeMonitor",
            "asu",
            (
                [
                    "type='method_call',"
                    "interface='org.freedesktop.Notifications',"
                    "member='Notify'"
                ],
                dbus.UInt32(0),
            ),
        )

    def _on_message(self, _connection, message):
        if (
            message.get_type() != lowlevel.MESSAGE_TYPE_METHOD_CALL
            or message.get_interface() != NOTIFICATION_INTERFACE
            or message.get_member() != "Notify"
        ):
            return
        try:
            (
                app_name,
                replaces_id,
                _app_icon,
                summary,
                body,
                _actions,
                hints,
                _expire_timeout,
            ) = message.get_args_list(byte_arrays=True)
            self._forward(app_name, replaces_id, summary, body, hints)
        except (TypeError, ValueError, dbus.DBusException):
            LOGGER.exception("failed to process monitored notification")

    def _forward(self, app_name, replaces_id, summary, body, hints):
        notification_id = (
            int(replaces_id) if int(replaces_id) else next(self.ids)
        )
        app_id = classify_app(app_name, summary, hints)
        settings = load_settings()
        should_forward = (
            env_enabled("ENABLE_BROWSER_NOTIFICATIONS", True)
            and app_id in SUPPORTED_APPS
            and settings["enabled"]
            and settings["apps"].get(app_id, False)
        )
        if should_forward:
            self.relay.publish(
                {
                    "id": notification_id,
                    "app": app_id,
                    "title": plain_text(summary) or str(app_name) or app_id,
                    "body": plain_text(body),
                }
            )
        LOGGER.info(
            "notification app=%r classified=%r forwarded=%s",
            str(app_name),
            app_id,
            should_forward,
        )


async def serve_http(relay, ready):
    relay.attach_loop(asyncio.get_running_loop())
    application = web.Application()
    register_routes(application)
    application.router.add_get("/events", relay.events)
    application.router.add_get("/config", relay.config)
    application.router.add_get("/health", relay.health)
    application.router.add_post("/client-status", relay.client_status)
    runner = web.AppRunner(application, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, LISTEN_HOST, LISTEN_PORT)
    await site.start()
    ready.set()
    LOGGER.info(
        "notification bridge listening on http://%s:%s",
        LISTEN_HOST,
        LISTEN_PORT,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_settings()
    relay = NotificationRelay()
    DBusGMainLoop(set_as_default=True)
    monitor = FreedesktopNotificationMonitor(relay)
    dbus_loop = GLib.MainLoop()
    ready = threading.Event()
    http_thread = threading.Thread(
        target=lambda: asyncio.run(serve_http(relay, ready)),
        daemon=True,
    )
    http_thread.start()
    if not ready.wait(timeout=5):
        raise RuntimeError("notification HTTP bridge did not start")
    LOGGER.info("passively monitoring D-Bus service %s", NOTIFICATION_INTERFACE)
    try:
        dbus_loop.run()
    finally:
        del monitor


if __name__ == "__main__":
    main()
