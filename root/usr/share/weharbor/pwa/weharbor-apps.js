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
    desktop: {label: '微信', hint: '官方桌面', icon: '💬', path: null},
    analysis: {label: '分析', hint: '聊天与媒体', icon: '📊', path: '/analysis/'},
    magpie: {label: 'Magpie', hint: '模型网关', icon: '🛡️', path: '/magpie/'},
    assistant: {label: '助手', hint: 'DeepSeek', icon: '🤖', path: '/assistant/'},
    connections: {label: '连接', hint: '网络 · MCP', icon: '🔗', path: '/workspace/'},
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

  const mount = () => {
    if (document.getElementById('weharbor-shell')) return;
    const read = (key, fallback) => {
      try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
    };
    const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };

    const themePref = read('weharbor-theme', 'system');
    const applyTheme = (pref) => {
      const dark = pref === 'dark' || (pref === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.dataset.weharborTheme = dark ? 'dark' : 'light';
      document.documentElement.classList.add('weharbor-unified');
    };
    applyTheme(themePref);
    try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => applyTheme(read('weharbor-theme', 'system'))); } catch {}

    let sideWidth = Math.max(320, Math.min(720, Number(read('weharbor-side-width', 420)) || 420));
    let layout = read('weharbor-layout', {mode: 'desktop', side: 'assistant'}); // mode: desktop | split | focus
    if (!VIEW_META[layout.side]) layout.side = 'assistant';
    if (!['desktop', 'split', 'focus'].includes(layout.mode)) layout.mode = 'desktop';
    let currentView = layout.mode === 'desktop' ? 'desktop' : layout.side;
    let mobile = matchMedia('(max-width: 720px)').matches;

    const style = document.createElement('style');
    style.textContent = `
:root, html[data-weharbor-theme=light]{
  --wh-bg:#f4f7fb; --wh-surface:#ffffff; --wh-surface-2:#eef3f8; --wh-ink:#0f172a; --wh-muted:#5b6b7c;
  --wh-line:#d5dee8; --wh-accent:#0b6e99; --wh-accent-soft:#d9eff8; --wh-ok:#15803d; --wh-warn:#b45309;
  --wh-danger:#b91c1c; --wh-rail:56px; --wh-top:44px; --wh-side:0px; --wh-bottom:0px; --wh-radius:12px;
  --wh-shadow:0 10px 40px #0f172a1a; --wh-font:system-ui,-apple-system,"Segoe UI","PingFang SC","Noto Sans SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;
  --wh-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; color-scheme:light;
}
html[data-weharbor-theme=dark]{
  --wh-bg:#0b1220; --wh-surface:#121c2c; --wh-surface-2:#1a2740; --wh-ink:#e8f0fa; --wh-muted:#9db0c5;
  --wh-line:#2a3b55; --wh-accent:#5ec8f0; --wh-accent-soft:#163247; --wh-ok:#4ade80; --wh-warn:#fbbf24;
  --wh-danger:#f87171; --wh-shadow:0 14px 40px #0008; color-scheme:dark;
}
html.weharbor-unified, html.weharbor-unified body{height:100%;margin:0;overflow:hidden;background:var(--wh-bg);font-family:var(--wh-font);color:var(--wh-ink)}
html.weharbor-unified #app{
  position:fixed!important;left:var(--wh-rail)!important;top:var(--wh-top)!important;right:var(--wh-side)!important;bottom:var(--wh-bottom)!important;
  width:auto!important;height:auto!important;overflow:hidden;z-index:1;background:#0b1220;
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
#weharbor-shell{position:fixed;inset:0;z-index:2147482900;pointer-events:none;font:13px/1.45 var(--wh-font);color:var(--wh-ink)}
#weharbor-shell *{box-sizing:border-box}
#weharbor-shell .wh-chrome{pointer-events:auto}
#weharbor-rail{position:absolute;left:0;top:0;bottom:var(--wh-bottom);width:var(--wh-rail);display:flex;flex-direction:column;align-items:center;gap:4px;padding:8px 0 10px;background:var(--wh-surface);border-right:1px solid var(--wh-line);z-index:5}
#weharbor-rail .wh-brand{width:36px;height:36px;border-radius:10px;background:linear-gradient(145deg,#0b6e99,#14b8a6);color:#fff;display:grid;place-items:center;font-weight:700;letter-spacing:-.04em;margin-bottom:8px}
#weharbor-rail .wh-nav{display:flex;flex-direction:column;gap:4px;width:100%;align-items:center;flex:1}
#weharbor-rail button.wh-nav-btn,#weharbor-top button,#weharbor-side button,#weharbor-apps button,#weharbor-palette button,#weharbor-bottom button{
  appearance:none;border:1px solid transparent;background:transparent;color:var(--wh-ink);cursor:pointer;font:inherit;border-radius:10px}
#weharbor-rail button.wh-nav-btn{width:44px;height:44px;display:grid;place-items:center;gap:0;position:relative;color:var(--wh-ink)}
#weharbor-rail button.wh-nav-btn[aria-current=true],#weharbor-rail button.wh-nav-btn[aria-pressed=true]{background:var(--wh-accent-soft);color:var(--wh-accent);border-color:transparent}
#weharbor-rail button.wh-nav-btn:hover{background:var(--wh-surface-2);color:var(--wh-ink)}
#weharbor-rail button.wh-nav-btn:focus-visible,#weharbor-top button:focus-visible,#weharbor-side button:focus-visible,#weharbor-apps button:focus-visible,#weharbor-palette button:focus-visible{outline:2px solid var(--wh-accent);outline-offset:2px}
#weharbor-rail .wh-nav-btn .wh-ico{font-size:18px;line-height:1}
#weharbor-rail .wh-nav-btn .wh-kbd{position:absolute;bottom:2px;right:3px;font:8px/1 var(--wh-mono);opacity:.35;color:var(--wh-muted);pointer-events:none}
#weharbor-rail .wh-rail-foot{display:flex;flex-direction:column;gap:4px;margin-top:auto}
#weharbor-top{position:absolute;left:var(--wh-rail);right:0;top:0;height:var(--wh-top);display:flex;align-items:center;gap:12px;padding:0 16px;background:color-mix(in srgb, var(--wh-surface) 94%, transparent);backdrop-filter:blur(12px);border-bottom:1px solid var(--wh-line);z-index:3}
#weharbor-top .wh-title{font-weight:650;letter-spacing:-.02em;white-space:nowrap}
#weharbor-top .wh-chips{display:flex;gap:6px;flex:1;overflow:auto;scrollbar-width:none}
#weharbor-top .wh-chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;background:var(--wh-surface-2);border:1px solid var(--wh-line);color:var(--wh-muted);white-space:nowrap;font-size:12px;line-height:1.2;height:26px}
#weharbor-top .wh-chip[data-state=ok]{color:var(--wh-ok);border-color:color-mix(in srgb, var(--wh-ok) 35%, var(--wh-line))}
#weharbor-top .wh-chip[data-state=warn]{color:var(--wh-warn)}
#weharbor-top .wh-chip[data-state=off]{opacity:.65}
#weharbor-top .wh-dot{width:7px;height:7px;border-radius:50%;background:currentColor}
#weharbor-top .wh-actions{display:flex;gap:6px;margin-left:auto}
#weharbor-top .wh-actions button{min-height:30px;padding:0 10px;border:1px solid var(--wh-line);background:var(--wh-surface);border-radius:8px;color:var(--wh-ink)}
#weharbor-side{position:absolute;top:var(--wh-top);right:0;bottom:var(--wh-bottom);width:var(--wh-side);background:var(--wh-surface);border-left:1px solid var(--wh-line);display:flex;flex-direction:column;z-index:4;min-width:0}
#weharbor-side[hidden],#weharbor-resizer[hidden],#weharbor-bottom[hidden],#weharbor-apps[hidden],#weharbor-palette[hidden]{display:none!important}
#weharbor-side .wh-side-head{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--wh-line);min-height:40px}
#weharbor-side .wh-side-head h2{margin:0;font-size:13px;font-weight:650;flex:1}
#weharbor-side .wh-side-head button{width:30px;height:30px;border:1px solid var(--wh-line);background:var(--wh-surface-2);border-radius:8px}
#weharbor-side .wh-frame-host{position:relative;flex:1;min-height:0;background:var(--wh-bg)}
#weharbor-side iframe,#weharbor-workspace-frames iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:var(--wh-bg)}
#weharbor-side iframe[hidden],#weharbor-workspace-frames iframe[hidden]{display:none}
#weharbor-side .wh-empty{position:absolute;inset:0;display:grid;place-items:center;padding:24px;text-align:center;color:var(--wh-muted)}
#weharbor-side .wh-empty strong{display:block;color:var(--wh-ink);margin-bottom:6px}
#weharbor-resizer{position:absolute;top:var(--wh-top);bottom:var(--wh-bottom);width:6px;margin-left:-3px;cursor:col-resize;z-index:5;background:transparent}
#weharbor-resizer:hover,#weharbor-resizer.dragging{background:var(--wh-accent)}
#weharbor-workspace-frames{position:absolute;inset:0;z-index:0}
#weharbor-bottom{position:absolute;left:0;right:0;bottom:0;height:56px;display:flex;background:var(--wh-surface);border-top:1px solid var(--wh-line);z-index:3}
#weharbor-bottom button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;color:var(--wh-muted);font-size:11px;border-radius:0}
#weharbor-bottom button[aria-current=true]{color:var(--wh-accent);background:var(--wh-accent-soft)}
#weharbor-apps{position:absolute;z-index:2147483001;width:min(340px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;padding:16px;border:1px solid var(--wh-line);border-radius:var(--wh-radius);background:var(--wh-surface);box-shadow:var(--wh-shadow);left:calc(var(--wh-rail) + 12px);top:56px}
#weharbor-apps h2{margin:0;font-size:15px}
#weharbor-apps header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
#weharbor-apps button{border:1px solid var(--wh-line);background:var(--wh-surface-2);padding:7px 10px;border-radius:8px}
#weharbor-apps .app-row{display:flex;gap:8px;margin-top:12px}
#weharbor-apps .app-switch{flex:1;display:flex;align-items:center;justify-content:space-between}
#weharbor-apps .app-switch.active{border-color:var(--wh-ok);background:color-mix(in srgb, var(--wh-ok) 12%, var(--wh-surface))}
#weharbor-apps .app-status,#weharbor-apps .app-hint,#weharbor-apps .app-shortcuts,#weharbor-apps details{color:var(--wh-muted);font-size:12px}
#weharbor-apps .app-windows{display:grid;gap:4px;margin:5px 0}
#weharbor-apps .app-windows button{text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#weharbor-apps .app-settings{margin-top:14px;border-top:1px solid var(--wh-line);padding-top:10px}
#weharbor-apps label{display:flex;align-items:center;gap:7px;padding:4px 0}
#weharbor-apps input{accent-color:var(--wh-accent)}
#weharbor-apps kbd{font:11px var(--wh-mono);border:1px solid var(--wh-line);border-radius:4px;padding:0 3px;background:var(--wh-surface-2)}
#weharbor-apps .app-feedback{margin:10px 0 0;white-space:pre-wrap;font-size:12px}
#weharbor-palette{position:absolute;inset:0;z-index:2147483010;display:grid;place-items:start center;padding-top:12vh;background:#0f172a66}
#weharbor-palette .wh-pal{width:min(560px,calc(100vw - 24px));background:var(--wh-surface);border:1px solid var(--wh-line);border-radius:16px;box-shadow:var(--wh-shadow);overflow:hidden}
#weharbor-palette input{width:100%;border:0;border-bottom:1px solid var(--wh-line);padding:16px 18px;font:15px var(--wh-font);background:transparent;color:var(--wh-ink);outline:none}
#weharbor-palette ul{list-style:none;margin:0;padding:8px;max-height:50vh;overflow:auto}
#weharbor-palette li button{width:100%;display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;text-align:left}
#weharbor-palette li button[aria-selected=true],#weharbor-palette li button:hover{background:var(--wh-accent-soft)}
#weharbor-palette .wh-pal-meta{margin-left:auto;color:var(--wh-muted);font-size:12px}
@media (max-width:720px){
  :root{--wh-rail:0px;--wh-bottom:56px}
  #weharbor-rail,#weharbor-resizer{display:none!important}
  #weharbor-top{left:0}
  #weharbor-side{left:0;right:0;width:auto!important;border-left:0}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
`;
    document.head.appendChild(style);

    const shell = document.createElement('div');
    shell.id = 'weharbor-shell';
    shell.innerHTML = `
<aside id="weharbor-rail" class="wh-chrome" aria-label="WeHarbor 导航">
  <div class="wh-brand" title="WeHarbor｜微港">微</div>
  <nav class="wh-nav" data-rail-nav></nav>
  <div class="wh-rail-foot">
    <button type="button" class="wh-nav-btn" data-action="palette" title="命令面板 (${isMac ? '⌘' : 'Ctrl'}+K)" aria-label="打开命令面板"><span class="wh-ico">⌘</span></button>
    <button type="button" class="wh-nav-btn" data-action="theme" title="切换外观" aria-label="切换浅色/深色"><span class="wh-ico">◐</span></button>
    <button type="button" class="wh-nav-btn" id="weharbor-apps-button" data-action="settings" title="应用管理" aria-label="打开应用管理" aria-controls="weharbor-apps" aria-expanded="false"><span class="wh-ico">⚙️</span></button>
  </div>
</aside>
<header id="weharbor-top" class="wh-chrome">
  <div class="wh-title">WeHarbor｜微港</div>
  <div class="wh-chips" data-chips aria-live="polite"></div>
  <div class="wh-actions">
    <button type="button" data-action="split" title="与微信并排">并排</button>
    <button type="button" data-action="focus" title="专注当前应用">专注</button>
    <button type="button" data-action="palette">${isMac ? '⌘' : 'Ctrl'}+K</button>
  </div>
</header>
<div id="weharbor-resizer" class="wh-chrome" hidden title="拖动调整宽度" role="separator" aria-orientation="vertical"></div>
<section id="weharbor-side" class="wh-chrome" hidden aria-label="侧栏应用">
  <div class="wh-side-head"><h2 data-side-title>助手</h2>
    <button type="button" data-action="focus" title="专注" aria-label="专注模式">⛶</button>
    <button type="button" data-action="close-side" title="关闭侧栏" aria-label="关闭侧栏">×</button>
  </div>
  <div class="wh-frame-host" id="weharbor-workspace-frames">
    <div class="wh-empty" data-empty hidden><strong>尚未加载</strong><span></span></div>
  </div>
</section>
<nav id="weharbor-bottom" class="wh-chrome" hidden aria-label="移动端导航"></nav>
<section id="weharbor-apps" class="wh-chrome" hidden aria-labelledby="weharbor-apps-title">
  <header><h2 id="weharbor-apps-title">应用管理</h2><button type="button" data-close aria-label="收起">×</button></header>
  <div class="app-row"><button type="button" class="app-switch" data-app="wechat" data-action="switch"><span>微信</span><span class="app-status" data-status="wechat">…</span></button>
    <button type="button" data-app="wechat" data-action="restart" title="重启微信" aria-label="重启微信">↻</button></div>
  <details data-windows="wechat"><summary>微信窗口</summary><div class="app-windows"></div></details>
  <div class="app-row"><button type="button" class="app-switch" data-app="alpha" data-action="switch"><span>Alpha</span><span class="app-status" data-status="alpha">…</span></button>
    <button type="button" data-app="alpha" data-action="restart" title="重启 Alpha" aria-label="重启 Alpha">↻</button></div>
  <details data-windows="alpha"><summary>Alpha 窗口</summary><div class="app-windows"></div></details>
  <p class="app-hint">点击应用切换；再次点击可轮换窗口。重启前请保存未发送的内容。</p>
  <div class="app-settings">
    <label><input type="checkbox" data-setting="enabled">浏览器通知</label>
    <label><input type="checkbox" data-setting="wechat">微信通知</label>
    <label><input type="checkbox" data-setting="alpha">Alpha 通知</label>
    <label><input type="checkbox" data-local="shortcuts">启用切换快捷键（本浏览器）</label>
    <label>外观
      <select data-local="theme" style="margin-left:8px;min-height:32px;border:1px solid var(--wh-line);border-radius:8px;background:var(--wh-surface);color:inherit">
        <option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option>
      </select>
    </label>
    <p class="app-shortcuts" data-shortcut-help></p>
  </div>
  <p class="app-feedback" role="status" aria-live="polite"></p>
  <div class="app-install"><button type="button" id="weharbor-install" hidden>安装 WeHarbor</button></div>
</section>
<div id="weharbor-palette" class="wh-chrome" hidden role="dialog" aria-modal="true" aria-label="命令面板">
  <div class="wh-pal"><input type="search" placeholder="搜索应用、布局或操作…" aria-label="命令搜索" autocomplete="off">
    <ul data-palette-list></ul></div>
</div>`;
    document.body.appendChild(shell);

    const railNav = shell.querySelector('[data-rail-nav]');
    const bottom = shell.querySelector('#weharbor-bottom');
    const side = shell.querySelector('#weharbor-side');
    const frames = shell.querySelector('#weharbor-workspace-frames');
    const empty = frames.querySelector('[data-empty]');
    const resizer = shell.querySelector('#weharbor-resizer');
    const panel = shell.querySelector('#weharbor-apps');
    const launcher = shell.querySelector('#weharbor-apps-button');
    const chips = shell.querySelector('[data-chips]');
    const palette = shell.querySelector('#weharbor-palette');
    const paletteInput = palette.querySelector('input');
    const paletteList = palette.querySelector('[data-palette-list]');
    const sideTitle = shell.querySelector('[data-side-title]');
    const feedback = panel.querySelector('.app-feedback');
    const shortcutHelp = panel.querySelector('[data-shortcut-help]');
    const shortcutToggle = panel.querySelector('[data-local="shortcuts"]');
    const themeSelect = panel.querySelector('[data-local="theme"]');

    for (const view of VIEW_ORDER) {
      const meta = VIEW_META[view];
      const btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'wh-nav-btn'; btn.dataset.view = view;
      btn.title = meta.label + ' · ' + meta.hint + (readShortcutsEnabled() ? ' (' + shortcutLabel(view) + ')' : '');
      btn.setAttribute('aria-label', meta.label);
      btn.innerHTML = '<span class="wh-ico" aria-hidden="true">' + meta.icon + '</span><span class="wh-kbd">' + (VIEW_ORDER.indexOf(view) + 1) + '</span>';
      railNav.appendChild(btn);
      const m = document.createElement('button');
      m.type = 'button'; m.dataset.view = view; m.innerHTML = '<span>' + meta.icon + '</span><span>' + meta.label + '</span>';
      bottom.appendChild(m);
    }

    const stopChrome = (root) => {
      for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'mousedown', 'mousemove',
        'mouseup', 'click', 'dblclick', 'keydown', 'keyup', 'wheel', 'touchstart', 'touchmove', 'touchend', 'contextmenu']) {
        root.addEventListener(type, (event) => event.stopPropagation());
      }
    };
    stopChrome(shell);

    const syncLayoutVars = () => {
      mobile = matchMedia('(max-width: 720px)').matches;
      const sideOpen = layout.mode !== 'desktop' && !mobile;
      const focus = layout.mode === 'focus' || (mobile && layout.mode !== 'desktop');
      document.documentElement.style.setProperty('--wh-rail', mobile ? '0px' : '56px');
      document.documentElement.style.setProperty('--wh-top', '44px');
      document.documentElement.style.setProperty('--wh-bottom', mobile ? '56px' : '0px');
      document.documentElement.style.setProperty('--wh-side', sideOpen && !focus ? sideWidth + 'px' : (focus ? (mobile ? '0px' : '0px') : '0px'));
      if (focus) {
        document.documentElement.classList.add('weharbor-focus');
        document.documentElement.style.setProperty('--wh-side', '0px');
        side.style.left = mobile ? '0' : 'var(--wh-rail)';
        side.style.right = '0';
        side.style.width = 'auto';
        side.hidden = false;
      } else {
        document.documentElement.classList.remove('weharbor-focus');
        side.style.left = '';
        side.style.right = '';
        side.style.width = '';
        side.hidden = layout.mode === 'desktop';
      }
      bottom.hidden = !mobile;
      resizer.hidden = !(sideOpen && !focus);
      if (!resizer.hidden) resizer.style.right = sideWidth + 'px';
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

    const ensureFrame = (view) => {
      const meta = VIEW_META[view];
      if (!meta?.path) return null;
      let frame = frames.querySelector('[data-frame="' + view + '"]');
      if (!frame) {
        frame = document.createElement('iframe');
        frame.dataset.frame = view;
        frame.title = meta.label;
        frame.referrerPolicy = 'same-origin';
        frame.loading = 'lazy';
        empty.hidden = true;
        frame.addEventListener('load', () => {
          try { hookKeys(frame.contentWindow); } catch {}
          frame.dataset.loaded = '1';
        });
        frame.addEventListener('error', () => {
          empty.hidden = false;
          empty.querySelector('strong').textContent = meta.label + ' 加载失败';
          empty.querySelector('span').textContent = '请检查服务是否已启动，或稍后重试。';
        });
        // Lazy: set src only when first shown.
        frames.appendChild(frame);
      }
      if (!frame.src) frame.src = meta.path;
      return frame;
    };

    const renderNav = () => {
      for (const btn of shell.querySelectorAll('[data-view]')) {
        const on = btn.dataset.view === currentView || (layout.mode === 'split' && btn.dataset.view === layout.side && currentView === 'desktop');
        const active = layout.mode === 'desktop' ? btn.dataset.view === 'desktop'
          : (btn.dataset.view === layout.side || (btn.dataset.view === 'desktop' && layout.mode === 'split'));
        btn.setAttribute('aria-current', String(btn.dataset.view === (layout.mode === 'desktop' ? 'desktop' : layout.side)));
        btn.setAttribute('aria-pressed', String(active));
      }
      sideTitle.textContent = VIEW_META[layout.side]?.label || '';
      for (const frame of frames.querySelectorAll('iframe')) {
        const show = layout.mode !== 'desktop' && frame.dataset.frame === layout.side;
        frame.hidden = !show;
      }
    };

    const setLayout = (next) => {
      layout = {...layout, ...next};
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
        frames.querySelector('[data-frame="' + layout.side + '"]')?.focus?.();
      }
    };

    const showView = (view) => {
      if (view === 'desktop') setLayout({mode: 'desktop'});
      else if (mobile) setLayout({mode: 'focus', side: view});
      else if (layout.mode === 'desktop') setLayout({mode: 'split', side: view});
      else if (layout.mode === 'split' && layout.side === view) setLayout({mode: 'focus', side: view});
      else setLayout({mode: layout.mode === 'focus' ? 'focus' : 'split', side: view});
    };

    const renderShortcuts = () => {
      const enabled = readShortcutsEnabled();
      shortcutToggle.checked = enabled;
      themeSelect.value = read('weharbor-theme', 'system');
      shortcutHelp.innerHTML = enabled
        ? '快捷键：<kbd>' + SHORTCUT_PREFIX + '1–5</kbd> 切换，<kbd>' + SHORTCUT_PREFIX +
          '`</kbd> 轮换，<kbd>' + SHORTCUT_PREFIX + '0</kbd>/<kbd>' + SHORTCUT_PREFIX + 'Space</kbd> 应用管理，<kbd>' +
          (isMac ? '⌘' : 'Ctrl') + '+K</kbd> 命令面板'
        : '切换快捷键已关闭。';
      for (const btn of railNav.querySelectorAll('[data-view]')) {
        const view = btn.dataset.view;
        btn.title = VIEW_META[view].label + ' · ' + VIEW_META[view].hint + (enabled ? ' (' + shortcutLabel(view) + ')' : '');
      }
    };

    let busy = false, refreshing = false, timer = null;
    let status = {}, settings = {}, notificationAvailable = false;
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
    const renderStatus = () => {
      const chip = (label, state) => '<span class="wh-chip" data-state="' + state + '"><span class="wh-dot"></span>' + label + '</span>';
      const wechat = status.wechat || {};
      const alpha = status.alpha || {};
      chips.innerHTML = [
        chip('微信 ' + (wechat.running ? (wechat.active ? '前台' : '运行中') : '未启动'), wechat.running ? 'ok' : 'off'),
        chip('Alpha ' + (alpha.running ? (alpha.active ? '前台' : '运行中') : '未启动'), alpha.running ? 'ok' : 'off'),
        chip('Magpie 本地网关', 'ok'),
        chip('脱敏 已启用', 'ok'),
      ].join('');
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
            button.dataset.app = app; button.dataset.action = 'switch';
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
      panel.hidden = false;
      launcher.setAttribute('aria-expanded', 'true');
      feedback.textContent = '';
      renderShortcuts();
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
      if (focus) launcher.focus();
    };

    const paletteItems = () => [
      ...VIEW_ORDER.map((view) => ({id: 'view:' + view, label: VIEW_META[view].label, hint: VIEW_META[view].hint + ' · ' + shortcutLabel(view), run: () => showView(view)})),
      {id: 'split', label: '并排显示', hint: '微信 + 侧栏', run: () => setLayout({mode: 'split', side: layout.side === 'desktop' ? 'assistant' : layout.side})},
      {id: 'focus', label: '专注模式', hint: '全屏当前应用', run: () => setLayout({mode: 'focus', side: layout.side === 'desktop' ? 'assistant' : layout.side})},
      {id: 'desktop', label: '回到微信桌面', hint: SHORTCUT_PREFIX + '1', run: () => setLayout({mode: 'desktop'})},
      {id: 'theme', label: '切换外观', hint: '浅色 / 深色', run: () => {
        const cur = document.documentElement.dataset.weharborTheme === 'dark' ? 'light' : 'dark';
        write('weharbor-theme', cur); applyTheme(cur); themeSelect.value = cur;
      }},
      {id: 'settings', label: '应用管理', hint: SHORTCUT_PREFIX + '0', run: () => openPanel()},
    ];
    let paletteIndex = 0;
    const renderPalette = (query = '') => {
      const q = query.trim().toLowerCase();
      const items = paletteItems().filter((item) => !q || item.label.toLowerCase().includes(q) || item.hint.toLowerCase().includes(q));
      paletteIndex = Math.max(0, Math.min(paletteIndex, items.length - 1));
      paletteList.replaceChildren(...items.map((item, i) => {
        const li = document.createElement('li');
        const b = document.createElement('button');
        b.type = 'button'; b.setAttribute('aria-selected', String(i === paletteIndex));
        b.innerHTML = '<span>' + item.label + '</span><span class="wh-pal-meta">' + item.hint + '</span>';
        b.addEventListener('click', () => { closePalette(); item.run(); });
        li.appendChild(b); return li;
      }));
      paletteList._items = items;
    };
    const openPalette = () => {
      palette.hidden = false; paletteIndex = 0; paletteInput.value = '';
      renderPalette(); paletteInput.focus();
    };
    const closePalette = () => { palette.hidden = true; };
    dock.openPalette = openPalette;

    shell.addEventListener('click', (event) => {
      const t = event.target.closest('[data-view],[data-action],[data-close]');
      if (!t) {
        if (event.target === palette) closePalette();
        return;
      }
      if (t.dataset.close !== undefined) { close(true); return; }
      if (t.dataset.view) { showView(t.dataset.view); close(); closePalette(); return; }
      const action = t.dataset.action;
      if (action === 'palette') openPalette();
      else if (action === 'settings') { if (panel.hidden) openPanel(); else close(); }
      else if (action === 'theme') {
        const cur = document.documentElement.dataset.weharborTheme === 'dark' ? 'light' : 'dark';
        write('weharbor-theme', cur); applyTheme(cur); themeSelect.value = cur;
      } else if (action === 'split') setLayout({mode: 'split', side: layout.side === 'desktop' ? 'assistant' : layout.side});
      else if (action === 'focus') setLayout({mode: 'focus', side: layout.side === 'desktop' ? 'assistant' : layout.side});
      else if (action === 'close-side') setLayout({mode: 'desktop'});
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
      if (!panel.hidden && !panel.contains(event.target) && !launcher.contains(event.target)) close();
    });

    paletteInput.addEventListener('input', () => { paletteIndex = 0; renderPalette(paletteInput.value); });
    palette.addEventListener('keydown', (event) => {
      const items = paletteList._items || [];
      if (event.key === 'Escape') { event.preventDefault(); closePalette(); }
      else if (event.key === 'ArrowDown') { event.preventDefault(); paletteIndex = Math.min(items.length - 1, paletteIndex + 1); renderPalette(paletteInput.value); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); paletteIndex = Math.max(0, paletteIndex - 1); renderPalette(paletteInput.value); }
      else if (event.key === 'Enter') { event.preventDefault(); items[paletteIndex]?.run(); closePalette(); }
    });

    let dragSide = null;
    resizer.addEventListener('pointerdown', (event) => {
      dragSide = {x: event.clientX, width: sideWidth, id: event.pointerId};
      resizer.setPointerCapture(event.pointerId);
      resizer.classList.add('dragging');
    });
    resizer.addEventListener('pointermove', (event) => {
      if (!dragSide || dragSide.id !== event.pointerId) return;
      sideWidth = Math.max(300, Math.min(Math.floor(innerWidth * 0.7), dragSide.width + (dragSide.x - event.clientX)));
      syncLayoutVars();
    });
    const endDrag = (event) => {
      if (!dragSide || dragSide.id !== event.pointerId) return;
      dragSide = null; resizer.classList.remove('dragging');
      write('weharbor-side-width', sideWidth);
      bumpResolution();
    };
    resizer.addEventListener('pointerup', endDrag);
    resizer.addEventListener('pointercancel', endDrag);

    dock.handleShortcut = (action) => {
      if (launcher.hidden) return;
      if (action.type === 'panel') {
        if (panel.hidden) openPanel(); else close(layout.mode === 'desktop');
        return;
      }
      const view = action.type === 'cycle' ? nextView(currentView) : action.view;
      showView(view);
      if (layout.mode === 'desktop') document.getElementById('overlayInput')?.focus?.();
    };

    addEventListener('resize', () => syncLayoutVars());
    window.dispatchEvent(new CustomEvent('weharbor:apps-ready'));
    // Restore previous layout; default is WeChat desktop with shell chrome.
    if (layout.mode !== 'desktop') ensureFrame(layout.side);
    syncLayoutVars();
    bumpResolution();
    renderNav();
    renderShortcuts();
    refresh().catch(() => {});
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
