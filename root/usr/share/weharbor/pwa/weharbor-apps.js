(() => {
  'use strict';
  // https://user:pass@host/ breaks every relative fetch(). Chrome hides userinfo from
  // location.href but keeps it in document.URL / document.baseURI, so test document.URL.
  try {
    const here = new URL(document.URL);
    if (here.username || here.password) {
      here.username = ''; here.password = '';
      location.replace(here.href);
      return;
    }
  } catch {}

  const VIEW_ORDER = ['desktop', 'analysis', 'magpie', 'assistant', 'connections'];
  const VIEW_META = {
    desktop: {label: '微信', hint: '官方桌面', icon: 'chat', path: null},
    analysis: {label: '分析', hint: '聊天与媒体', icon: 'chart', path: '/analysis/'},
    magpie: {label: 'Magpie', hint: '模型网关', icon: 'shield', path: '/magpie/'},
    assistant: {label: '助手', hint: 'DeepSeek', icon: 'sparkles', path: '/assistant/'},
    connections: {label: '连接', hint: '网络 · MCP', icon: 'plug', path: '/workspace/'},
  };
  const NEAR_PX = 56, COLLAPSE_DELAY_MS = 400;
  const isMac = /Mac|iPhone|iPad/.test(globalThis.navigator?.platform || globalThis.navigator?.userAgent || '');
  const SHORTCUT_PREFIX = isMac ? '⌥' : 'Alt+';
  // Two-key shortcuts: Alt/Option + Digit1-5 / Digit0 / Backquote / Space. Matched by
  // physical key code. Only Alt alone counts (not Ctrl+Alt/AltGr, Shift, Meta, numpad).
  const SHORTCUT_KEYS = {Digit0: {type: 'panel'}, Space: {type: 'panel'}, Backquote: {type: 'cycle'}};
  const matchShortcut = (event) => {
    if (!event || !event.altKey || event.ctrlKey || event.shiftKey || event.metaKey || event.isComposing) return null;
    const code = event.code || '';
    const digit = /^Digit([1-9])$/.exec(code);
    if (digit) { const view = VIEW_ORDER[Number(digit[1]) - 1]; return view ? {type: 'view', view} : null; }
    return SHORTCUT_KEYS[code] ? {...SHORTCUT_KEYS[code]} : null;
  };
  const nextView = (current, step = 1) => {
    const index = VIEW_ORDER.indexOf(current);
    return VIEW_ORDER[((index < 0 ? 0 : index) + step + VIEW_ORDER.length) % VIEW_ORDER.length];
  };
  const distanceToRect = (x, y, rect) => Math.hypot(
    Math.max(rect.left - x, 0, x - rect.right), Math.max(rect.top - y, 0, y - rect.bottom));
  const shortcutLabel = (view) => SHORTCUT_PREFIX + (VIEW_ORDER.indexOf(view) + 1);
  const logic = {VIEW_ORDER, VIEW_META, NEAR_PX, COLLAPSE_DELAY_MS, matchShortcut, nextView, distanceToRect, shortcutLabel};
  const dock = {logic, handleShortcut: null};
  globalThis.WeHarborDock = dock;

  const readShortcutsEnabled = () => {
    try { return JSON.parse(localStorage.getItem('weharbor-dock-shortcuts')) !== false; } catch { return true; }
  };
  const swallowed = new Set();
  const hookKeys = (target) => {
    if (!target || target.__weharborDockKeys) return;
    try {
      target.__weharborDockKeys = true;
      target.addEventListener('keydown', (event) => {
        // Command palette: Ctrl/⌘+K (not an Alt shortcut).
        if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && (event.code === 'KeyK' || event.key === 'k' || event.key === 'K')) {
          if (dock.openPalette) {
            event.preventDefault(); event.stopImmediatePropagation();
            dock.openPalette();
            return;
          }
        }
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

  // Line icons (24px grid, stroke = currentColor) so the chrome renders the same on every OS.
  const ICON_PATHS = {
    chat: '<path d="M20.5 11.5a8.5 8.5 0 0 1-12.3 7.6L3.5 20.5l1.4-4.4A8.5 8.5 0 1 1 20.5 11.5Z"/><path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01"/>',
    chart: '<path d="M3.5 3.5v17h17"/><path d="M8 16v-4.5M12.5 16V8M17 16v-6.5"/>',
    shield: '<path d="M12 3 5 6v5.2c0 4.3 2.9 8 7 9.8 4.1-1.8 7-5.5 7-9.8V6l-7-3Z"/><path d="m9.2 12 2 2 3.8-3.9"/>',
    sparkles: '<path d="M11 3.5 12.9 8.6 18 10.5l-5.1 1.9L11 17.5l-1.9-5.1L4 10.5l5.1-1.9L11 3.5Z"/><path d="m18.5 15 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z"/>',
    plug: '<path d="M9 7.5V3M15 7.5V3"/><path d="M6 7.5h12v3.5a6 6 0 0 1-12 0V7.5Z"/><path d="M12 17v4"/>',
    box: '<path d="M20.5 7.8 12 3.3 3.5 7.8v8.4l8.5 4.5 8.5-4.5V7.8Z"/><path d="m3.5 7.8 8.5 4.5 8.5-4.5M12 12.3v8.4"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    command: '<path d="M9 6.5A2.5 2.5 0 1 0 6.5 9H17.5A2.5 2.5 0 1 0 15 6.5v11a2.5 2.5 0 1 0 2.5-2.5h-11A2.5 2.5 0 1 0 9 17.5v-11Z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
    moon: '<path d="M20 14.6A8 8 0 1 1 9.4 4a6.3 6.3 0 0 0 10.6 10.6Z"/>',
    settings: '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
    monitor: '<rect x="3" y="4" width="18" height="12.5" rx="2"/><path d="M8.5 20.5h7M12 16.5v4"/>',
    columns: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M14 4v16"/>',
    maximize: '<path d="M8.5 3.5h-3a2 2 0 0 0-2 2v3M15.5 3.5h3a2 2 0 0 1 2 2v3M8.5 20.5h-3a2 2 0 0 1-2-2v-3M15.5 20.5h3a2 2 0 0 0 2-2v-3"/>',
    minimize: '<path d="M8.5 3.5v3a2 2 0 0 1-2 2h-3M15.5 3.5v3a2 2 0 0 0 2 2h3M8.5 20.5v-3a2 2 0 0 0-2-2h-3M15.5 20.5v-3a2 2 0 0 1 2-2h3"/>',
    close: '<path d="M18 6 6 18M6 6l12 12"/>',
    external: '<path d="M14 4h6v6M20 4l-8.5 8.5"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
    refresh: '<path d="M20 11.5A8 8 0 1 0 17.7 17"/><path d="M20 4.5v7h-7"/>',
    alert: '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v4.5M12 16h.01"/>',
    corner: '<path d="m9 10-5 5 5 5"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/>',
  };
  const icon = (name, size = 18) => '<svg class="wh-svg" width="' + size + '" height="' + size +
    '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    (ICON_PATHS[name] || '') + '</svg>';
  const MOD_KEY = isMac ? '⌘' : 'Ctrl';
  const SEARCH_KEYWORDS = {
    desktop: 'wechat weixin wx 桌面', analysis: 'analysis fenxi fx 聊天 媒体', magpie: 'magpie gateway 网关 脱敏 tuomin',
    assistant: 'assistant zhushou zs deepseek ai', connections: 'connections lianjie lj mcp network 网络',
  };

  const mount = () => {
    if (document.getElementById('weharbor-shell')) return;
    const read = (key, fallback) => {
      try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
    };
    const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };

    const darkQuery = matchMedia('(prefers-color-scheme: dark)');
    let onThemeApplied = () => {};
    const applyTheme = (pref) => {
      const dark = pref === 'dark' || (pref === 'system' && darkQuery.matches);
      document.documentElement.dataset.weharborTheme = dark ? 'dark' : 'light';
      document.documentElement.classList.add('weharbor-unified');
      onThemeApplied(pref, dark);
    };
    applyTheme(read('weharbor-theme', 'system'));
    try { darkQuery.addEventListener('change', () => applyTheme(read('weharbor-theme', 'system'))); } catch {}

    const SIDE_DEFAULT = 420;
    let sideWidth = Math.max(320, Math.min(720, Number(read('weharbor-side-width', SIDE_DEFAULT)) || SIDE_DEFAULT));
    let layout = read('weharbor-layout', {mode: 'desktop', side: 'assistant'}); // mode: desktop | split | focus
    if (!VIEW_META[layout.side] || layout.side === 'desktop') layout.side = 'assistant';
    if (!['desktop', 'split', 'focus'].includes(layout.mode)) layout.mode = 'desktop';
    let currentView = layout.mode === 'desktop' ? 'desktop' : layout.side;
    const mobileQuery = matchMedia('(max-width: 720px)');
    let mobile = mobileQuery.matches;

    const style = document.createElement('style');
    style.textContent = `
:root, html[data-weharbor-theme=light]{
  --wh-bg:#f3f5f8; --wh-surface:#ffffff; --wh-surface-2:#f1f4f8; --wh-hover:#e9eef4; --wh-ink:#0f1a2a; --wh-muted:#5d6b7c; --wh-faint:#8a96a5;
  --wh-line:#dde3ea; --wh-line-strong:#c9d2dd; --wh-accent:#0a7ea4; --wh-accent-ink:#ffffff; --wh-accent-soft:#e1f2f8; --wh-ok:#16a34a; --wh-warn:#d97706;
  --wh-danger:#dc2626; --wh-tip-bg:#0f1a2a; --wh-tip-ink:#f4f7fb; --wh-scrim:#0f1a2a59; --wh-stage:#0d1422;
  --wh-rail:56px; --wh-top:48px; --wh-side:0px; --wh-bottom:0px; --wh-radius:12px;
  --wh-shadow:0 1px 2px #0f1a2a14,0 12px 32px -6px #0f1a2a2e; --wh-shadow-lg:0 2px 6px #0f1a2a14,0 24px 64px -12px #0f1a2a4d;
  --wh-font:system-ui,-apple-system,"Segoe UI","PingFang SC","Noto Sans SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;
  --wh-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; --wh-ease:cubic-bezier(.2,.8,.2,1); color-scheme:light;
}
html[data-weharbor-theme=dark]{
  --wh-bg:#0a0f18; --wh-surface:#111824; --wh-surface-2:#172131; --wh-hover:#1d293b; --wh-ink:#e6edf6; --wh-muted:#97a6b8; --wh-faint:#6b7a8d;
  --wh-line:#222e40; --wh-line-strong:#2e3c52; --wh-accent:#4cc3e6; --wh-accent-ink:#04202b; --wh-accent-soft:#13324200; --wh-ok:#4ade80; --wh-warn:#fbbf24;
  --wh-danger:#f87171; --wh-tip-bg:#e6edf6; --wh-tip-ink:#0a0f18; --wh-scrim:#02050a99; --wh-stage:#0a0f18;
  --wh-shadow:0 1px 2px #0006,0 12px 32px -6px #000a; --wh-shadow-lg:0 2px 6px #0006,0 24px 64px -12px #000c; color-scheme:dark;
}
html[data-weharbor-theme=dark]{--wh-accent-soft:#12303f}
html.weharbor-unified, html.weharbor-unified body{height:100%;margin:0;overflow:hidden;background:var(--wh-bg);font-family:var(--wh-font);color:var(--wh-ink)}
html.weharbor-unified #app{
  position:fixed!important;left:var(--wh-rail)!important;top:var(--wh-top)!important;right:var(--wh-side)!important;bottom:var(--wh-bottom)!important;
  width:auto!important;height:auto!important;overflow:hidden;z-index:1;background:var(--wh-stage);
  display:flex!important;align-items:stretch;justify-content:stretch;border-radius:0;
}
html.weharbor-unified #app .video-container,
html.weharbor-unified #app #videoStream,
html.weharbor-unified #app #videoCanvas,
html.weharbor-unified #app #videoWorkerCanvas,
html.weharbor-unified #app #overlayInput{
  position:absolute!important;inset:0!important;width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;
  object-fit:fill!important;border-radius:0!important;margin:0!important;
}
/* Hide leftover Selkies chrome: the notification CTA was a full-pane translucent
   rounded button that covered the rail; dashboard overlays are replaced by our shell. */
html.weharbor-unified #browser-notification-permission,
html.weharbor-unified #playButton,
html.weharbor-unified .notification-container,
html.weharbor-unified #status-display{display:none!important}
html.weharbor-unified #root,
html.weharbor-unified #dashboard-root,
html.weharbor-unified #touch-gamepad-host{
  position:fixed!important;left:var(--wh-rail)!important;top:var(--wh-top)!important;right:var(--wh-side)!important;bottom:var(--wh-bottom)!important;
  width:auto!important;height:auto!important;pointer-events:none!important;z-index:2;opacity:0!important;
}
html.weharbor-unified.weharbor-focus #app,
html.weharbor-unified.weharbor-focus #root,
html.weharbor-unified.weharbor-focus #dashboard-root,
html.weharbor-unified.weharbor-focus #touch-gamepad-host{visibility:hidden}
html.weharbor-unified.weharbor-resizing #app,html.weharbor-unified.weharbor-resizing #weharbor-side iframe{pointer-events:none}
html.weharbor-unified.weharbor-resizing{cursor:col-resize}
#weharbor-shell{position:fixed;inset:0;z-index:2147482900;pointer-events:none;font:13px/1.45 var(--wh-font);color:var(--wh-ink);-webkit-font-smoothing:antialiased}
#weharbor-shell *{box-sizing:border-box}
#weharbor-shell .wh-chrome{pointer-events:auto}
#weharbor-shell .wh-svg{display:block;flex:none}
#weharbor-shell button,#weharbor-shell a.wh-icon-btn{appearance:none;border:1px solid transparent;background:transparent;color:inherit;cursor:pointer;font:inherit;border-radius:8px;
  transition:background-color .15s var(--wh-ease),color .15s var(--wh-ease),border-color .15s var(--wh-ease),box-shadow .15s var(--wh-ease)}
#weharbor-shell button:disabled{cursor:default;opacity:.55}
#weharbor-shell :is(button,a,input,summary):focus-visible{outline:2px solid var(--wh-accent);outline-offset:2px}
#weharbor-shell kbd{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 5px;font:500 11px/1 var(--wh-mono);color:var(--wh-muted);
  background:var(--wh-surface-2);border:1px solid var(--wh-line);border-bottom-width:2px;border-radius:5px}
#weharbor-shell .wh-icon-btn{width:30px;height:30px;display:inline-grid;place-items:center;color:var(--wh-muted);text-decoration:none}
#weharbor-shell .wh-icon-btn:hover{background:var(--wh-hover);color:var(--wh-ink)}

/* Rail */
#weharbor-rail{position:absolute;left:0;top:0;bottom:var(--wh-bottom);width:var(--wh-rail);display:flex;flex-direction:column;align-items:center;gap:4px;padding:6px 0 10px;background:var(--wh-surface);border-right:1px solid var(--wh-line);z-index:5}
#weharbor-rail .wh-brand{width:34px;height:34px;margin:1px 0 9px;border-radius:10px;background:linear-gradient(145deg,#0a7ea4,#14b8a6);color:#fff;display:grid;place-items:center;font-weight:700;font-size:15px;box-shadow:inset 0 1px 0 #ffffff40,0 2px 6px #0a7ea440}
#weharbor-rail .wh-nav{display:flex;flex-direction:column;gap:4px;width:100%;align-items:center;flex:1}
#weharbor-rail .wh-sep{width:24px;height:1px;background:var(--wh-line);margin:6px 0}
#weharbor-rail .wh-rail-foot{display:flex;flex-direction:column;gap:2px;align-items:center}
#weharbor-rail button.wh-nav-btn{width:40px;height:40px;display:grid;place-items:center;position:relative;color:var(--wh-muted);border-radius:10px}
#weharbor-rail button.wh-nav-btn:hover{background:var(--wh-hover);color:var(--wh-ink)}
#weharbor-rail button.wh-nav-btn[aria-pressed=true]{color:var(--wh-ink);background:var(--wh-surface-2)}
#weharbor-rail button.wh-nav-btn[aria-current=true]{color:var(--wh-accent);background:var(--wh-accent-soft)}
#weharbor-rail .wh-ind{position:absolute;left:-8px;top:50%;width:3px;height:0;border-radius:0 3px 3px 0;background:var(--wh-accent);transform:translateY(-50%);transition:height .2s var(--wh-ease)}
#weharbor-rail [aria-pressed=true] .wh-ind{height:8px;background:var(--wh-faint)}
#weharbor-rail [aria-current=true] .wh-ind{height:20px;background:var(--wh-accent)}
#weharbor-rail [data-tip]::after{content:attr(data-tip);position:absolute;left:calc(100% + 12px);top:50%;transform:translate(-4px,-50%);opacity:0;pointer-events:none;white-space:pre;
  padding:6px 9px;border-radius:7px;background:var(--wh-tip-bg);color:var(--wh-tip-ink);font:500 12px/1.3 var(--wh-font);box-shadow:var(--wh-shadow);
  transition:opacity .12s var(--wh-ease),transform .12s var(--wh-ease);z-index:10}
#weharbor-rail [data-tip]:hover::after,#weharbor-rail [data-tip]:focus-visible::after{opacity:1;transform:translate(0,-50%);transition-delay:.35s}

/* Top bar */
#weharbor-top{position:absolute;left:var(--wh-rail);right:0;top:0;height:var(--wh-top);display:flex;align-items:center;gap:10px;padding:0 10px 0 16px;background:var(--wh-surface);border-bottom:1px solid var(--wh-line);z-index:3;min-width:0}
#weharbor-top .wh-title{display:flex;align-items:baseline;gap:8px;min-width:0;white-space:nowrap}
#weharbor-top .wh-title strong{font-weight:650;font-size:14px;letter-spacing:-.01em}
#weharbor-top .wh-title-cn{font-weight:500;color:var(--wh-muted);margin-left:2px}
#weharbor-top .wh-crumb{color:var(--wh-muted);overflow:hidden;text-overflow:ellipsis}
#weharbor-top .wh-crumb::before{content:"/";margin-right:8px;color:var(--wh-line-strong)}
#weharbor-top .wh-search{display:flex;align-items:center;gap:8px;width:clamp(180px,22vw,280px);height:32px;margin-left:12px;padding:0 6px 0 10px;
  border:1px solid var(--wh-line);background:var(--wh-surface-2);color:var(--wh-faint);border-radius:8px;text-align:left}
#weharbor-top .wh-search span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#weharbor-top .wh-search:hover{border-color:var(--wh-line-strong);color:var(--wh-muted)}
#weharbor-top .wh-spacer{flex:1}
#weharbor-top .wh-chips{display:flex;gap:2px;min-width:0}
#weharbor-top .wh-chip{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 9px;border-radius:7px;color:var(--wh-muted);white-space:nowrap;font-size:12px}
#weharbor-top .wh-chip:hover{background:var(--wh-hover);color:var(--wh-ink)}
#weharbor-shell .wh-dot{width:7px;height:7px;border-radius:50%;background:var(--wh-faint);flex:none}
#weharbor-shell [data-state=ok] .wh-dot{background:var(--wh-ok);box-shadow:0 0 0 3px color-mix(in srgb,var(--wh-ok) 18%,transparent)}
#weharbor-shell [data-state=warn] .wh-dot{background:var(--wh-warn);box-shadow:0 0 0 3px color-mix(in srgb,var(--wh-warn) 20%,transparent)}
#weharbor-shell [data-state=busy] .wh-dot{background:var(--wh-warn);animation:wh-pulse 1.2s ease-in-out infinite}
#weharbor-shell [data-state=off] .wh-dot{background:transparent;box-shadow:inset 0 0 0 1.5px var(--wh-faint)}
#weharbor-top .wh-vsep{width:1px;height:20px;background:var(--wh-line);flex:none}
#weharbor-shell .wh-seg{display:inline-flex;padding:2px;gap:2px;border-radius:9px;background:var(--wh-surface-2);border:1px solid var(--wh-line)}
#weharbor-shell .wh-seg button{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 10px;border-radius:7px;color:var(--wh-muted);font-size:12px;white-space:nowrap}
#weharbor-shell .wh-seg button:hover{color:var(--wh-ink)}
#weharbor-shell .wh-seg button[aria-pressed=true]{background:var(--wh-surface);color:var(--wh-ink);border-color:var(--wh-line);box-shadow:0 1px 2px #0f1a2a1f}
html[data-weharbor-theme=dark] #weharbor-shell .wh-seg button[aria-pressed=true]{background:var(--wh-hover);border-color:var(--wh-line-strong)}
#weharbor-top .wh-mobile-only{display:none}

/* Side panel */
#weharbor-side{position:absolute;top:var(--wh-top);right:0;bottom:var(--wh-bottom);width:var(--wh-side);background:var(--wh-surface);border-left:1px solid var(--wh-line);display:flex;flex-direction:column;z-index:4;min-width:0}
#weharbor-side[hidden],#weharbor-resizer[hidden],#weharbor-bottom[hidden],#weharbor-apps[hidden],#weharbor-palette[hidden],#weharbor-shell [hidden]{display:none!important}
#weharbor-side .wh-side-head{display:flex;align-items:center;gap:10px;padding:0 8px 0 12px;height:44px;flex:none;border-bottom:1px solid var(--wh-line)}
#weharbor-side .wh-side-ico{width:26px;height:26px;border-radius:7px;display:grid;place-items:center;background:var(--wh-accent-soft);color:var(--wh-accent);flex:none}
#weharbor-side .wh-side-titles{display:flex;align-items:baseline;gap:8px;flex:1;min-width:0;white-space:nowrap}
#weharbor-side .wh-side-head h2{margin:0;font-size:13px;font-weight:650}
#weharbor-side .wh-side-hint{color:var(--wh-faint);font-size:12px;overflow:hidden;text-overflow:ellipsis}
#weharbor-side .wh-side-actions{display:flex;gap:2px}
#weharbor-side .wh-frame-host{position:relative;flex:1;min-height:0;background:var(--wh-bg)}
#weharbor-side iframe,#weharbor-workspace-frames iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:var(--wh-bg)}
#weharbor-side iframe[hidden],#weharbor-workspace-frames iframe[hidden]{display:none}
#weharbor-side .wh-state{position:absolute;inset:0;display:grid;place-content:center;justify-items:center;gap:10px;padding:24px;text-align:center;color:var(--wh-muted);background:var(--wh-bg);z-index:1}
#weharbor-side .wh-state strong{color:var(--wh-ink);font-size:14px;font-weight:600}
#weharbor-side .wh-state .wh-state-ico{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;background:var(--wh-surface-2);color:var(--wh-muted);border:1px solid var(--wh-line)}
#weharbor-side .wh-state[data-kind=error] .wh-state-ico{color:var(--wh-danger)}
#weharbor-side .wh-state button{margin-top:4px;height:30px;padding:0 12px;border:1px solid var(--wh-line);background:var(--wh-surface);border-radius:8px}
#weharbor-side .wh-state button:hover{background:var(--wh-hover)}
#weharbor-shell .wh-spinner{width:22px;height:22px;border-radius:50%;border:2px solid var(--wh-line-strong);border-top-color:var(--wh-accent);animation:wh-spin .8s linear infinite}
#weharbor-side .wh-state[data-kind=loading]{animation:wh-fade-in .2s .25s both}
#weharbor-resizer{position:absolute;top:var(--wh-top);bottom:var(--wh-bottom);width:10px;margin-right:-5px;cursor:col-resize;z-index:6;touch-action:none}
#weharbor-resizer::before{content:"";position:absolute;left:4px;top:0;bottom:0;width:2px;background:transparent;transition:background-color .15s .1s}
#weharbor-resizer::after{content:"";position:absolute;left:3px;top:50%;width:4px;height:32px;margin-top:-16px;border-radius:4px;background:var(--wh-line-strong);opacity:0;transition:opacity .15s}
#weharbor-resizer:hover::before,#weharbor-resizer.dragging::before{background:var(--wh-accent)}
#weharbor-resizer:hover::after{opacity:0}
#weharbor-workspace-frames{position:absolute;inset:0;z-index:0}

/* Mobile bottom navigation */
#weharbor-bottom{position:absolute;left:0;right:0;bottom:0;height:var(--wh-bottom);padding:0 4px env(safe-area-inset-bottom);display:flex;background:var(--wh-surface);border-top:1px solid var(--wh-line);z-index:3}
#weharbor-shell #weharbor-bottom button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;color:var(--wh-muted);font-size:11px;border-radius:0;border:0}
#weharbor-bottom .wh-pill{display:grid;place-items:center;width:52px;height:28px;border-radius:14px;transition:background-color .2s var(--wh-ease)}
#weharbor-shell #weharbor-bottom button[aria-current=true]{color:var(--wh-ink);font-weight:600}
#weharbor-bottom button[aria-current=true] .wh-pill{background:var(--wh-accent-soft);color:var(--wh-accent)}

/* App manager popover */
#weharbor-apps{position:absolute;z-index:2147483001;width:min(348px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;padding:6px 16px 16px;border:1px solid var(--wh-line);
  border-radius:14px;background:var(--wh-surface);box-shadow:var(--wh-shadow-lg);left:calc(var(--wh-rail) + 10px);bottom:12px;animation:wh-pop-in .16s var(--wh-ease);transform-origin:bottom left}
#weharbor-apps header{display:flex;align-items:center;justify-content:space-between;height:44px;margin:0 -6px 2px 0}
#weharbor-apps h2{margin:0;font-size:14px;font-weight:650}
#weharbor-apps .wh-sec{margin:14px 0 6px;color:var(--wh-faint);font-size:11px;font-weight:600;letter-spacing:.06em}
#weharbor-apps .app-card{border:1px solid var(--wh-line);border-radius:10px;background:var(--wh-surface-2);margin-top:8px;overflow:hidden}
#weharbor-apps .app-row{display:flex;align-items:center;gap:2px;padding:4px 4px 4px 4px}
#weharbor-shell #weharbor-apps .app-switch{flex:1;display:flex;align-items:center;gap:10px;min-height:40px;padding:0 8px;text-align:left;border-radius:7px}
#weharbor-shell #weharbor-apps .app-switch:hover:not(:disabled){background:var(--wh-hover)}
#weharbor-apps .app-ico{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;background:var(--wh-surface);border:1px solid var(--wh-line);color:var(--wh-muted)}
#weharbor-apps .app-switch.active .app-ico{color:var(--wh-accent);border-color:color-mix(in srgb,var(--wh-accent) 40%,var(--wh-line))}
#weharbor-apps .app-name{font-weight:600;flex:1}
#weharbor-apps .app-status{display:inline-flex;align-items:center;gap:6px;color:var(--wh-muted);font-size:12px}
#weharbor-apps [data-action=restart][data-state=busy] .wh-svg{animation:wh-spin 1s linear infinite}
#weharbor-apps details{border-top:1px solid var(--wh-line);font-size:12px;color:var(--wh-muted)}
#weharbor-apps summary{cursor:pointer;padding:7px 12px;list-style:none;display:flex;align-items:center;gap:6px;user-select:none}
#weharbor-apps summary::-webkit-details-marker{display:none}
#weharbor-apps summary::before{content:"";width:5px;height:5px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(-45deg);transition:transform .15s}
#weharbor-apps details[open] summary::before{transform:rotate(45deg)}
#weharbor-apps summary:hover{color:var(--wh-ink)}
#weharbor-apps .app-windows{display:grid;gap:2px;padding:0 6px 8px}
#weharbor-shell #weharbor-apps .app-windows button{text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:5px 8px;border-radius:6px;color:var(--wh-ink)}
#weharbor-shell #weharbor-apps .app-windows button:hover{background:var(--wh-hover)}
#weharbor-shell #weharbor-apps .app-windows button.active{color:var(--wh-accent);font-weight:600}
#weharbor-apps .app-windows:not(:has(button)){padding:0 12px 8px;color:var(--wh-faint)}
#weharbor-apps .app-hint{margin:10px 2px 0;color:var(--wh-faint);font-size:12px}
#weharbor-apps .wh-switch{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:34px;cursor:pointer}
#weharbor-apps .wh-switch input{appearance:none;flex:none;width:32px;height:18px;margin:0;border-radius:9px;background:var(--wh-line-strong);position:relative;cursor:pointer;transition:background-color .15s}
#weharbor-apps .wh-switch input::after{content:"";position:absolute;left:2px;top:2px;width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 1px 2px #0004;transition:transform .18s var(--wh-ease)}
#weharbor-apps .wh-switch input:checked{background:var(--wh-accent)}
#weharbor-apps .wh-switch input:checked::after{transform:translateX(14px)}
#weharbor-apps .wh-switch input:disabled{opacity:.5;cursor:default}
#weharbor-apps .wh-field{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:38px}
#weharbor-apps .wh-seg label{position:relative}
#weharbor-apps .wh-seg input{position:absolute;opacity:0;pointer-events:none}
#weharbor-apps .wh-seg label span{display:inline-flex;align-items:center;height:26px;padding:0 10px;border-radius:7px;border:1px solid transparent;color:var(--wh-muted);font-size:12px;cursor:pointer}
#weharbor-apps .wh-seg label:hover span{color:var(--wh-ink)}
#weharbor-apps .wh-seg input:checked + span{background:var(--wh-surface);color:var(--wh-ink);border-color:var(--wh-line);box-shadow:0 1px 2px #0f1a2a1f}
html[data-weharbor-theme=dark] #weharbor-apps .wh-seg input:checked + span{background:var(--wh-hover);border-color:var(--wh-line-strong)}
#weharbor-apps .wh-seg input:focus-visible + span{outline:2px solid var(--wh-accent);outline-offset:1px}
#weharbor-apps .app-shortcuts{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;align-items:center;margin:10px 0 0;padding:10px 12px;border-radius:10px;background:var(--wh-surface-2);color:var(--wh-muted);font-size:12px}
#weharbor-apps .app-shortcuts .wh-keys{display:flex;gap:3px;justify-self:end}
#weharbor-apps .app-feedback{margin:10px 0 0;white-space:pre-wrap;font-size:12px;color:var(--wh-muted)}
#weharbor-apps .app-feedback:empty{display:none}
#weharbor-shell #weharbor-install{margin-top:12px;width:100%;height:34px;border:1px solid var(--wh-line);background:var(--wh-surface-2);border-radius:8px;font-weight:600}
#weharbor-shell #weharbor-install:hover{background:var(--wh-hover)}

/* Command palette */
#weharbor-palette{position:absolute;inset:0;z-index:2147483010;display:grid;place-items:start center;padding-top:min(14vh,120px);background:var(--wh-scrim);animation:wh-fade-in .12s ease-out}
#weharbor-palette .wh-pal{width:min(600px,calc(100vw - 24px));background:var(--wh-surface);border:1px solid var(--wh-line);border-radius:14px;box-shadow:var(--wh-shadow-lg);overflow:hidden;animation:wh-pop-in .16s var(--wh-ease);transform-origin:top center}
#weharbor-palette .wh-pal-search{display:flex;align-items:center;gap:10px;padding:0 14px 0 16px;height:54px;border-bottom:1px solid var(--wh-line);color:var(--wh-faint)}
#weharbor-shell #weharbor-palette input{flex:1;min-width:0;border:0;padding:0;font:15px var(--wh-font);background:transparent;color:var(--wh-ink);outline:none}
#weharbor-palette input::placeholder{color:var(--wh-faint)}
#weharbor-palette input::-webkit-search-cancel-button{display:none}
#weharbor-palette ul{list-style:none;margin:0;padding:6px;max-height:min(540px,62vh);overflow:auto;scroll-padding:30px 0 6px}
#weharbor-palette .wh-pal-group{padding:10px 10px 4px;color:var(--wh-faint);font-size:11px;font-weight:600;letter-spacing:.06em}
#weharbor-shell #weharbor-palette li button{width:100%;display:flex;align-items:center;gap:12px;height:42px;padding:0 10px;border-radius:9px;text-align:left;color:var(--wh-ink)}
#weharbor-palette .wh-pal-ico{width:28px;height:28px;border-radius:7px;display:grid;place-items:center;color:var(--wh-muted);background:var(--wh-surface-2);border:1px solid var(--wh-line);flex:none}
#weharbor-palette .wh-pal-label{font-weight:500}
#weharbor-palette .wh-pal-hint{color:var(--wh-faint);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#weharbor-palette .wh-pal-tag{font-size:11px;padding:1px 6px;border-radius:5px;color:var(--wh-accent);background:var(--wh-accent-soft)}
#weharbor-palette .wh-pal-meta{margin-left:auto;display:flex;gap:3px;flex:none}
#weharbor-shell #weharbor-palette li button[aria-selected=true]{background:var(--wh-hover)}
#weharbor-palette li button[aria-selected=true] .wh-pal-ico{color:var(--wh-accent);border-color:color-mix(in srgb,var(--wh-accent) 35%,var(--wh-line))}
#weharbor-palette .wh-pal-empty{padding:28px 12px;text-align:center;color:var(--wh-faint)}
#weharbor-palette .wh-pal-foot{display:flex;gap:16px;padding:8px 14px;border-top:1px solid var(--wh-line);color:var(--wh-faint);font-size:12px;background:var(--wh-surface-2)}
#weharbor-palette .wh-pal-foot span{display:inline-flex;align-items:center;gap:5px}
#weharbor-palette .wh-pal-foot kbd{min-width:18px;height:18px;background:var(--wh-surface)}

@keyframes wh-spin{to{transform:rotate(360deg)}}
@keyframes wh-pulse{50%{opacity:.35}}
@keyframes wh-fade-in{from{opacity:0}}
@keyframes wh-pop-in{from{opacity:0;transform:scale(.97) translateY(-4px)}}

@media (max-width:1280px){#weharbor-top .wh-chip-label>span{display:none}}
@media (max-width:960px){
  #weharbor-top .wh-chip .wh-chip-label{display:none}
  #weharbor-top .wh-chip{padding:0 7px}
}
@media (max-width:1100px){
  #weharbor-top .wh-search{width:32px;padding:0;justify-content:center;margin-left:4px}
  #weharbor-top .wh-search span,#weharbor-top .wh-search kbd{display:none}
}
@media (max-width:900px){
  #weharbor-top .wh-seg button span{display:none}
  #weharbor-top .wh-seg button{padding:0 7px}
  #weharbor-top .wh-title-cn{font-weight:500;color:var(--wh-muted);margin-left:2px}
#weharbor-top .wh-crumb{display:none}
}
@media (max-width:720px){
  :root{--wh-rail:0px;--wh-bottom:56px}
  #weharbor-rail,#weharbor-resizer,#weharbor-top .wh-chips,#weharbor-top .wh-seg,#weharbor-top .wh-vsep,#weharbor-top .wh-search{display:none!important}
  #weharbor-top{left:0;padding:0 6px 0 14px}
  #weharbor-top .wh-title-cn{font-weight:500;color:var(--wh-muted);margin-left:2px}
#weharbor-top .wh-crumb{display:inline}
  #weharbor-top .wh-mobile-only{display:inline-grid}
  #weharbor-side{left:0!important;right:0;width:auto!important;border-left:0}
  #weharbor-side [data-action=focus-toggle]{display:none}
  #weharbor-apps{left:8px;right:8px;width:auto;bottom:calc(var(--wh-bottom) + 8px);transform-origin:bottom center}
  #weharbor-palette{padding-top:10px}
}
@media (prefers-reduced-motion:reduce){#weharbor-shell *,#weharbor-shell *::before,#weharbor-shell *::after{transition:none!important;animation:none!important}}
`;
    document.head.appendChild(style);

    const shell = document.createElement('div');
    shell.id = 'weharbor-shell';
    shell.innerHTML = `
<aside id="weharbor-rail" class="wh-chrome" aria-label="WeHarbor 导航">
  <div class="wh-brand" title="WeHarbor｜微港">微</div>
  <nav class="wh-nav" data-rail-nav></nav>
  <div class="wh-sep" aria-hidden="true"></div>
  <div class="wh-rail-foot">
    <button type="button" class="wh-nav-btn" data-action="palette" data-tip="命令面板  ${MOD_KEY}+K" aria-label="打开命令面板">${icon('command')}</button>
    <button type="button" class="wh-nav-btn" data-action="theme" data-tip="切换外观" aria-label="切换浅色/深色" data-theme-icon>${icon('moon')}</button>
    <button type="button" class="wh-nav-btn" id="weharbor-apps-button" data-action="settings" data-tip="应用管理  ${SHORTCUT_PREFIX}0" aria-label="打开应用管理" aria-controls="weharbor-apps" aria-expanded="false">${icon('settings')}</button>
  </div>
</aside>
<header id="weharbor-top" class="wh-chrome">
  <div class="wh-title"><strong>WeHarbor <span class="wh-title-cn">微港</span></strong><span class="wh-crumb" data-crumb></span></div>
  <button type="button" class="wh-search" data-action="palette" aria-label="打开命令面板">${icon('search', 15)}<span>搜索应用或命令…</span><kbd>${MOD_KEY}</kbd><kbd>K</kbd></button>
  <div class="wh-spacer"></div>
  <div class="wh-chips" data-chips aria-live="polite"></div>
  <div class="wh-vsep" aria-hidden="true"></div>
  <div class="wh-seg" role="group" aria-label="布局">
    <button type="button" data-action="layout-desktop" data-mode="desktop" title="仅显示微信 (${SHORTCUT_PREFIX}1)">${icon('monitor', 15)}<span>微信</span></button>
    <button type="button" data-action="split" data-mode="split" title="与微信并排">${icon('columns', 15)}<span>并排</span></button>
    <button type="button" data-action="focus" data-mode="focus" title="专注当前应用">${icon('maximize', 15)}<span>专注</span></button>
  </div>
  <button type="button" class="wh-icon-btn wh-mobile-only" data-action="palette" aria-label="打开命令面板">${icon('search')}</button>
  <button type="button" class="wh-icon-btn wh-mobile-only" data-action="settings" aria-label="打开应用管理">${icon('settings')}</button>
</header>
<div id="weharbor-resizer" class="wh-chrome" hidden title="拖动调整宽度，双击恢复默认" role="separator" aria-orientation="vertical"></div>
<section id="weharbor-side" class="wh-chrome" hidden aria-label="侧栏应用">
  <div class="wh-side-head">
    <span class="wh-side-ico" data-side-icon></span>
    <div class="wh-side-titles"><h2 data-side-title>助手</h2><span class="wh-side-hint" data-side-hint></span></div>
    <div class="wh-side-actions">
      <button type="button" class="wh-icon-btn" data-action="side-reload" title="重新加载" aria-label="重新加载">${icon('refresh', 16)}</button>
      <a class="wh-icon-btn" data-side-open href="#" target="_blank" rel="noopener" title="在新标签页打开" aria-label="在新标签页打开">${icon('external', 16)}</a>
      <button type="button" class="wh-icon-btn" data-action="focus-toggle" title="专注" aria-label="专注模式">${icon('maximize', 16)}</button>
      <button type="button" class="wh-icon-btn" data-action="close-side" title="关闭侧栏，回到微信" aria-label="关闭侧栏">${icon('close', 16)}</button>
    </div>
  </div>
  <div class="wh-frame-host" id="weharbor-workspace-frames">
    <div class="wh-state" data-kind="loading" data-loading hidden><span class="wh-spinner"></span><span data-loading-text>正在加载…</span></div>
    <div class="wh-state" data-kind="error" data-empty hidden><span class="wh-state-ico">${icon('alert', 22)}</span><strong>尚未加载</strong><span></span>
      <button type="button" data-action="side-reload">重试</button></div>
  </div>
</section>
<nav id="weharbor-bottom" class="wh-chrome" hidden aria-label="移动端导航"></nav>
<section id="weharbor-apps" class="wh-chrome" hidden aria-labelledby="weharbor-apps-title">
  <header><h2 id="weharbor-apps-title">应用管理</h2><button type="button" class="wh-icon-btn" data-close aria-label="收起">${icon('close', 16)}</button></header>
  <div class="app-card">
    <div class="app-row"><button type="button" class="app-switch" data-app="wechat" data-action="switch"><span class="app-ico">${icon('chat', 16)}</span><span class="app-name">微信</span><span class="app-status" data-status="wechat">…</span></button>
      <button type="button" class="wh-icon-btn" data-app="wechat" data-action="restart" title="重启微信" aria-label="重启微信">${icon('refresh', 16)}</button></div>
    <details data-windows="wechat"><summary>微信窗口</summary><div class="app-windows"></div></details>
  </div>
  <div class="app-card">
    <div class="app-row"><button type="button" class="app-switch" data-app="alpha" data-action="switch"><span class="app-ico">${icon('box', 16)}</span><span class="app-name">Alpha</span><span class="app-status" data-status="alpha">…</span></button>
      <button type="button" class="wh-icon-btn" data-app="alpha" data-action="restart" title="重启 Alpha" aria-label="重启 Alpha">${icon('refresh', 16)}</button></div>
    <details data-windows="alpha"><summary>Alpha 窗口</summary><div class="app-windows"></div></details>
  </div>
  <p class="app-hint">点击应用切换；再次点击可轮换窗口。重启前请保存未发送的内容。</p>
  <div class="app-settings">
    <div class="wh-sec">通知</div>
    <label class="wh-switch"><span>浏览器通知</span><input type="checkbox" role="switch" data-setting="enabled"></label>
    <label class="wh-switch"><span>微信通知</span><input type="checkbox" role="switch" data-setting="wechat"></label>
    <label class="wh-switch"><span>Alpha 通知</span><input type="checkbox" role="switch" data-setting="alpha"></label>
    <div class="wh-sec">偏好</div>
    <label class="wh-switch"><span>启用切换快捷键（本浏览器）</span><input type="checkbox" role="switch" data-local="shortcuts"></label>
    <div class="wh-field"><span>外观</span>
      <div class="wh-seg" role="radiogroup" aria-label="外观">
        <label><input type="radio" name="weharbor-theme" value="system" data-local="theme"><span>跟随系统</span></label>
        <label><input type="radio" name="weharbor-theme" value="light" data-local="theme"><span>浅色</span></label>
        <label><input type="radio" name="weharbor-theme" value="dark" data-local="theme"><span>深色</span></label>
      </div>
    </div>
    <div class="app-shortcuts" data-shortcut-help></div>
  </div>
  <p class="app-feedback" role="status" aria-live="polite"></p>
  <div class="app-install"><button type="button" id="weharbor-install" hidden>安装 WeHarbor</button></div>
</section>
<div id="weharbor-palette" class="wh-chrome" hidden role="dialog" aria-modal="true" aria-label="命令面板">
  <div class="wh-pal">
    <div class="wh-pal-search">${icon('search')}<input type="search" placeholder="搜索应用、布局或操作…" aria-label="命令搜索" autocomplete="off" spellcheck="false"
      role="combobox" aria-expanded="true" aria-controls="weharbor-palette-list"><kbd>Esc</kbd></div>
    <ul id="weharbor-palette-list" data-palette-list role="listbox" aria-label="命令"></ul>
    <div class="wh-pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd>选择</span><span><kbd>↵</kbd>执行</span><span><kbd>Esc</kbd>关闭</span></div>
  </div>
</div>`;
    document.body.appendChild(shell);

    const $ = (selector) => shell.querySelector(selector);
    const railNav = $('[data-rail-nav]');
    const bottom = $('#weharbor-bottom');
    const side = $('#weharbor-side');
    const frames = $('#weharbor-workspace-frames');
    const empty = frames.querySelector('[data-empty]');
    const loading = frames.querySelector('[data-loading]');
    const resizer = $('#weharbor-resizer');
    const panel = $('#weharbor-apps');
    const launcher = $('#weharbor-apps-button');
    const chips = $('[data-chips]');
    const crumb = $('[data-crumb]');
    const palette = $('#weharbor-palette');
    const paletteInput = palette.querySelector('input');
    const paletteList = palette.querySelector('[data-palette-list]');
    const sideTitle = $('[data-side-title]');
    const sideHint = $('[data-side-hint]');
    const sideIcon = $('[data-side-icon]');
    const sideOpen = $('[data-side-open]');
    const focusToggle = $('[data-action="focus-toggle"]');
    const themeButton = $('[data-theme-icon]');
    const feedback = panel.querySelector('.app-feedback');
    const shortcutHelp = panel.querySelector('[data-shortcut-help]');
    const shortcutToggle = panel.querySelector('[data-local="shortcuts"]');
    const themeInputs = [...panel.querySelectorAll('[data-local="theme"]')];

    onThemeApplied = (pref, dark) => {
      themeButton.innerHTML = icon(dark ? 'sun' : 'moon');
      themeButton.dataset.tip = dark ? '切换到浅色' : '切换到深色';
      for (const input of themeInputs) input.checked = input.value === pref;
    };
    applyTheme(read('weharbor-theme', 'system'));
    const toggleTheme = () => {
      const next = document.documentElement.dataset.weharborTheme === 'dark' ? 'light' : 'dark';
      write('weharbor-theme', next); applyTheme(next);
    };

    for (const view of VIEW_ORDER) {
      const meta = VIEW_META[view];
      const btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'wh-nav-btn'; btn.dataset.view = view;
      btn.setAttribute('aria-label', meta.label);
      btn.innerHTML = '<span class="wh-ind"></span>' + icon(meta.icon, 20);
      railNav.appendChild(btn);
      const m = document.createElement('button');
      m.type = 'button'; m.dataset.view = view;
      m.innerHTML = '<span class="wh-pill">' + icon(meta.icon, 20) + '</span><span>' + meta.label + '</span>';
      bottom.appendChild(m);
    }

    const stopChrome = (root) => {
      for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'mousedown', 'mousemove',
        'mouseup', 'click', 'dblclick', 'keydown', 'keyup', 'wheel', 'touchstart', 'touchmove', 'touchend', 'contextmenu']) {
        root.addEventListener(type, (event) => event.stopPropagation());
      }
    };
    stopChrome(shell);

    const rootStyle = document.documentElement.style;
    const syncLayoutVars = () => {
      mobile = mobileQuery.matches;
      const focus = layout.mode === 'focus' || (mobile && layout.mode !== 'desktop');
      const split = layout.mode === 'split' && !mobile;
      if (!mobile) sideWidth = Math.max(300, Math.min(sideWidth, Math.floor(innerWidth * 0.7)));
      rootStyle.setProperty('--wh-rail', mobile ? '0px' : '56px');
      rootStyle.setProperty('--wh-top', mobile ? '52px' : '48px');
      rootStyle.setProperty('--wh-bottom', mobile ? 'calc(56px + env(safe-area-inset-bottom))' : '0px');
      rootStyle.setProperty('--wh-side', split ? sideWidth + 'px' : '0px');
      document.documentElement.classList.toggle('weharbor-focus', focus);
      side.hidden = !(focus || split);
      side.style.left = focus ? (mobile ? '0' : 'var(--wh-rail)') : '';
      side.style.width = focus ? 'auto' : '';
      side.style.borderLeft = focus ? '0' : '';
      bottom.hidden = !mobile;
      resizer.hidden = !split;
      if (split) resizer.style.right = sideWidth + 'px';
    };
    // Selkies reads the video parent's getBoundingClientRect() on window.resize.
    // Fire a few delayed resize events after *our* layout changes (not from the
    // listener below) so the remote desktop tracks the pane without looping.
    let bumpTimer = 0;
    const bumpResolution = () => {
      const fire = () => window.dispatchEvent(new Event('resize'));
      clearTimeout(bumpTimer);
      requestAnimationFrame(fire);
      bumpTimer = setTimeout(fire, 120);
      setTimeout(fire, 400);
      setTimeout(fire, 900);
    };

    const sideFrame = () => frames.querySelector('[data-frame="' + layout.side + '"]');
    const renderFrameState = () => {
      const frame = layout.mode === 'desktop' ? null : sideFrame();
      const failed = frame?.dataset.failed === '1';
      empty.hidden = !failed;
      loading.hidden = !frame || failed || frame.dataset.loaded === '1';
      if (frame) loading.querySelector('[data-loading-text]').textContent = '正在加载' + VIEW_META[layout.side].label + '…';
    };
    const ensureFrame = (view) => {
      const meta = VIEW_META[view];
      if (!meta?.path) return null;
      let frame = frames.querySelector('[data-frame="' + view + '"]');
      if (!frame) {
        frame = document.createElement('iframe');
        frame.dataset.frame = view;
        frame.title = meta.label;
        frame.referrerPolicy = 'same-origin';
        frame.addEventListener('load', () => {
          // Ignore the synchronous about:blank load some engines fire on insertion.
          try { if (frame.contentWindow.location.href === 'about:blank') return; } catch {}
          try { hookKeys(frame.contentWindow); } catch {}
          frame.dataset.loaded = '1';
          delete frame.dataset.failed;
          renderFrameState();
        });
        frame.addEventListener('error', () => {
          frame.dataset.failed = '1';
          empty.querySelector('strong').textContent = meta.label + ' 加载失败';
          empty.querySelector('span:not(.wh-state-ico)').textContent = '请检查服务是否已启动，或稍后重试。';
          renderFrameState();
        });
        // Lazy: only views that have been shown get a frame; it stays alive when hidden.
        frame.src = meta.path;
        frames.appendChild(frame);
      }
      return frame;
    };
    const reloadSide = () => {
      const frame = sideFrame();
      if (!frame) return;
      delete frame.dataset.loaded; delete frame.dataset.failed;
      try { frame.contentWindow.location.reload(); } catch { frame.src = VIEW_META[layout.side].path; }
      renderFrameState();
    };

    const renderNav = () => {
      const primary = layout.mode === 'desktop' ? 'desktop' : layout.side;
      for (const btn of shell.querySelectorAll('[data-view]')) {
        const view = btn.dataset.view;
        const visible = view === primary || (layout.mode === 'split' && !mobile && view === 'desktop');
        btn.setAttribute('aria-current', String(view === primary));
        btn.setAttribute('aria-pressed', String(visible));
        if (btn.parentElement === railNav) {
          btn.dataset.tip = VIEW_META[view].label + ' · ' + VIEW_META[view].hint +
            (readShortcutsEnabled() ? '   ' + shortcutLabel(view) : '');
        }
      }
      for (const btn of shell.querySelectorAll('.wh-seg [data-mode]')) btn.setAttribute('aria-pressed', String(btn.dataset.mode === layout.mode));
      const meta = VIEW_META[layout.side];
      sideTitle.textContent = meta.label;
      sideHint.textContent = meta.hint;
      sideIcon.innerHTML = icon(meta.icon, 15);
      sideOpen.href = meta.path;
      const focused = layout.mode === 'focus';
      focusToggle.innerHTML = icon(focused ? 'minimize' : 'maximize', 16);
      focusToggle.title = focused ? '退出专注，与微信并排' : '专注（全屏此应用）';
      focusToggle.setAttribute('aria-label', focusToggle.title);
      crumb.textContent = layout.mode === 'desktop' ? '微信'
        : layout.mode === 'split' && !mobile ? '微信 + ' + meta.label : meta.label;
      for (const frame of frames.querySelectorAll('iframe')) {
        frame.hidden = !(layout.mode !== 'desktop' && frame.dataset.frame === layout.side);
      }
      renderFrameState();
    };

    const setLayout = (next) => {
      layout = {...layout, ...next};
      if (!VIEW_META[layout.side] || layout.side === 'desktop') layout.side = 'assistant';
      if (layout.mode === 'desktop') currentView = 'desktop';
      else {
        currentView = layout.side;
        ensureFrame(layout.side);
      }
      write('weharbor-layout', layout);
      write('weharbor-workspace-view', currentView);
      syncLayoutVars();
      bumpResolution();
      renderNav();
      // Hand focus back to the stream when showing desktop/split.
      if (layout.mode !== 'focus' && currentView === 'desktop') {
        document.getElementById('overlayInput')?.focus?.();
      } else if (layout.mode !== 'desktop') {
        sideFrame()?.focus?.();
      }
    };

    const showView = (view) => {
      if (view === 'desktop') setLayout({mode: 'desktop'});
      else if (mobile) setLayout({mode: 'focus', side: view});
      else if (layout.mode === 'desktop') setLayout({mode: 'split', side: view});
      else if (layout.mode === 'split' && layout.side === view) setLayout({mode: 'focus', side: view});
      else setLayout({mode: layout.mode === 'focus' ? 'focus' : 'split', side: view});
    };

    const keys = (...list) => '<span class="wh-keys">' + list.map((k) => '<kbd>' + k + '</kbd>').join('') + '</span>';
    const renderShortcuts = () => {
      const enabled = readShortcutsEnabled();
      shortcutToggle.checked = enabled;
      for (const input of themeInputs) input.checked = input.value === read('weharbor-theme', 'system');
      const alt = isMac ? '⌥' : 'Alt';
      shortcutHelp.innerHTML = (enabled
        ? '<span>切换应用</span>' + keys(alt, '1–5') + '<span>轮换应用</span>' + keys(alt, '`') +
          '<span>应用管理</span>' + keys(alt, '0') + ''
        : '<span>切换快捷键已关闭</span><span></span>') + '<span>命令面板</span>' + keys(MOD_KEY, 'K');
      renderNav();
    };

    let busy = false, refreshing = false, timer = null;
    let status = {}, settings = {}, notificationAvailable = false, magpie = 'unknown';
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
    // Magpie (the local redacting model gateway) has no JSON health route on this origin;
    // a HEAD of its web UI tells us whether nginx can reach it (502 while it starts/is off).
    const probeMagpie = async () => {
      try {
        const response = await fetch(new URL(VIEW_META.magpie.path, location.origin), {
          method: 'HEAD', credentials: 'same-origin', cache: 'no-store', redirect: 'manual', signal: AbortSignal.timeout(8000)});
        magpie = response.type === 'opaqueredirect' || response.status < 500 ? 'ok' : 'down';
      } catch { magpie = 'down'; }
      renderStatus();
    };
    const appState = (state) => state.restarting ? ['busy', '处理中'] : state.running
      ? ['ok', state.active ? '前台' : '运行中'] : ['off', '未启动'];
    const renderStatus = () => {
      const chip = (label, [state, text], action, title) => '<button type="button" class="wh-chip" data-state="' + state + '" data-action="' + action +
        '" title="' + title + '：' + text + '"><span class="wh-dot"></span><span class="wh-chip-label">' + label + ' <span>' + text + '</span></span></button>';
      const gateway = magpie === 'ok' ? ['ok', '已启用'] : magpie === 'down' ? ['warn', '未就绪'] : ['off', '检查中'];
      chips.innerHTML = [
        chip('微信', appState(status.wechat || {}), 'settings', '微信'),
        chip('Alpha', appState(status.alpha || {}), 'settings', 'Alpha'),
        chip('脱敏网关', gateway, 'view-magpie', 'Magpie 本地脱敏模型网关'),
      ].join('');
    };
    const render = () => {
      for (const app of ['wechat', 'alpha']) {
        const state = status[app] || {};
        const [dot] = appState(state);
        const label = panel.querySelector('[data-status="' + app + '"]');
        label.dataset.state = dot;
        label.innerHTML = '<span class="wh-dot"></span>' +
          (state.restarting ? '处理中' : state.active ? '当前应用' : state.running ? '运行中' : '点击启动');
        panel.querySelector('.app-switch[data-app="' + app + '"]').classList.toggle('active', !!state.active);
        const restart = panel.querySelector('[data-action="restart"][data-app="' + app + '"]');
        if (state.restarting) restart.dataset.state = 'busy'; else delete restart.dataset.state;
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
            button.dataset.app = app; button.dataset.action = 'switch';
            button.dataset.windowId = String(window.id);
            list.appendChild(button);
          }
          if (!windows.length) list.textContent = '暂无窗口';
        }
        const summary = panel.querySelector('[data-windows="' + app + '"] summary');
        summary.textContent = (app === 'wechat' ? '微信窗口' : 'Alpha 窗口') + (windows.length ? ' · ' + windows.length : '');
      }
      for (const button of panel.querySelectorAll('[data-action]')) {
        button.disabled = busy || !!status[button.dataset.app]?.restarting;
      }
      for (const input of panel.querySelectorAll('[data-setting]')) {
        input.checked = input.dataset.setting === 'enabled' ? !!settings.enabled : !!settings.apps?.[input.dataset.setting];
        input.disabled = busy || !notificationAvailable;
      }
      renderStatus();
    };
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try { status = await request('apps'); render(); }
      catch (error) { feedback.textContent = error.message; }
      finally { refreshing = false; }
    };
    const openPanel = async () => {
      closePalette(false);
      panel.hidden = false;
      launcher.setAttribute('aria-expanded', 'true');
      feedback.textContent = '';
      renderShortcuts();
      clearInterval(timer);
      timer = setInterval(refresh, 2000);
      await refresh();
      try {
        settings = await request('config');
        notificationAvailable = settings.available !== false;
        render();
      } catch (error) { feedback.textContent = error.message; }
    };
    const close = (focus = false) => {
      panel.hidden = true;
      launcher.setAttribute('aria-expanded', 'false');
      clearInterval(timer); timer = null;
      if (focus && !mobile) launcher.focus();
    };

    const paletteItems = () => {
      const side = layout.side;
      const sideLabel = VIEW_META[side].label;
      return [
        ...VIEW_ORDER.map((view) => ({id: 'view:' + view, group: '应用', icon: VIEW_META[view].icon, label: VIEW_META[view].label,
          hint: VIEW_META[view].hint, keys: readShortcutsEnabled() ? [SHORTCUT_PREFIX.replace('+', ''), String(VIEW_ORDER.indexOf(view) + 1)] : [],
          words: SEARCH_KEYWORDS[view], current: view === currentView, run: () => showView(view)})),
        {id: 'desktop', group: '布局', icon: 'monitor', label: '仅显示微信', hint: '收起侧栏', words: 'desktop wechat 桌面 weixin',
          current: layout.mode === 'desktop', run: () => setLayout({mode: 'desktop'})},
        {id: 'split', group: '布局', icon: 'columns', label: '并排显示', hint: '微信 + ' + sideLabel, words: 'split bingpai 并排 side',
          current: layout.mode === 'split', run: () => setLayout({mode: 'split', side})},
        {id: 'focus', group: '布局', icon: 'maximize', label: '专注模式', hint: '全屏' + sideLabel, words: 'focus zhuanzhu 专注 fullscreen',
          current: layout.mode === 'focus', run: () => setLayout({mode: 'focus', side})},
        {id: 'theme', group: '偏好', icon: document.documentElement.dataset.weharborTheme === 'dark' ? 'sun' : 'moon',
          label: document.documentElement.dataset.weharborTheme === 'dark' ? '切换到浅色外观' : '切换到深色外观', hint: '外观',
          words: 'theme dark light waiguan 主题 深色 浅色', run: toggleTheme},
        {id: 'settings', group: '偏好', icon: 'settings', label: '应用管理', hint: '窗口、重启与通知',
          keys: readShortcutsEnabled() ? [SHORTCUT_PREFIX.replace('+', ''), '0'] : [], words: 'settings guanli 设置 通知 notifications restart', run: () => openPanel()},
      ];
    };
    let paletteIndex = 0, paletteReturn = null;
    const selectPalette = (index, scroll = true) => {
      const buttons = paletteList.querySelectorAll('li button');
      paletteIndex = Math.max(0, Math.min(index, buttons.length - 1));
      buttons.forEach((b, i) => b.setAttribute('aria-selected', String(i === paletteIndex)));
      const active = buttons[paletteIndex];
      if (active) {
        paletteInput.setAttribute('aria-activedescendant', active.id);
        if (scroll) active.scrollIntoView({block: 'nearest'});
      }
    };
    const renderPalette = (query = '') => {
      const q = query.trim().toLowerCase();
      const items = paletteItems().filter((item) => !q ||
        [item.label, item.hint, item.words || ''].some((text) => text.toLowerCase().includes(q)));
      const nodes = [];
      let group = '';
      items.forEach((item, i) => {
        if (item.group !== group) {
          group = item.group;
          const header = document.createElement('li');
          header.className = 'wh-pal-group'; header.setAttribute('role', 'presentation'); header.textContent = group;
          nodes.push(header);
        }
        const li = document.createElement('li');
        li.setAttribute('role', 'presentation');
        const b = document.createElement('button');
        b.type = 'button'; b.id = 'weharbor-pal-' + i; b.setAttribute('role', 'option'); b.tabIndex = -1;
        b.innerHTML = '<span class="wh-pal-ico">' + icon(item.icon, 16) + '</span><span class="wh-pal-label">' + item.label +
          '</span><span class="wh-pal-hint">' + item.hint + '</span>' + (item.current ? '<span class="wh-pal-tag">当前</span>' : '') +
          '<span class="wh-pal-meta">' + (item.keys || []).map((k) => '<kbd>' + k + '</kbd>').join('') + '</span>';
        b.addEventListener('click', () => { closePalette(); item.run(); });
        b.addEventListener('mousemove', () => { if (paletteIndex !== i) selectPalette(i, false); });
        li.appendChild(b);
        nodes.push(li);
      });
      if (!items.length) {
        const li = document.createElement('li');
        li.className = 'wh-pal-empty'; li.textContent = '没有匹配“' + query.trim() + '”的命令';
        nodes.push(li);
      }
      paletteList.replaceChildren(...nodes);
      paletteList._items = items;
      selectPalette(paletteIndex);
    };
    const openPalette = () => {
      if (!palette.hidden) { closePalette(); return; }
      close();
      paletteReturn = document.activeElement;
      palette.hidden = false; paletteIndex = 0; paletteInput.value = '';
      renderPalette(); paletteInput.focus();
    };
    const closePalette = (restore = true) => {
      if (palette.hidden) return;
      palette.hidden = true;
      if (!restore) return;
      if (paletteReturn && paletteReturn !== document.body && document.contains(paletteReturn)) paletteReturn.focus?.();
      else if (layout.mode === 'desktop') document.getElementById('overlayInput')?.focus?.();
      paletteReturn = null;
    };
    dock.openPalette = openPalette;

    shell.addEventListener('click', (event) => {
      const t = event.target.closest('[data-view],[data-action],[data-close]');
      if (!t) {
        if (event.target === palette) closePalette();
        return;
      }
      if (t.dataset.close !== undefined) { close(true); return; }
      if (t.dataset.view) { showView(t.dataset.view); close(); closePalette(false); return; }
      const action = t.dataset.action;
      if (action === 'palette') openPalette();
      else if (action === 'settings') { if (panel.hidden) openPanel(); else close(); }
      else if (action === 'theme') toggleTheme();
      else if (action === 'layout-desktop') setLayout({mode: 'desktop'});
      else if (action === 'split') setLayout({mode: 'split'});
      else if (action === 'focus') setLayout({mode: 'focus'});
      else if (action === 'focus-toggle') setLayout({mode: layout.mode === 'focus' ? 'split' : 'focus'});
      else if (action === 'close-side') setLayout({mode: 'desktop'});
      else if (action === 'side-reload') reloadSide();
      else if (action === 'view-magpie') { showView('magpie'); probeMagpie(); }
    });

    panel.addEventListener('click', async (event) => {
      const button = event.target.closest('[data-action]');
      if (!button || busy || button.disabled || !button.dataset.app) return;
      const app = button.dataset.app, action = button.dataset.action;
      const name = app === 'wechat' ? '微信' : 'Alpha';
      busy = true; render();
      feedback.textContent = name + (action === 'restart' ? '正在重启，请稍候…' : '正在切换…');
      try {
        const result = await request('apps/' + app + '/' + action, action,
          button.dataset.windowId ? {windowId: Number(button.dataset.windowId)} : {});
        feedback.textContent = name + (action === 'restart' ? '已重新启动。' : '已切换。');
        if (action === 'switch') {
          setLayout({mode: 'desktop'});
          if (result.windowId) { close(); document.activeElement?.blur(); }
          else feedback.textContent = name + '正在准备窗口，窗口出现后请再次点击。';
        }
      } catch (error) {
        feedback.textContent = error.name === 'TimeoutError' ? '等待超时，请稍后查看应用状态。' : error.message;
      } finally { busy = false; await refresh(); }
    });
    panel.addEventListener('change', async (event) => {
      const input = event.target.closest('[data-setting],[data-local]');
      if (!input) return;
      if (input.dataset.local === 'shortcuts') { write('weharbor-dock-shortcuts', input.checked); renderShortcuts(); return; }
      if (input.dataset.local === 'theme') { write('weharbor-theme', input.value); applyTheme(input.value); return; }
      if (!input.dataset.setting || busy) return;
      const key = input.dataset.setting;
      const payload = key === 'enabled' ? {enabled: input.checked} : {apps: {[key]: input.checked}};
      busy = true; render();
      try { settings = await request('app-settings', 'settings', payload); feedback.textContent = '通知设置已保存。'; }
      catch (error) { feedback.textContent = error.message; }
      finally { busy = false; render(); }
    });
    panel.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(true); });
    document.addEventListener('pointerdown', (event) => {
      if (panel.hidden || panel.contains(event.target)) return;
      // Any "settings" trigger toggles the panel itself on click.
      if (event.target.closest?.('[data-action="settings"]')) return;
      close();
    }, true);

    paletteInput.addEventListener('input', () => { paletteIndex = 0; renderPalette(paletteInput.value); });
    palette.addEventListener('keydown', (event) => {
      const items = paletteList._items || [];
      if (event.key === 'Escape') { event.preventDefault(); closePalette(); }
      else if (event.key === 'ArrowDown') { event.preventDefault(); selectPalette((paletteIndex + 1) % Math.max(items.length, 1)); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); selectPalette((paletteIndex - 1 + items.length) % Math.max(items.length, 1)); }
      else if (event.key === 'Enter') {
        event.preventDefault();
        const item = items[paletteIndex];
        closePalette(!item); item?.run();
      } else if (event.key === 'Tab') event.preventDefault();
    });

    let dragSide = null;
    resizer.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      dragSide = {x: event.clientX, width: sideWidth, id: event.pointerId};
      resizer.setPointerCapture(event.pointerId);
      resizer.classList.add('dragging');
      document.documentElement.classList.add('weharbor-resizing');
    });
    resizer.addEventListener('pointermove', (event) => {
      if (!dragSide || dragSide.id !== event.pointerId) return;
      sideWidth = Math.max(300, Math.min(Math.floor(innerWidth * 0.7), dragSide.width + (dragSide.x - event.clientX)));
      syncLayoutVars();
    });
    const endDrag = (event) => {
      if (!dragSide || dragSide.id !== event.pointerId) return;
      dragSide = null; resizer.classList.remove('dragging');
      document.documentElement.classList.remove('weharbor-resizing');
      write('weharbor-side-width', sideWidth);
      bumpResolution();
    };
    resizer.addEventListener('pointerup', endDrag);
    resizer.addEventListener('pointercancel', endDrag);
    resizer.addEventListener('dblclick', () => {
      sideWidth = SIDE_DEFAULT; write('weharbor-side-width', sideWidth);
      syncLayoutVars(); bumpResolution();
    });

    dock.handleShortcut = (action) => {
      if (launcher.hidden) return;
      if (action.type === 'panel') {
        if (panel.hidden) openPanel(); else close(layout.mode === 'desktop');
        return;
      }
      closePalette(false);
      const view = action.type === 'cycle' ? nextView(currentView) : action.view;
      showView(view);
      if (layout.mode === 'desktop') document.getElementById('overlayInput')?.focus?.();
    };

    let wasMobile = mobile;
    addEventListener('resize', () => {
      syncLayoutVars();
      if (mobile !== wasMobile) { wasMobile = mobile; renderNav(); bumpResolution(); }
    });
    window.dispatchEvent(new CustomEvent('weharbor:apps-ready'));
    // Restore previous layout; default is WeChat desktop with shell chrome.
    if (layout.mode !== 'desktop') ensureFrame(layout.side);
    syncLayoutVars();
    bumpResolution();
    renderShortcuts();
    renderStatus();
    refresh().catch(() => {});
    probeMagpie();
    setInterval(() => { if (!document.hidden) { probeMagpie(); if (panel.hidden) refresh(); } }, 30000);
    request('config').then((config) => {
      if (config.appSwitcherEnabled === false) {
        close(); shell.hidden = true;
        document.documentElement.classList.remove('weharbor-unified', 'weharbor-focus');
      }
    }).catch(() => {});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
