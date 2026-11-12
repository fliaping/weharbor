(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let connections = [];
  const connectionId = () => globalThis.crypto.randomUUID?.() || Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
  const feedback = (text, error = false) => { $('feedback').textContent = text; $('feedback').classList.toggle('error', error); };
  async function api(path, body) {
    const r = await fetch(new URL('/workspace/' + path, location.origin), {credentials: 'same-origin', cache: 'no-store',
      ...(body !== undefined ? {method: 'POST', headers: {'Content-Type':'application/json', 'X-WeHarbor-Action':'workspace'}, body: JSON.stringify(body)} : {})});
    const data = await r.json();
    if (!r.ok) throw new Error([data.error || data.detail || '服务请求失败', data.recovery].filter(Boolean).join('；'));
    return data;
  }
  function badge(id, text, ok) { $(id).textContent = text; $(id).className = 'badge ' + (ok ? 'ok' : 'warn'); }
  async function refresh() {
    const [data, history, desktop] = await Promise.all([api('connections'), api('actions'),
      api('desktop/status').catch(() => ({state:'blocked', message:'无法检查微信桌面', recovery:'请确认操作服务运行正常后刷新。'}))]);
    badge('desktop-state', desktop.state === 'ready' ? '就绪' : '需要处理', desktop.state === 'ready');
    $('desktop-message').textContent = desktop.message;
    $('desktop-recovery').textContent = desktop.recovery;
    connections = data.connections;
    badge('selected', data.selected === 'local' ? '正在使用本地服务' : data.selected ? '正在使用网络连接' : '没有可用连接', !!data.selected);
    $('connections').replaceChildren();
    for (const probe of data.probes) {
      const c = connections.find((x) => x.id === probe.id);
      const row = document.createElement('div'); row.className = 'connection row';
      const name = document.createElement('span'); name.textContent = c ? c.url : '本机消息读取服务';
      const state = document.createElement('span'); state.className = 'badge ' + (probe.reachable ? 'ok' : 'warn');
      state.textContent = probe.reachable ? '可达 · ' + probe.latency_ms + ' ms' : '不可达';
      row.append(name, state);
      if (c) {
        const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '移除';
        remove.addEventListener('click', () => run(remove, async () => {
          await api('connections', {connections: connections.filter((x) => x.id !== c.id)}); await refresh();
        })); row.append(remove);
      }
      $('connections').append(row);
    }
    await refreshRemote();
    $('actions').replaceChildren();
    if (!history.actions.length) { const p = document.createElement('p'); p.className = 'empty subtle'; p.textContent = '暂无操作记录。AI 准备或发送消息后，记录会显示在这里。'; $('actions').append(p); return; }
    const table = document.createElement('table');
    table.innerHTML = '<thead><tr><th scope="col">时间</th><th scope="col">目标账号</th><th scope="col">状态</th><th scope="col">说明</th><th scope="col">操作</th></tr></thead>';
    const body = document.createElement('tbody');
    const labels = {prepared:'待提交',scheduled:'已定时',blocked:'等待恢复',submitted:'已提交',sent:'本地已记录',completed:'已完成',uncertain:'待核对',failed:'失败',cancelled:'已取消',expired:'已过期'};
    for (const a of history.actions) {
      const row = document.createElement('tr');
      for (const value of [new Date((a.due || a.created)*1000).toLocaleString(), a.username, labels[a.status] || a.status]) {
        const td = document.createElement('td'); td.textContent = value; row.append(td);
      }
      const explanation = document.createElement('td');
      explanation.style.whiteSpace = 'normal'; explanation.style.minWidth = '200px';
      let detail = null; try { detail = JSON.parse(a.receipt); } catch (_) {}
      explanation.textContent = detail?.code ? [detail.message, detail.recovery].filter(Boolean).join('；') : a.status === 'sent' ? '已核验新增的本地本人消息记录' : a.status === 'uncertain' ? '请在微信核对，系统不会自动重发' : a.receipt || '—';
      row.append(explanation);
      const cell = document.createElement('td');
      if (['prepared','scheduled','blocked'].includes(a.status)) {
        if (a.status === 'blocked' && Date.now()/1000 <= (a.due ? a.due+300 : a.created+120)) {
          const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = '重试'; retry.style.marginRight = '8px';
          retry.addEventListener('click', () => run(retry, async () => { await api((a.operation ? 'operations/' : 'actions/')+a.id+'/commit', {}); await refresh(); })); cell.append(retry);
        }
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消';
        cancel.addEventListener('click', () => run(cancel, async () => { await api((a.operation ? 'operations/' : 'actions/')+a.id+'/cancel', {}); await refresh(); })); cell.append(cancel);
      } else cell.textContent = a.status === 'uncertain' ? '请在微信核对' : '—';
      row.append(cell); body.append(row);
    }
    table.append(body); $('actions').append(table);
  }
  async function run(button, fn) { button.disabled = true; feedback('正在处理…'); try { await fn(); feedback('已更新。'); } catch(e) { feedback(e.message, true); } finally { button.disabled = false; } }
  $('refresh').addEventListener('click', () => run($('refresh'), refresh));
  $('connection-form').addEventListener('submit', (e) => { e.preventDefault(); run(e.submitter, async () => {
    await api('connections', {connections: [...connections, {id: connectionId(), kind: $('kind').value, url: $('url').value, token: $('connection-token').value, enabled: true}]});
    $('connection-token').value = ''; $('url').value = ''; await refresh();
  }); });
  const stateLabels = {disabled: ['未启用', ''], starting: ['启动中', 'warn'], running: ['运行中', 'warn'], connected: ['已连接', 'ok'],
    needs_login: ['需要登录', 'warn'], error: ['错误', 'err'], unknown: ['未知', '']};
  let remoteDirty = {};
  function fillRemote(name, info) {
    const form = $('remote-' + name); if (!form) return;
    const q = (role) => form.querySelector('[data-role="' + role + '"]');
    const status = info.status || {}, label = stateLabels[status.state] || [status.state || '未知', ''];
    q('state').textContent = label[0]; q('state').className = 'badge ' + label[1];
    q('message').textContent = status.message || ''; q('message').title = status.message || '';
    const detail = [];
    if (name === 'tailscale') {
      const live = info.live || {};
      if (live.ips?.length) detail.push('Tailnet IP：' + live.ips.join(' · '));
      if (live.dns) detail.push(info.settings.serve ? 'https://' + live.dns : live.dns);
      const url = live.auth_url || status.auth_url;
      const link = q('login'); link.hidden = !url || live.state === 'Running'; if (url) link.href = url;
    }
    if (name === 'frp' && info.url) detail.push('访问地址：' + info.url);
    if (status.retry_in) detail.push(status.retry_in + ' 秒后自动重试');
    q('detail').textContent = detail.join('　');
    const log = q('log'), atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
    log.textContent = (info.log || []).join('\n') || '暂无日志';
    if (atEnd) log.scrollTop = log.scrollHeight;
    if (remoteDirty[name]) return;
    for (const [field, value] of Object.entries(info.settings)) {
      const input = form.elements[field]; if (!input) continue;
      if (input.type === 'checkbox') input.checked = !!value; else input.value = value === 0 ? '' : value;
      const locked = info.locked.includes(field);
      input.disabled = locked;
      const holder = input.closest('label');
      holder.querySelector('.lock')?.remove();
      if (locked) { const note = document.createElement('span'); note.className = 'lock'; note.textContent = '由环境变量 ' + info.env[field] + ' 设置'; holder.append(note); }
    }
    if (name === 'frp') {
      form.elements.raw.value = info.raw || ''; form.elements.raw.disabled = info.locked.includes('mode');
      q('raw-path').textContent = info.raw_path; showMode(form);
    }
    if (name === 'tailscale') $('ts-login').disabled = !!info.settings.authkey || (info.locked.includes('enabled') && !info.settings.enabled);
  }
  function showMode(form) {
    const mode = form.elements.mode.value;
    form.querySelectorAll('[data-mode]').forEach((el) => { el.hidden = el.dataset.mode !== mode; });
  }
  async function refreshRemote() {
    const data = await api('remote-access');
    for (const name of ['tailscale', 'cloudflare', 'frp']) fillRemote(name, data[name]);
  }
  for (const form of document.querySelectorAll('form.remote')) {
    const name = form.dataset.name;
    form.addEventListener('input', () => { remoteDirty[name] = true; if (form.elements.mode) showMode(form); });
    form.addEventListener('submit', (e) => { e.preventDefault(); run(e.submitter, async () => {
      const body = {};
      for (const input of form.elements) {
        if (!input.name || input.disabled) continue;
        body[input.name] = input.type === 'checkbox' ? input.checked : input.value;
      }
      if (name === 'frp' && body.mode !== 'raw') delete body.raw;
      await api('remote-access/' + name, body);
      remoteDirty[name] = false; await refreshRemote();
    }); });
  }
  $('ts-login').addEventListener('click', () => run($('ts-login'), async () => {
    const result = await api('network/tailscale/login', {});
    remoteDirty.tailscale = false; await refreshRemote();
    if (result.login_url) { const link = $('remote-tailscale').querySelector('[data-role="login"]'); link.href = result.login_url; link.hidden = false; }
    else if (!result.connected) feedback('Tailscale 正在启动，稍后刷新查看登录链接。');
  }));
  setInterval(() => { if (!document.hidden) refreshRemote().catch(() => {}); }, 5000);
  $('sync').addEventListener('click', () => run($('sync'), async () => { await api('sync', {}); await refresh(); }));
  const mcp = location.origin + '/workspace/mcp'; $('mcp-url').textContent = mcp;
  $('copy-mcp').addEventListener('click', () => run($('copy-mcp'), async () => {
    if (navigator.clipboard) return navigator.clipboard.writeText(mcp);
    const selection = getSelection(), range = document.createRange();
    range.selectNodeContents($('mcp-url')); selection.removeAllRanges(); selection.addRange(range);
    if (!document.execCommand('copy')) throw new Error('请手动复制已选中的 MCP 地址。');
  }));
  refresh().catch((e) => feedback(e.message, true));
})();
