(() => {
  'use strict';
  // https://user:pass@host/ breaks every relative fetch() ("Request cannot be constructed
  // from a URL that includes credentials"). Chrome hides the userinfo from location.href but
  // keeps it in document.URL / document.baseURI, which relative URLs (and iframe src) resolve
  // against, so test document.URL. The browser keeps the Basic auth, so reload clean before
  // any iframe exists.
  try {
    const here = new URL(document.URL);
    if (here.username || here.password) {
      here.username = ''; here.password = '';
      location.replace(here.href);
      return;
    }
  } catch {}
  // Pure helpers (exported on window.WeHarborDock for tests and debugging).
  const VIEW_ORDER = ['desktop', 'analysis', 'magpie', 'assistant', 'connections'];
  const VIEW_ICONS = {desktop: '💬', analysis: '📊', magpie: '🛡️', assistant: '🤖', connections: '🔗'};
  const NEAR_PX = 56, COLLAPSE_DELAY_MS = 400;
  const isMac = /Mac|iPhone|iPad/.test(globalThis.navigator?.platform || globalThis.navigator?.userAgent || '');
  const SHORTCUT_PREFIX = isMac ? '⌃⌥⇧' : 'Ctrl+Alt+Shift+';
  // Ctrl+Alt+Shift (+Digit / Backquote / Space): unused by browsers, WeChat and Selkies' own
  // Ctrl+Shift hotkeys. Matched by physical key code so keyboard layouts don't matter.
  const matchShortcut = (event) => {
    if (!event || !event.ctrlKey || !event.altKey || !event.shiftKey || event.metaKey) return null;
    const digit = /^(?:Digit|Numpad)([1-9])$/.exec(event.code || '');
    if (digit) { const view = VIEW_ORDER[Number(digit[1]) - 1]; return view ? {type: 'view', view} : null; }
    if (event.code === 'Backquote') return {type: 'cycle'};
    if (event.code === 'Space') return {type: 'panel'};
    return null;
  };
  const nextView = (current, step = 1) => {
    const index = VIEW_ORDER.indexOf(current);
    return VIEW_ORDER[((index < 0 ? 0 : index) + step + VIEW_ORDER.length) % VIEW_ORDER.length];
  };
  // Distance (px) from a point to a rectangle; 0 when inside.
  const distanceToRect = (x, y, rect) => Math.hypot(
    Math.max(rect.left - x, 0, x - rect.right), Math.max(rect.top - y, 0, y - rect.bottom));
  const shortcutLabel = (view) => SHORTCUT_PREFIX + (VIEW_ORDER.indexOf(view) + 1);
  const logic = {VIEW_ORDER, NEAR_PX, COLLAPSE_DELAY_MS, matchShortcut, nextView, distanceToRect, shortcutLabel};
  const dock = {logic, handleShortcut: null};
  globalThis.WeHarborDock = dock;
  const readShortcutsEnabled = () => {
    try { return JSON.parse(localStorage.getItem('weharbor-dock-shortcuts')) !== false; } catch { return true; }
  };
  const swallowed = new Set();
  // Capture-phase listener on a window, installed before Selkies wires its own window
  // listeners, so matched keys never reach the remote desktop.
  const hookKeys = (target) => {
    if (!target || target.__weharborDockKeys) return;
    try {
      target.__weharborDockKeys = true;
      target.addEventListener('keydown', (event) => {
        const action = matchShortcut(event);
        if (!action || !dock.handleShortcut || !readShortcutsEnabled()) return;
        event.preventDefault(); event.stopImmediatePropagation();
        swallowed.add(event.code);
        if (!event.repeat) dock.handleShortcut(action);
      }, true);
      target.addEventListener('keyup', (event) => {
        if (!swallowed.delete(event.code)) return;
        event.preventDefault(); event.stopImmediatePropagation();
      }, true);
    } catch {}
  };
  dock.hookKeys = hookKeys;
  if (globalThis.window && typeof window.addEventListener === 'function') hookKeys(window);
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
      #weharbor-apps-button{position:fixed;width:10px;height:52px;padding:0;margin:0;z-index:2147483000;
        display:flex;align-items:center;justify-content:center;overflow:hidden;
        border:1px solid #6d93b8;border-radius:6px;background:#294662cc;color:#e7f1fa;
        cursor:grab;touch-action:none;box-shadow:0 1px 7px #0004;
        transition:width .18s ease,height .18s ease,margin .18s ease,border-radius .18s ease,background .15s,box-shadow .18s}
      #weharbor-apps-button:hover,#weharbor-apps-button:focus-visible{background:#527ea7}
      #weharbor-apps-button:focus-visible{outline:2px solid #b9dfff;outline-offset:2px}
      #weharbor-apps-button::after{content:'⋮';font:18px system-ui}
      #weharbor-apps-button .dock-icon{display:none;font:20px/1 system-ui;pointer-events:none}
      #weharbor-apps-button.expanded{width:42px;height:42px;margin:5px 6px;border-radius:50%;
        background:#294662f2;box-shadow:0 3px 14px #0006}
      #weharbor-apps-button.expanded::after{content:none}
      #weharbor-apps-button.expanded .dock-icon{display:block}
      #weharbor-apps-button.dragging{cursor:grabbing;transition:none}
      @media (prefers-reduced-motion:reduce){#weharbor-apps-button{transition:none}}
      #weharbor-apps .app-shortcuts{margin:8px 0 0;color:#bccddd;font-size:12px}
      #weharbor-apps kbd{font:11px ui-monospace,monospace;border:1px solid #38506b;border-radius:4px;padding:0 3px}
      #weharbor-workspace-frames{position:fixed;inset:0;z-index:2147482900;background:#f8fafc}
      #weharbor-workspace-frames[hidden]{display:none}
      #weharbor-workspace-frames iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:#f8fafc}
      #weharbor-workspace-frames iframe[hidden]{display:none}
      #weharbor-apps .workspace-views{display:grid;gap:8px;margin-bottom:16px}
      #weharbor-apps [data-view]{min-height:44px;text-align:left;display:flex;align-items:center;justify-content:space-between}
      #weharbor-apps [data-view][aria-pressed=true]{border-color:#76c7ab;background:#234c48}
      #weharbor-apps .workspace-caption{color:#bccddd;font-size:12px;margin:0 0 6px}
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
      #weharbor-apps .app-install{margin-top:12px}
      #weharbor-apps #weharbor-install{min-height:36px;padding:6px 10px;font-size:12px;
        background:transparent;color:#bccddd}
    `;
    document.head.appendChild(style);
    const launcher = document.createElement('button');
    launcher.id = 'weharbor-apps-button';
    launcher.type = 'button';
    launcher.innerHTML = '<span class="dock-icon" aria-hidden="true"></span>';
    const launcherIcon = launcher.firstChild;
    const updateLauncherTitle = () => {
      const keys = readShortcutsEnabled() ? '（' + SHORTCUT_PREFIX + 'Space）' : '';
      launcher.title = '应用管理' + keys + ' · 拖动可调整位置';
      launcher.setAttribute('aria-label', '打开应用管理' + keys + '，拖动可调整位置');
    };
    updateLauncherTitle();
    launcher.setAttribute('aria-expanded', 'false');
    launcher.setAttribute('aria-controls', 'weharbor-apps');
    const panel = document.createElement('section');
    panel.id = 'weharbor-apps';
    panel.hidden = true;
    panel.setAttribute('aria-labelledby', 'weharbor-apps-title');
    panel.innerHTML = `<header><h2 id="weharbor-apps-title">应用管理</h2>
      <button type="button" data-close aria-label="收起应用管理">×</button></header>
      <p class="workspace-caption">全屏工作区</p>
      <nav class="workspace-views" aria-label="工作区切换">
        <button type="button" data-view="desktop" aria-pressed="true">微信桌面<span>Selkies</span></button>
        <button type="button" data-view="analysis" aria-pressed="false">数据分析<span>聊天与媒体</span></button>
        <button type="button" data-view="magpie" aria-pressed="false">Magpie 网关<span>模型与本地脱敏</span></button>
        <button type="button" data-view="assistant" aria-pressed="false">DeepSeek 助手<span>AI 对话</span></button>
        <button type="button" data-view="connections" aria-pressed="false">连接与操作记录<span>网络 · MCP</span></button>
      </nav>
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
        <label><input type="checkbox" data-setting="alpha">Alpha 通知</label>
        <label><input type="checkbox" data-local="shortcuts">启用切换快捷键（本浏览器）</label>
        <p class="app-shortcuts" data-shortcut-help></p></div>
      <p class="app-feedback" role="status" aria-live="polite"></p>
      <div class="app-install"><button type="button" id="weharbor-install" hidden>安装 WeHarbor</button></div>`;
    const feedback = panel.querySelector('.app-feedback');
    const shortcutHelp = panel.querySelector('[data-shortcut-help]');
    const shortcutToggle = panel.querySelector('[data-local="shortcuts"]');
    const renderShortcuts = () => {
      const enabled = readShortcutsEnabled();
      shortcutToggle.checked = enabled;
      for (const button of panel.querySelectorAll('[data-view]')) {
        button.title = enabled ? '快捷键 ' + shortcutLabel(button.dataset.view) : '';
      }
      shortcutHelp.innerHTML = enabled
        ? '快捷键：<kbd>' + SHORTCUT_PREFIX + '1–' + VIEW_ORDER.length + '</kbd> 切换视图，<kbd>' + SHORTCUT_PREFIX +
          '`</kbd> 轮换，<kbd>' + SHORTCUT_PREFIX + 'Space</kbd> 打开/收起本面板'
        : '切换快捷键已关闭。';
      updateLauncherTitle();
    };
    shortcutToggle.addEventListener('change', () => {
      write('weharbor-dock-shortcuts', shortcutToggle.checked);
      renderShortcuts();
    });
    const frames = document.createElement('div');
    frames.id = 'weharbor-workspace-frames';
    frames.hidden = true;
    const views = {analysis: ['/analysis/', '微信数据分析'], magpie: ['/magpie/', 'Magpie 网关'], assistant: ['/assistant/', 'DeepSeek 助手'],
      connections: ['/workspace/', '连接与操作记录']};
    let currentView = 'desktop';
    const showView = (view) => {
      if (view !== 'desktop' && !views[view]) return;
      currentView = view;
      launcherIcon.textContent = VIEW_ICONS[view] || '⋮';
      for (const child of [...document.body.children]) {
        if ([launcher, panel, frames, style].includes(child) || ['SCRIPT', 'STYLE'].includes(child.tagName)) continue;
        if (view !== 'desktop') {
          if (!child.hasAttribute('data-weharbor-inert')) {
            child.dataset.weharborInert = child.inert ? 'true' : 'false';
            child.inert = true;
          }
        } else if (child.hasAttribute('data-weharbor-inert')) {
          child.inert = child.dataset.weharborInert === 'true';
          delete child.dataset.weharborInert;
        }
      }
      if (view !== 'desktop' && !frames.querySelector('[data-frame="' + view + '"]')) {
        const frame = document.createElement('iframe');
        frame.dataset.frame = view; frame.src = views[view][0]; frame.title = views[view][1];
        frame.referrerPolicy = 'same-origin';
        // Same-origin views: forward shortcuts and proximity tracking from inside the frame.
        frame.addEventListener('load', () => {
          try { hookKeys(frame.contentWindow); hookPointer(frame.contentWindow); } catch {}
        });
        frames.appendChild(frame);
      }
      for (const frame of frames.children) frame.hidden = frame.dataset.frame !== view;
      frames.hidden = view === 'desktop';
      for (const button of panel.querySelectorAll('[data-view]')) button.setAttribute('aria-pressed', String(button.dataset.view === view));
      write('weharbor-workspace-view', view);
      close();
      if (view !== 'desktop') frames.querySelector('[data-frame="' + view + '"]').focus();
      else launcher.focus();
    };
    panel.addEventListener('click', (event) => {
      const button = event.target.closest('[data-view]');
      if (button) showView(button.dataset.view);
    });
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
      if (!panel.hidden) setTimeout(() => scheduleCollapse(), 0);
      panel.hidden = true;
      launcher.setAttribute('aria-expanded', 'false');
      clearInterval(timer); timer = null;
      if (focus) launcher.focus();
    };
    const request = async (path, action, payload = {}) => {
      const response = await fetch(new URL('/notifications/' + path, location.origin), {
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
    const openPanel = async () => {
      panel.hidden = false;
      launcher.setAttribute('aria-expanded', 'true');
      feedback.textContent = '';
      position();
      setExpanded(true);
      renderShortcuts();
      timer = setInterval(refresh, 2000);
      await refresh();
      try {
        settings = await request('config');
        notificationAvailable = settings.available !== false;
        render();
      } catch (error) { feedback.textContent = error.message; }
    };
    launcher.addEventListener('click', async () => {
      if (suppressClick) { suppressClick = false; return; }
      if (!panel.hidden) { close(); return; }
      await openPanel();
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
          showView('desktop');
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
    // Proximity expansion: collapsed handle grows into a round button when the pointer nears it.
    let expanded = false, collapseTimer = null, touchExpandedAt = 0;
    const setExpanded = (value) => {
      clearTimeout(collapseTimer); collapseTimer = null;
      if (expanded === value) return;
      expanded = value;
      launcher.classList.toggle('expanded', value);
    };
    const scheduleCollapse = (delay = COLLAPSE_DELAY_MS) => {
      if (!expanded || collapseTimer) return;
      collapseTimer = setTimeout(() => {
        collapseTimer = null;
        if (drag || !panel.hidden || launcher.matches(':hover')) return;
        setExpanded(false);
      }, delay);
    };
    const collapsedRect = () => {
      // Measure against the collapsed footprint so the zone doesn't grow with the circle.
      const rect = launcher.getBoundingClientRect();
      if (!expanded) return rect;
      const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
      const left = side === 'left' ? 0 : innerWidth - 10;
      return {left, right: left + 10, top: cy - 26, bottom: cy + 26, cx};
    };
    const onPointerMove = (event) => {
      if (launcher.hidden || drag || event.pointerType === 'touch') return;
      const near = distanceToRect(event.clientX, event.clientY, collapsedRect()) <= (expanded ? NEAR_PX + 16 : NEAR_PX);
      if (near) setExpanded(true);
      else scheduleCollapse();
    };
    const onPointerDownAnywhere = (event) => {
      if (launcher.hidden || event.pointerType === 'mouse') return;
      // Touch/pen: tapping the screen edge next to the handle expands it.
      if (distanceToRect(event.clientX, event.clientY, collapsedRect()) <= NEAR_PX / 2) {
        if (!expanded) touchExpandedAt = Date.now();
        setExpanded(true);
        clearTimeout(collapseTimer); collapseTimer = null;
        setTimeout(() => scheduleCollapse(0), 3500);
      }
    };
    function hookPointer(target) {
      if (!target || target.__weharborDockPointer) return;
      try {
        target.__weharborDockPointer = true;
        // Passive, no capture of the pointer: only observes, never alters input forwarding.
        target.addEventListener('pointermove', onPointerMove, {capture: true, passive: true});
        target.addEventListener('pointerdown', onPointerDownAnywhere, {capture: true, passive: true});
        target.document?.documentElement?.addEventListener('mouseleave', () => scheduleCollapse(), {passive: true});
      } catch {}
    }
    hookPointer(window);
    launcher.addEventListener('pointerleave', () => scheduleCollapse(), {passive: true});
    launcher.addEventListener('focus', () => {
      try { if (launcher.matches(':focus-visible')) setExpanded(true); } catch {}
    });
    launcher.addEventListener('blur', () => scheduleCollapse());
    launcher.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      suppressClick = false;
      // First tap on a still-collapsed handle (touch) only expands it.
      if (event.pointerType !== 'mouse' && (!expanded || Date.now() - touchExpandedAt < 350)) {
        touchExpandedAt = 0; setExpanded(true); suppressClick = true; return;
      }
      setExpanded(true);
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY, moved: false};
      launcher.setPointerCapture(event.pointerId);
    });
    launcher.addEventListener('pointermove', (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 6) drag.moved = true;
      if (!drag.moved) return;
      close();
      launcher.classList.add('dragging');
      launcher.style.left = Math.max(0, Math.min(innerWidth - 54, event.clientX - 27)) + 'px';
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
      launcher.classList.remove('dragging');
      position();
      scheduleCollapse(1200);
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
    document.body.append(frames, launcher, panel);
    window.dispatchEvent(new CustomEvent('weharbor:apps-ready'));
    position();
    showView(read('weharbor-workspace-view', 'desktop'));
    renderShortcuts();
    dock.handleShortcut = (action) => {
      if (launcher.hidden) return;
      if (action.type === 'panel') {
        if (panel.hidden) { openPanel(); panel.querySelector('[data-view][aria-pressed=true]')?.focus(); }
        else close(currentView === 'desktop');
        return;
      }
      showView(action.type === 'cycle' ? nextView(currentView) : action.view);
      // Hand keyboard focus back to the stream instead of leaving it on the dock button.
      if (currentView === 'desktop') launcher.blur();
      setExpanded(true); scheduleCollapse(1200);
    };
    addEventListener('resize', position);
    request('config').then((config) => {
      if (config.appSwitcherEnabled === false) { close(); launcher.hidden = true; }
    }).catch(() => {});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
