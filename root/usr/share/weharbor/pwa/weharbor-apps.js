(() => {
  'use strict';
  const mount = () => {
    if (document.getElementById('weharbor-apps-button')) return;
    const read = (key, fallback) => {
      try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
    };
    const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };
    const stored = read('weharbor-dock-position', {});
    let side = stored.side === 'left' ? 'left' : 'right';
    let fraction = Number.isFinite(stored.fraction) ? Math.max(0, Math.min(1, stored.fraction)) : .42;
    const style = document.createElement('style');
    style.textContent = `
      #weharbor-apps-button{position:fixed;width:10px;height:52px;padding:0;z-index:2147483000;
        border:1px solid #6d93b8;border-radius:6px;background:#294662cc;color:#e7f1fa;
        cursor:grab;touch-action:none;box-shadow:0 1px 7px #0004;transition:background .15s}
      #weharbor-apps-button:hover,#weharbor-apps-button:focus-visible{background:#527ea7}
      #weharbor-apps-button:focus-visible{outline:2px solid #b9dfff;outline-offset:2px}
      #weharbor-apps-button::after{content:'⋮';font:18px system-ui}
      #weharbor-apps{position:fixed;z-index:2147483001;width:min(300px,calc(100vw - 36px));
        max-height:calc(100dvh - 24px);overflow:auto;box-sizing:border-box;padding:16px;
        border:1px solid #38506b;border-radius:14px;background:#101c2df5;color:#edf5fc;
        box-shadow:0 8px 30px #0005;font:14px/1.5 system-ui}
      #weharbor-apps[hidden]{display:none}
      #weharbor-apps h2{margin:0;font-size:16px}
      #weharbor-apps header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
      #weharbor-apps button{border:1px solid #38506b;border-radius:8px;background:#20354c;
        color:inherit;cursor:pointer;font:inherit;padding:7px 10px}
      #weharbor-apps button:disabled{opacity:.55;cursor:wait}
      #weharbor-apps button:focus-visible{outline:2px solid #b9dfff}
      #weharbor-apps .app-row{display:flex;gap:8px;margin-top:12px}
      #weharbor-apps .app-switch{flex:1;display:flex;align-items:center;justify-content:space-between}
      #weharbor-apps .app-switch.active{border-color:#76c7ab;background:#234c48}
      #weharbor-apps .app-status{font-size:12px;color:#bccddd}
      #weharbor-apps details{margin:6px 0;color:#bccddd;font-size:12px}
      #weharbor-apps summary{cursor:pointer;padding:4px 0}
      #weharbor-apps .app-windows{display:grid;gap:4px;margin:5px 0}
      #weharbor-apps .app-windows button{text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      #weharbor-apps .app-windows button.active{border-color:#76c7ab}
      #weharbor-apps .app-feedback{margin:10px 0 0;white-space:pre-wrap;font-size:12px}
      #weharbor-apps .app-hint{margin:10px 0;color:#bccddd;font-size:12px}
      #weharbor-apps .app-settings{margin-top:14px;border-top:1px solid #38506b;padding-top:10px}
      #weharbor-apps label{display:flex;align-items:center;gap:7px;padding:4px 0}
      #weharbor-apps input{accent-color:#76c7ab}
    `;
    document.head.appendChild(style);
    const launcher = document.createElement('button');
    launcher.id = 'weharbor-apps-button';
    launcher.type = 'button';
    launcher.title = '应用管理 · 拖动可调整位置';
    launcher.setAttribute('aria-label', '打开应用管理，拖动可调整位置');
    launcher.setAttribute('aria-expanded', 'false');
    launcher.setAttribute('aria-controls', 'weharbor-apps');
    const panel = document.createElement('section');
    panel.id = 'weharbor-apps';
    panel.hidden = true;
    panel.setAttribute('aria-labelledby', 'weharbor-apps-title');
    panel.innerHTML = `<header><h2 id="weharbor-apps-title">应用管理</h2>
      <button type="button" data-close aria-label="收起应用管理">×</button></header>
      <div class="app-row"><button type="button" class="app-switch" data-app="wechat" data-action="switch">
        <span>微信</span><span class="app-status" data-status="wechat">…</span></button>
        <button type="button" data-app="wechat" data-action="restart" title="重启微信" aria-label="重启微信">↻</button></div>
      <details data-windows="wechat"><summary>微信窗口</summary><div class="app-windows"></div></details>
      <div class="app-row"><button type="button" class="app-switch" data-app="alpha" data-action="switch">
        <span>Alpha</span><span class="app-status" data-status="alpha">…</span></button>
        <button type="button" data-app="alpha" data-action="restart" title="重启 Alpha" aria-label="重启 Alpha">↻</button></div>
      <details data-windows="alpha"><summary>Alpha 窗口</summary><div class="app-windows"></div></details>
      <p class="app-hint">点击应用切换；再次点击可轮换窗口。重启前请保存未发送的内容。</p>
      <div class="app-settings"><label><input type="checkbox" data-setting="enabled">浏览器通知</label>
        <label><input type="checkbox" data-setting="wechat">微信通知</label>
        <label><input type="checkbox" data-setting="alpha">Alpha 通知</label></div>
      <p class="app-feedback" role="status" aria-live="polite"></p>`;
    const feedback = panel.querySelector('.app-feedback');
    let busy = false, refreshing = false, timer = null, drag = null, suppressClick = false;
    let status = {}, settings = {}, notificationAvailable = false;
    const position = () => {
      const top = Math.max(8, Math.min(innerHeight - 60, fraction * Math.max(0, innerHeight - 52)));
      launcher.style.top = top + 'px';
      launcher.style.left = side === 'left' ? '0' : '';
      launcher.style.right = side === 'right' ? '0' : '';
      panel.style.left = side === 'left' ? '18px' : '';
      panel.style.right = side === 'right' ? '18px' : '';
      panel.style.top = Math.max(12, Math.min(top, innerHeight - panel.offsetHeight - 12)) + 'px';
    };
    const close = (focus = false) => {
      panel.hidden = true;
      launcher.setAttribute('aria-expanded', 'false');
      clearInterval(timer); timer = null;
      if (focus) launcher.focus();
    };
    const request = async (path, action, payload = {}) => {
      const response = await fetch('/notifications/' + path, {
        credentials: 'same-origin', cache: 'no-store',
        ...(action ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-WeHarbor-Action': action},
          body: JSON.stringify(payload), signal: AbortSignal.timeout(30000)} : {})
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || '无法连接应用管理服务，请稍后重试。');
      return result;
    };
    const render = () => {
      for (const app of ['wechat', 'alpha']) {
        const state = status[app] || {};
        panel.querySelector('[data-status="' + app + '"]').textContent =
          state.restarting ? '处理中' : state.active ? '当前应用' : state.running ? '运行中' : '点击启动';
        panel.querySelector('.app-switch[data-app="' + app + '"]').classList.toggle('active', !!state.active);
        const list = panel.querySelector('[data-windows="' + app + '"] .app-windows');
        const windows = state.windows || [];
        const signature = JSON.stringify(windows);
        if (list.dataset.signature !== signature) {
          list.dataset.signature = signature;
          list.replaceChildren();
          for (const window of windows) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = window.title + (window.minimized ? ' · 已最小化' : '');
            button.title = window.title;
            button.classList.toggle('active', !!window.active);
            button.dataset.app = app;
            button.dataset.action = 'switch';
            button.dataset.windowId = String(window.id);
            list.appendChild(button);
          }
          if (!windows.length) list.textContent = '暂无窗口';
        }
      }
      for (const button of panel.querySelectorAll('[data-action]')) {
        button.disabled = busy || !!status[button.dataset.app]?.restarting;
      }
      for (const input of panel.querySelectorAll('[data-setting]')) {
        input.checked = input.dataset.setting === 'enabled' ? !!settings.enabled : !!settings.apps?.[input.dataset.setting];
        input.disabled = busy || !notificationAvailable;
      }
      position();
    };
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try { status = await request('apps'); render(); }
      catch (error) { feedback.textContent = error.message; }
      finally { refreshing = false; }
    };
    launcher.addEventListener('click', async () => {
      if (suppressClick) { suppressClick = false; return; }
      if (!panel.hidden) { close(); return; }
      panel.hidden = false;
      launcher.setAttribute('aria-expanded', 'true');
      feedback.textContent = '';
      position();
      timer = setInterval(refresh, 2000);
      await refresh();
      try {
        settings = await request('config');
        notificationAvailable = settings.available !== false;
        render();
      } catch (error) { feedback.textContent = error.message; }
    });
    panel.addEventListener('click', async (event) => {
      const button = event.target.closest('[data-action]');
      if (!button || busy || button.disabled) return;
      const app = button.dataset.app, action = button.dataset.action;
      const name = app === 'wechat' ? '微信' : 'Alpha';
      busy = true; render();
      feedback.textContent = name + (action === 'restart' ? '正在重启，请稍候…' : '正在切换…');
      try {
        const result = await request('apps/' + app + '/' + action, action,
          button.dataset.windowId ? {windowId: Number(button.dataset.windowId)} : {});
        feedback.textContent = name + (action === 'restart' ? '已重新启动。' : '已切换。');
        if (action === 'switch') {
          if (result.windowId) { close(); document.activeElement?.blur(); }
          else feedback.textContent = name + '正在准备窗口，窗口出现后请再次点击。';
        }
      } catch (error) {
        feedback.textContent = error.name === 'TimeoutError' ? '等待超时，请稍后查看应用状态。' : error.message;
      } finally { busy = false; await refresh(); }
    });
    panel.addEventListener('change', async (event) => {
      const input = event.target.closest('[data-setting]');
      if (!input || busy) return;
      const key = input.dataset.setting;
      const payload = key === 'enabled' ? {enabled: input.checked} : {apps: {[key]: input.checked}};
      busy = true; render();
      try { settings = await request('app-settings', 'settings', payload); feedback.textContent = '通知设置已保存。'; }
      catch (error) { feedback.textContent = error.message; }
      finally { busy = false; render(); }
    });
    panel.querySelector('[data-close]').addEventListener('click', () => close(true));
    launcher.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      suppressClick = false;
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY, moved: false};
      launcher.setPointerCapture(event.pointerId);
    });
    launcher.addEventListener('pointermove', (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 6) drag.moved = true;
      if (!drag.moved) return;
      close();
      launcher.style.left = Math.max(0, Math.min(innerWidth - 10, event.clientX - 5)) + 'px';
      launcher.style.right = '';
      launcher.style.top = Math.max(8, Math.min(innerHeight - 60, event.clientY - 26)) + 'px';
    });
    const finishDrag = (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      if (drag.moved) {
        side = event.clientX < innerWidth / 2 ? 'left' : 'right';
        fraction = Math.max(0, Math.min(1, (event.clientY - 26) / Math.max(1, innerHeight - 52)));
        write('weharbor-dock-position', {side, fraction});
        suppressClick = true;
      }
      drag = null;
      position();
    };
    launcher.addEventListener('pointerup', finishDrag);
    launcher.addEventListener('pointercancel', finishDrag);
    document.addEventListener('pointerdown', (event) => {
      if (!panel.hidden && !panel.contains(event.target) && event.target !== launcher) close();
    });
    panel.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(true); });
    launcher.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(true); });
    // Keep dock interactions out of the remote desktop's input handlers.
    for (const element of [launcher, panel]) {
      for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'mousedown', 'mousemove',
        'mouseup', 'click', 'dblclick', 'keydown', 'keyup', 'wheel', 'touchstart', 'touchmove', 'touchend', 'contextmenu']) {
        element.addEventListener(type, (event) => event.stopPropagation());
      }
    }
    document.body.append(launcher, panel);
    position();
    addEventListener('resize', position);
    request('config').then((config) => {
      if (config.appSwitcherEnabled === false) { close(); launcher.hidden = true; }
    }).catch(() => {});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
