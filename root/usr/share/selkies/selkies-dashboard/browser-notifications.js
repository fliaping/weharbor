(() => {
  "use strict";

  const endpoint = (name) =>
    new URL(`/notifications/${name}`, window.location.origin).toString();
  let source = null;
  let reconnectTimer = null;
  const activeNotifications = new Map();
  const clientIdKey = "browser-notification-client-id";
  let clientId = sessionStorage.getItem(clientIdKey);
  if (!clientId) {
    clientId =
      globalThis.crypto?.randomUUID?.() ||
      `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    sessionStorage.setItem(clientIdKey, clientId);
  }

  function report(stage, details = {}) {
    const payload = {
      clientId,
      stage,
      supported: "Notification" in window,
      permission:
        "Notification" in window ? Notification.permission : "unsupported",
      secureContext: window.isSecureContext,
      visibility: document.visibilityState,
      ...details,
    };
    fetch(endpoint("client-status"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  }

  function createPermissionPrompt() {
    if (
      !("Notification" in window) ||
      Notification.permission !== "default" ||
      document.getElementById("browser-notification-permission")
    ) {
      return;
    }

    const prompt = document.createElement("button");
    prompt.id = "browser-notification-permission";
    prompt.type = "button";
    prompt.textContent = "启用消息通知";
    Object.assign(prompt.style, {
      position: "fixed",
      top: "12px",
      left: "50%",
      transform: "translateX(-50%)",
      zIndex: "2147483647",
      padding: "8px 14px",
      border: "1px solid rgba(255,255,255,.28)",
      borderRadius: "18px",
      color: "#fff",
      background: "rgba(23,26,32,.94)",
      boxShadow: "0 4px 16px rgba(0,0,0,.28)",
      font: "13px system-ui,sans-serif",
      cursor: "pointer",
    });
    prompt.addEventListener("click", async () => {
      const permission = await Notification.requestPermission();
      report("permission-result", { permission });
      prompt.remove();
      if (permission === "granted") {
        connect();
      }
    });
    document.body.appendChild(prompt);
  }

  function showNotification(payload) {
    report("event-received");
    if (
      !("Notification" in window) ||
      Notification.permission !== "granted"
    ) {
      report("event-blocked");
      createPermissionPrompt();
      return;
    }

    const key = `${payload.app}:${payload.id}`;
    const previous = activeNotifications.get(key);
    if (previous) previous.close();
    let notification;
    try {
      notification = new Notification(payload.title || payload.app, {
        body: payload.body || "",
        icon: new URL("icon.png", document.baseURI).toString(),
        tag: key,
        renotify: true,
        requireInteraction: false,
        silent: false,
      });
      report("notification-created");
    } catch (error) {
      report("notification-create-error", { error: String(error) });
      return;
    }
    activeNotifications.set(key, notification);
    notification.addEventListener("show", () => {
      report("notification-shown");
    });
    notification.addEventListener("error", (event) => {
      report("notification-error", {
        error: String(event?.message || event?.type || "unknown"),
      });
    });
    notification.addEventListener("click", () => {
      window.focus();
      notification.close();
    });
    notification.addEventListener("close", () => {
      if (activeNotifications.get(key) === notification) {
        activeNotifications.delete(key);
      }
    });
  }

  function connect() {
    if (
      source ||
      !("Notification" in window) ||
      Notification.permission !== "granted"
    ) {
      return;
    }
    report("sse-connecting");
    source = new EventSource(endpoint("events"));
    source.onopen = () => {
      report("sse-open");
    };
    source.addEventListener("notification", (event) => {
      try {
        showNotification(JSON.parse(event.data));
      } catch (error) {
        console.warn("Invalid browser notification payload", error);
        report("invalid-event", { error: String(error) });
      }
    });
    source.onerror = () => {
      report("sse-error");
      source.close();
      source = null;
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, 3000);
    };
  }

  async function start() {
    report("loaded");
    if (!("Notification" in window)) return;
    try {
      const response = await fetch(endpoint("config"), {
        cache: "no-store",
      });
      const config = await response.json();
      if (!config.available) {
        report("bridge-disabled");
        return;
      }
    } catch (error) {
      report("config-error", { error: String(error) });
      return;
    }
    if (Notification.permission === "granted") {
      connect();
    } else if (Notification.permission === "default") {
      createPermissionPrompt();
    }
  }

  document.addEventListener("visibilitychange", () => {
    report("visibility-change");
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
