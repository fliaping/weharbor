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
from collections import OrderedDict
from itertools import count
from pathlib import Path

import dbus
from dbus import lowlevel
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from aiohttp import ClientError, ClientSession, ClientTimeout, web

from notification_config import ensure_settings, load_settings


LOGGER = logging.getLogger("browser-notification-bridge")
NOTIFICATION_INTERFACE = "org.freedesktop.Notifications"
OBJECT_PATH = "/org/freedesktop/Notifications"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8765
SUPPORTED_APPS = {"wechat", "weflow"}
WEFLOW_CONFIG_PATH = Path("/config/.config/weflow/WeFlow-config.json")
WEFLOW_PUSH_RECONNECT_SECONDS = 3
WEFLOW_PUSH_EVENT_TTL_SECONDS = 15 * 60


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
    if "weflow" in identity:
        return "weflow"
    if any(value in identity for value in ("wechat", "weixin", "微信")):
        return "wechat"
    return None


class NotificationRelay:
    def __init__(self):
        self.loop = None
        self.clients = set()
        self.browser_status = {}
        self.weflow_push_status = {
            "stage": "starting",
            "lastEvent": None,
            "lastError": None,
        }

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
        return web.json_response(settings)

    async def health(self, _request):
        return web.json_response(
            {
                "status": "ok",
                "clients": len(self.clients),
                "browser_status": list(self.browser_status.values()),
                "weflow_push": self.weflow_push_status,
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


def load_weflow_push_config():
    try:
        config = json.loads(WEFLOW_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(config, dict):
        return None

    token = str(config.get("httpApiToken", "")).strip()
    if not token or token.startswith(("safe:", "lock:")):
        return {
            "enabled": config.get("messagePushEnabled") is True,
            "error": "WeFlow API token is unavailable to the bridge",
        }
    try:
        port = int(config.get("httpApiPort", 5031))
    except (TypeError, ValueError):
        port = 5031
    if not 1 <= port <= 65535:
        port = 5031
    return {
        "enabled": config.get("messagePushEnabled") is True,
        "url": f"http://127.0.0.1:{port}/api/v1/push/messages",
        "token": token,
    }


def message_notification(payload):
    source_name = plain_text(payload.get("sourceName")) or "微信"
    group_name = plain_text(payload.get("groupName"))
    content = plain_text(payload.get("content")) or "[新消息]"
    if group_name:
        return group_name, f"{source_name}: {content}"
    return source_name, content


class RecentPushEvents:
    def __init__(self):
        self.events = OrderedDict()

    def add(self, payload):
        now = time.monotonic()
        cutoff = now - WEFLOW_PUSH_EVENT_TTL_SECONDS
        while self.events:
            _, created_at = next(iter(self.events.items()))
            if created_at >= cutoff:
                break
            self.events.popitem(last=False)

        raw_id = str(payload.get("rawid", "")).strip()
        event_name = str(payload.get("event", "message.new"))
        key = f"{event_name}:{raw_id}" if raw_id else json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        )
        if key in self.events:
            return False
        self.events[key] = now
        return True


async def consume_weflow_push(relay):
    """Forward WeFlow's structured message SSE directly to browser clients."""
    seen = RecentPushEvents()
    last_event_id = ""
    process_started_at = int(time.time())
    timeout = ClientTimeout(total=None, connect=5, sock_read=60)

    async with ClientSession(timeout=timeout) as session:
        while True:
            config = load_weflow_push_config()
            if not config:
                relay.weflow_push_status = {
                    "stage": "waiting-for-config",
                    "lastEvent": None,
                    "lastError": None,
                }
                await asyncio.sleep(WEFLOW_PUSH_RECONNECT_SECONDS)
                continue
            if config.get("error"):
                relay.weflow_push_status = {
                    "stage": "configuration-error",
                    "lastEvent": None,
                    "lastError": config["error"],
                }
                LOGGER.warning("WeFlow push: %s", config["error"])
                await asyncio.sleep(10)
                continue
            if not config["enabled"]:
                relay.weflow_push_status = {
                    "stage": "disabled",
                    "lastEvent": None,
                    "lastError": "messagePushEnabled is false",
                }
                await asyncio.sleep(WEFLOW_PUSH_RECONNECT_SECONDS)
                continue

            headers = {
                "Authorization": f"Bearer {config['token']}",
                "Accept": "text/event-stream",
            }
            if last_event_id:
                headers["Last-Event-ID"] = last_event_id

            try:
                relay.weflow_push_status = {
                    "stage": "connecting",
                    "lastEvent": relay.weflow_push_status.get("lastEvent"),
                    "lastError": None,
                }
                async with session.get(config["url"], headers=headers) as response:
                    if response.status != 200:
                        error = f"HTTP {response.status}"
                        relay.weflow_push_status = {
                            "stage": "error",
                            "lastEvent": relay.weflow_push_status.get(
                                "lastEvent"
                            ),
                            "lastError": error,
                        }
                        LOGGER.warning("WeFlow push connection failed: %s", error)
                        await response.read()
                        await asyncio.sleep(WEFLOW_PUSH_RECONNECT_SECONDS)
                        continue

                    LOGGER.info("connected to WeFlow message push stream")
                    relay.weflow_push_status = {
                        "stage": "connected",
                        "lastEvent": relay.weflow_push_status.get("lastEvent"),
                        "lastError": None,
                    }
                    event_name = ""
                    event_id = ""
                    data_lines = []
                    async for raw_line in response.content:
                        line = raw_line.decode("utf-8", errors="replace").rstrip(
                            "\r\n"
                        )
                        if line:
                            if line.startswith("event:"):
                                event_name = line[6:].strip()
                            elif line.startswith("id:"):
                                event_id = line[3:].strip()
                            elif line.startswith("data:"):
                                data_lines.append(line[5:].lstrip())
                            continue

                        if event_id:
                            last_event_id = event_id
                        if event_name not in {
                            "message.new",
                            "message.revoke",
                        }:
                            event_name = ""
                            event_id = ""
                            data_lines = []
                            continue
                        try:
                            payload = json.loads("\n".join(data_lines))
                        except (json.JSONDecodeError, TypeError):
                            LOGGER.warning(
                                "ignored malformed WeFlow push event %r",
                                event_name,
                            )
                        else:
                            if isinstance(payload, dict):
                                payload["event"] = event_name
                                try:
                                    message_timestamp = int(
                                        payload.get("timestamp", 0)
                                    )
                                except (TypeError, ValueError):
                                    message_timestamp = 0
                                stale_replay = (
                                    message_timestamp > 0
                                    and message_timestamp
                                    < process_started_at - 3
                                )
                                if stale_replay:
                                    LOGGER.info(
                                        "skipped stale WeFlow replay event=%r",
                                        event_name,
                                    )
                                elif seen.add(payload):
                                    settings = load_settings()
                                    enabled = (
                                        env_enabled(
                                            "ENABLE_BROWSER_NOTIFICATIONS",
                                            True,
                                        )
                                        and settings["enabled"]
                                        and settings["apps"].get(
                                            "wechat", False
                                        )
                                    )
                                    title, body = message_notification(payload)
                                    if enabled:
                                        raw_id = str(
                                            payload.get("rawid", "")
                                        ).strip()
                                        relay.publish(
                                            {
                                                "id": (
                                                    f"{event_name}:{raw_id}"
                                                    if raw_id
                                                    else event_id
                                                ),
                                                "app": "wechat",
                                                "title": title,
                                                "body": body,
                                            }
                                        )
                                    relay.weflow_push_status = {
                                        "stage": (
                                            "event-forwarded"
                                            if enabled
                                            else "event-suppressed"
                                        ),
                                        "lastEvent": {
                                            "event": event_name,
                                            "timestamp": int(time.time()),
                                        },
                                        "lastError": None,
                                    }
                                    LOGGER.info(
                                        "WeFlow push event=%r "
                                        "browser_forwarded=%s",
                                        event_name,
                                        enabled,
                                    )
                        event_name = ""
                        event_id = ""
                        data_lines = []
            except (ClientError, asyncio.TimeoutError, OSError) as error:
                relay.weflow_push_status = {
                    "stage": "error",
                    "lastEvent": relay.weflow_push_status.get("lastEvent"),
                    "lastError": type(error).__name__,
                }
                LOGGER.warning(
                    "WeFlow push stream disconnected: %s",
                    type(error).__name__,
                )
                await asyncio.sleep(WEFLOW_PUSH_RECONNECT_SECONDS)


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
    application.router.add_get("/events", relay.events)
    application.router.add_get("/config", relay.config)
    application.router.add_get("/health", relay.health)
    application.router.add_post("/client-status", relay.client_status)
    runner = web.AppRunner(application, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, LISTEN_HOST, LISTEN_PORT)
    await site.start()
    push_task = asyncio.create_task(consume_weflow_push(relay))
    ready.set()
    LOGGER.info(
        "notification bridge listening on http://%s:%s",
        LISTEN_HOST,
        LISTEN_PORT,
    )
    try:
        await asyncio.Event().wait()
    finally:
        push_task.cancel()
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
