#!/usr/bin/env python3
"""Shared persistent settings for the browser notification bridge."""

import json
import os
import tempfile
from pathlib import Path


CONFIG_PATH = Path("/config/.config/weflow/browser-notifications.json")
DEFAULT_SETTINGS = {
    "enabled": True,
    "apps": {
        "wechat": True,
        "weflow": True,
    },
}


def default_settings():
    return {
        "enabled": DEFAULT_SETTINGS["enabled"],
        "apps": dict(DEFAULT_SETTINGS["apps"]),
    }


def load_settings():
    settings = default_settings()
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return settings

    if not isinstance(loaded, dict):
        return settings
    if isinstance(loaded.get("enabled"), bool):
        settings["enabled"] = loaded["enabled"]
    apps = loaded.get("apps")
    if isinstance(apps, dict):
        for app_name in settings["apps"]:
            if isinstance(apps.get(app_name), bool):
                settings["apps"][app_name] = apps[app_name]
    return settings


def save_settings(settings):
    normalized = default_settings()
    normalized["enabled"] = bool(settings.get("enabled", True))
    apps = settings.get("apps", {})
    for app_name in normalized["apps"]:
        normalized["apps"][app_name] = bool(apps.get(app_name, True))

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{CONFIG_PATH.name}.",
        suffix=".tmp",
        dir=CONFIG_PATH.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(normalized, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, CONFIG_PATH)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
    return normalized


def ensure_settings():
    if CONFIG_PATH.exists():
        return load_settings()
    return save_settings(default_settings())
