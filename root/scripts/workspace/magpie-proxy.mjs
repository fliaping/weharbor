import crypto from 'node:crypto';
import http from 'node:http';
import { spawn } from 'node:child_process';

const args = process.argv.slice(2);
const valueAfter = (flag, fallback) => {
  const index = args.indexOf(flag);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const PORT = Number(valueAfter('--port', process.env.MAGPIE_WEB_PROXY_PORT || '3430'));
const UPSTREAM = Number(process.env.MAGPIE_WEB_UPSTREAM_PORT || '3431');
const GATEWAY = process.env.MAGPIE_ADDR || '127.0.0.1:3425';
const PREFIX = (process.env.MAGPIE_WEB_PROXY_PREFIX || '/magpie').replace(/\/+$/, '');
const BIN = process.env.MAGPIE_BIN || '/opt/weharbor/magpie/magpie';
const WEB_KEY = process.env.MAGPIE_WEB_KEY || crypto.randomBytes(24).toString('base64url');

let cookiePair = '';
let cookieName = '';
let ready = null;

function redact(text) {
  return text
    .split(WEB_KEY).join('[redacted]')
    .replace(/([?&]k=)[^&\s"'<>]+/g, '$1[redacted]');
}

function attachScrubbedStream(stream, target) {
  let carry = '';
  stream.setEncoding('utf8');
  stream.on('data', chunk => {
    carry += chunk;
    const lines = carry.split(/\r?\n/);
    carry = lines.pop() ?? '';
    for (const line of lines) target.write(redact(line) + '\n');
  });
  stream.on('end', () => {
    if (carry) target.write(redact(carry));
  });
}

const child = spawn(BIN, [
  'web', '--addr', `127.0.0.1:${UPSTREAM}`, '--no-open',
], {
  cwd: process.env.HOME || '/config',
  env: {
    ...process.env,
    MAGPIE_ADDR: GATEWAY,
    MAGPIE_WEB_KEY: WEB_KEY,
    DO_NOT_TRACK: '1',
    MAGPIE_NO_STATS: '1',
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
attachScrubbedStream(child.stdout, process.stdout);
attachScrubbedStream(child.stderr, process.stderr);
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));

async function exchangeKey() {
  let lastError = new Error('Magpie web did not accept launch key');
  for (let attempt = 0; attempt < 150; attempt++) {
    try {
      const response = await fetch(`http://127.0.0.1:${UPSTREAM}/?k=${encodeURIComponent(WEB_KEY)}`, {
        redirect: 'manual',
      });
      const setCookie = response.headers.getSetCookie?.() ||
        (response.headers.get('set-cookie') ? [response.headers.get('set-cookie')] : []);
      const first = (setCookie[0] || '').split(';', 1)[0].trim();
      if (first.includes('=')) {
        cookiePair = first;
        cookieName = first.slice(0, first.indexOf('='));
        return;
      }
      lastError = new Error(`Magpie web did not return session cookie (status ${response.status})`);
    } catch (error) {
      lastError = error;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw lastError;
}

ready = exchangeKey();

function stripPrefix(pathname) {
  if (pathname === PREFIX) return '/';
  if (pathname.startsWith(PREFIX + '/')) return pathname.slice(PREFIX.length) || '/';
  return pathname || '/';
}

function rewriteHtml(text) {
  if (!PREFIX) return text;
  const escaped = PREFIX.slice(1).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return text.replace(
    new RegExp(`([("'\`])\/(?!\/|${escaped}(?:\/|$))(assets\/|api\/|plugin-page\/|_magpie\/|icons\/|favicon|manifest\.json)`, 'g'),
    `$1${PREFIX}/$2`,
  );
}

function appendBootShim(text) {
  if (!PREFIX) return text;
  const prefixJson = JSON.stringify(PREFIX);
  return `${text}
;(() => {
  const prefix = ${prefixJson};
  const prefixes = ["/api", "/plugin-page", "/_magpie"];
  const rewrite = (v) => (typeof v === "string" && prefixes.some((p) => v === p || v.startsWith(p + "/") || v.startsWith(p + "?"))) ? prefix + v : v;
  const origFetch = typeof window !== "undefined" && window.fetch;
  if (typeof origFetch === "function") {
    window.fetch = function(input, init) {
      return origFetch.call(this, rewrite(input), init);
    };
  }
  for (const [Proto, prop] of [
    [typeof HTMLImageElement !== "undefined" && HTMLImageElement.prototype, "src"],
    [typeof HTMLIFrameElement !== "undefined" && HTMLIFrameElement.prototype, "src"],
    [typeof HTMLAnchorElement !== "undefined" && HTMLAnchorElement.prototype, "href"],
  ]) {
    const desc = Proto && Object.getOwnPropertyDescriptor(Proto, prop);
    if (desc && desc.set) {
      Object.defineProperty(Proto, prop, {
        ...desc,
        set(v) { desc.set.call(this, rewrite(v)); },
      });
    }
  }
})();
`;
}

function hasCookie(request) {
  return Boolean(cookieName && (request.headers.cookie || '').split(';').some(part => part.trim().startsWith(cookieName + '=')));
}

function trustedRequest(request) {
  if (request.headers['sec-fetch-site'] === 'cross-site') return false;
  const origin = request.headers.origin;
  if (origin === undefined) return true;
  try {
    const parsed = new URL(origin);
    const host = String(request.headers['x-forwarded-host'] || request.headers.host || '').split(',', 1)[0].trim().toLowerCase();
    return ['http:', 'https:'].includes(parsed.protocol) && parsed.host.toLowerCase() === host;
  } catch {
    return false;
  }
}

function upstreamHeaders(request) {
  const headers = { ...request.headers, host: `127.0.0.1:${UPSTREAM}` };
  if (request.headers.origin) headers.origin = `http://127.0.0.1:${UPSTREAM}`;
  delete headers['accept-encoding'];
  delete headers['content-length'];
  const existing = (request.headers.cookie || '')
    .split(';')
    .map(part => part.trim())
    .filter(part => part && (!cookieName || !part.startsWith(cookieName + '=')));
  if (cookiePair) existing.push(cookiePair);
  if (existing.length) headers.cookie = existing.join('; ');
  return headers;
}

const server = http.createServer(async (request, response) => {
  try {
    await ready;
    if (!trustedRequest(request)) {
      response.writeHead(403, { 'content-type': 'text/plain; charset=utf-8' });
      response.end('Cross-origin Magpie request rejected');
      return;
    }
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const upstreamPath = stripPrefix(url.pathname);
    const isBootstrap = (request.method === 'GET' || request.method === 'HEAD') &&
      (upstreamPath === '/' || upstreamPath === '/index.html');
    const isProtected = upstreamPath.startsWith('/api/') ||
      upstreamPath.startsWith('/plugin-page/') ||
      upstreamPath.startsWith('/_magpie/');
    if (isProtected && !hasCookie(request)) {
      response.writeHead(401, { 'content-type': 'text/plain; charset=utf-8' });
      response.end('Magpie session cookie required');
      return;
    }
    const body = request.method === 'GET' || request.method === 'HEAD'
      ? undefined
      : await new Promise((resolve, reject) => {
          const chunks = [];
          request.on('data', chunk => chunks.push(chunk));
          request.on('end', () => resolve(Buffer.concat(chunks)));
          request.on('error', reject);
        });
    const upstream = await fetch(`http://127.0.0.1:${UPSTREAM}${upstreamPath}${url.search}`, {
      method: request.method,
      headers: upstreamHeaders(request),
      body,
      redirect: 'manual',
    });
    const headers = {};
    upstream.headers.forEach((value, key) => {
      if (!['content-encoding', 'content-length', 'transfer-encoding', 'set-cookie'].includes(key.toLowerCase())) {
        headers[key] = value;
      }
    });
    if (isBootstrap && cookiePair) {
      headers['set-cookie'] = [`${cookiePair}; Path=${PREFIX || '/'}/; HttpOnly; SameSite=Strict`];
    }
    const type = (upstream.headers.get('content-type') || '').toLowerCase();
    if (upstreamPath === '/boot.js') {
      const payload = Buffer.from(appendBootShim(await upstream.text()), 'utf8');
      headers['content-length'] = String(payload.length);
      response.writeHead(upstream.status, headers);
      response.end(payload);
      return;
    }
    if (!upstreamPath.startsWith('/api/') && type.includes('text/html')) {
      const payload = Buffer.from(rewriteHtml(await upstream.text()), 'utf8');
      headers['content-length'] = String(payload.length);
      response.writeHead(upstream.status, headers);
      response.end(payload);
      return;
    }
    const payload = Buffer.from(await upstream.arrayBuffer());
    headers['content-length'] = String(payload.length);
    response.writeHead(upstream.status, headers);
    response.end(payload);
  } catch (error) {
    response.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' });
    response.end('Magpie web UI is starting: ' + redact(String(error?.message || error)));
  }
});

server.on('upgrade', async (request, socket, head) => {
  try {
    await ready;
    if (!trustedRequest(request)) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
      return;
    }
    if (!hasCookie(request)) {
      socket.end('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n');
      return;
    }
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const proxy = http.request({
      host: '127.0.0.1',
      port: UPSTREAM,
      method: request.method,
      path: stripPrefix(url.pathname) + url.search,
      headers: upstreamHeaders(request),
    });
    proxy.on('upgrade', (upstreamResponse, upstreamSocket, upstreamHead) => {
      const status = upstreamResponse.statusCode || 101;
      const lines = [`HTTP/1.1 ${status} ${upstreamResponse.statusMessage || 'Switching Protocols'}`];
      for (const [key, value] of Object.entries(upstreamResponse.headers)) {
        if (Array.isArray(value)) {
          for (const item of value) lines.push(`${key}: ${item}`);
        } else if (value !== undefined) {
          lines.push(`${key}: ${value}`);
        }
      }
      socket.write(lines.join('\r\n') + '\r\n\r\n');
      if (upstreamHead?.length) socket.write(upstreamHead);
      if (head?.length) upstreamSocket.write(head);
      upstreamSocket.pipe(socket).pipe(upstreamSocket);
    });
    proxy.on('response', upstreamResponse => {
      socket.end(`HTTP/1.1 ${upstreamResponse.statusCode || 502} ${upstreamResponse.statusMessage || 'Bad Gateway'}\r\nConnection: close\r\n\r\n`);
    });
    proxy.on('error', () => socket.destroy());
    proxy.end();
  } catch {
    socket.destroy();
  }
});

server.listen(PORT, '127.0.0.1');
