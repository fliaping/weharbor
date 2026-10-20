(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let connections = [];
  const connectionId = () => globalThis.crypto.randomUUID?.() || Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
  const feedback = (text, error = false) => { $('feedback').textContent = text; $('feedback').classList.toggle('error', error); };
  async function api(path, body) {
    const r = await fetch('/workspace/' + path, {credentials: 'same-origin', cache: 'no-store',
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
    const ts = data.network.tailscale, cf = data.network.cloudflare;
    badge('ts-state', !ts.installed ? '未安装' : ts.state === 'Running' ? '已连接' : ts.state || '未连接', ts.state === 'Running');
    $('ts-ips').textContent = ts.ips.join(' · '); $('ts-login').disabled = !ts.installed;
    badge('cf-state', !cf.installed ? '未安装' : cf.running ? '连接进程运行中' : cf.configured ? '已配置 · 未运行' : '未配置', cf.running);
    $('cf-open').disabled = !cf.installed;
    $('actions').replaceChildren();
    if (!history.actions.length) { const p = document.createElement('p'); p.className = 'empty subtle'; p.textContent = '暂无操作记录。AI 准备或发送消息后，记录会显示在这里。'; $('actions').append(p); return; }
    const table = document.createElement('table');
    table.innerHTML = '<thead><tr><th scope="col">时间</th><th scope="col">目标账号</th><th scope="col">状态</th><th scope="col">说明</th><th scope="col">操作</th></tr></thead>';
    const body = document.createElement('tbody');
    const labels = {prepared:'待提交',scheduled:'已定时',blocked:'等待恢复',submitted:'已提交',sent:'本地已记录',uncertain:'待核对',failed:'失败',cancelled:'已取消',expired:'已过期'};
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
          retry.addEventListener('click', () => run(retry, async () => { await api('actions/'+a.id+'/commit', {}); await refresh(); })); cell.append(retry);
        }
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = '取消';
        cancel.addEventListener('click', () => run(cancel, async () => { await api('actions/'+a.id+'/cancel', {}); await refresh(); })); cell.append(cancel);
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
  $('ts-login').addEventListener('click', () => run($('ts-login'), async () => {
    const result = await api('network/tailscale/login', {});
    if (result.login_url) { $('login-link').href = result.login_url; $('login-link').hidden = false; }
    await refresh();
  }));
  $('cf-open').addEventListener('click', () => $('cf-dialog').showModal());
  $('cf-close').addEventListener('click', () => { $('cf-token').value = ''; $('cf-dialog').close(); });
  $('cf-form').addEventListener('submit', (e) => { e.preventDefault(); run(e.submitter, async () => {
    await api('network/cloudflare', {token: $('cf-token').value}); $('cf-token').value = ''; $('cf-dialog').close(); await refresh();
  }); });
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
