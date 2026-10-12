(() => {
  "use strict";
  const mount = () => {
    if (document.getElementById('weharbor-apps-button')) return;
    const style = document.createElement('style');
    style.textContent = `
      #weharbor-apps-button{position:fixed;right:16px;bottom:70px;z-index:2147483000;
        padding:10px 16px;border:1px solid #38506b;border-radius:12px;background:#101c2d;
        color:#edf5fc;font:14px system-ui;cursor:pointer;box-shadow:0 4px 18px #0005}
      #weharbor-apps{width:min(360px,calc(100vw - 64px));margin:auto;padding:24px;
        border:1px solid #38506b;border-radius:16px;background:#101c2d;color:#edf5fc;
        font:15px/1.6 system-ui}
      #weharbor-apps::backdrop{background:#0008}
      #weharbor-apps h2{margin:0 0 12px;font-size:20px}
      #weharbor-apps p{color:#bccddd}
      #weharbor-apps button{padding:9px 14px;border:1px solid #38506b;
        border-radius:8px;background:#20354c;color:#edf5fc;cursor:pointer;font:inherit}
      #weharbor-apps button:disabled{opacity:.55;cursor:wait}
      #weharbor-apps .app-row{display:flex;align-items:center;justify-content:space-between;
        gap:12px;margin:14px 0}
      #weharbor-apps .app-status{font-size:13px;color:#bccddd}
      #weharbor-apps .app-feedback{min-height:24px;font-size:14px}
    `;
    document.head.appendChild(style);
    const launcher = document.createElement('button');
    launcher.id = 'weharbor-apps-button';
    launcher.type = 'button';
    launcher.textContent = '应用管理';
    const panel = document.createElement('dialog');
    panel.id = 'weharbor-apps';
    panel.setAttribute('aria-labelledby', 'weharbor-apps-title');
    panel.innerHTML = `<h2 id="weharbor-apps-title">应用管理</h2>
      <p>应用异常或调整缩放后，可以在这里重启。重启前请保存未发送的内容。</p>
      <div class="app-row"><div>微信 <span class="app-status" data-status="wechat"></span></div>
        <button type="button" data-app="wechat">重启微信</button></div>
      <div class="app-row"><div>WeFlow <span class="app-status" data-status="weflow"></span></div>
        <button type="button" data-app="weflow">重启 WeFlow</button></div>
      <p class="app-feedback" role="status" aria-live="polite"></p>
      <button type="button" data-close>关闭</button>`;
    const feedback = panel.querySelector('.app-feedback');
    const endpoint = (path) => new URL(`/notifications/apps${path}`, location.origin);
    let busy = false;
    const refresh = async () => {
      try {
        const response = await fetch(endpoint(''), {cache: 'no-store', credentials: 'same-origin'});
        if (!response.ok) throw new Error('无法读取应用状态');
        const status = await response.json();
        for (const name of ['wechat', 'weflow']) {
          const state = status[name];
          panel.querySelector(`[data-status="${name}"]`).textContent =
            state.restarting ? '正在重启' : state.running ? '运行中' : '未运行';
          panel.querySelector(`[data-app="${name}"]`).disabled = busy || state.restarting;
        }
      } catch (error) {
        feedback.textContent = '无法连接应用管理服务，请刷新页面后重试。';
      }
    };
    launcher.addEventListener('click', () => {
      if (panel.open) return;
      feedback.textContent = '';
      panel.showModal();
      refresh();
    });
    panel.querySelector('[data-close]').addEventListener('click', () => panel.close());
    for (const button of panel.querySelectorAll('[data-app]')) {
      button.addEventListener('click', async () => {
        if (busy) return;
        busy = true;
        for (const action of panel.querySelectorAll('[data-app]')) action.disabled = true;
        const name = button.dataset.app === 'wechat' ? '微信' : 'WeFlow';
        feedback.textContent = `${name}正在重启，请稍候…`;
        try {
          const response = await fetch(endpoint(`/${button.dataset.app}/restart`), {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-WeHarbor-Action': 'restart'},
            body: '{}', signal: AbortSignal.timeout(30000)
          });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || '重启失败，请刷新页面后重试。');
          feedback.textContent = `${name}已重新启动。`;
        } catch (error) {
          feedback.textContent = error.name === 'TimeoutError' ?
            '等待超时，应用可能仍在重启。请稍后关闭并重新打开此面板查看状态。' :
            error.message || '重启失败，请稍后重试。';
        } finally {
          busy = false;
          await refresh();
        }
      });
    }
    // Controls must not send pointer/keyboard events to the remote desktop.
    for (const element of [launcher, panel]) {
      for (const event of ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'keydown', 'keyup']) {
        element.addEventListener(event, (event) => event.stopPropagation());
      }
    }
    document.body.append(launcher, panel);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
