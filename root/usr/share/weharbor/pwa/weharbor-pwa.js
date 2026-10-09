(() => {
  "use strict";
  const script = document.currentScript;
  const base = new URL("./", script ? script.src : window.location.href);
  const standalone = () => window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: fullscreen)").matches || navigator.standalone === true;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  let installPrompt = null;
  let button;
  let help;
  let dismissed = false;
  const refresh = () => {
    if (button) button.hidden = dismissed || standalone() || !window.isSecureContext ||
      !(installPrompt || ios);
  };

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    refresh();
  });
  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    if (help && help.open) help.close();
    dismissed = true;
    refresh();
  });
  window.matchMedia("(display-mode: standalone)").addEventListener("change", refresh);

  const mount = () => {
    const styles = document.createElement("style");
    styles.textContent = '#weharbor-install[hidden]{display:none!important}' +
      '#weharbor-install{position:fixed;right:16px;bottom:16px;z-index:2147483000;' +
      'padding:10px 16px;border:1px solid #68dfc3;border-radius:12px;background:#101c2d;' +
      'color:#edf5fc;font:14px system-ui;cursor:pointer;box-shadow:0 4px 18px #0005}' +
      '#weharbor-install-help{max-width:360px;margin:auto;padding:24px;border:1px solid #38506b;' +
      'border-radius:16px;background:#101c2d;color:#edf5fc;font:16px/1.6 system-ui}' +
      '#weharbor-install-help::backdrop{background:#0008}' +
      '#weharbor-install-help button{padding:8px 14px;border:0;border-radius:8px;cursor:pointer}';
    document.head.appendChild(styles);
    button = document.createElement("button");
    button.id = "weharbor-install";
    button.type = "button";
    button.textContent = "安装 WeHarbor";
    button.hidden = true;
    button.addEventListener("click", async () => {
      if (!installPrompt) {
        if (!help) {
          help = document.createElement("dialog");
          help.id = "weharbor-install-help";
          const title = document.createElement("h2");
          title.textContent = "安装 WeHarbor";
          const text = document.createElement("p");
          text.textContent = "在 Safari 中打开此页面，点击分享按钮，再选择“添加到主屏幕”。添加后可从桌面打开 WeHarbor。";
          const close = document.createElement("button");
          close.textContent = "知道了";
          close.type = "button";
          close.addEventListener("click", () => help.close());
          help.append(title, text, close);
          document.body.appendChild(help);
        }
        help.showModal();
        return;
      }
      const prompt = installPrompt;
      installPrompt = null;
      refresh();
      try {
        await prompt.prompt();
        const choice = await prompt.userChoice;
        if (choice.outcome === "accepted") dismissed = true;
      } catch (error) {
        console.warn("WeHarbor install prompt unavailable", error);
      }
      refresh();
    });
    document.body.appendChild(button);
    refresh();
    if (window.isSecureContext && "serviceWorker" in navigator) {
      navigator.serviceWorker.register(new URL("weharbor-sw.js", base), {
        scope: base.pathname, updateViaCache: "none"
      }).then((registration) => registration.update()).catch((error) => {
        console.warn("WeHarbor service worker unavailable", error);
      });
    }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, {once: true});
  else mount();
})();
