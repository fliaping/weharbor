#!/usr/bin/env node

import http from "node:http";
import net from "node:net";
import process from "node:process";
import { spawn } from "node:child_process";

const rawArgs = process.argv.slice(2);
let listenHost = "127.0.0.1";
let listenPort = 3080;
const dshArgs = [];
const launcherArgs = [];

for (let index = 0; index < rawArgs.length; index += 1) {
  const arg = rawArgs[index];
  if (arg === "--patch" && rawArgs[index + 1]) {
    launcherArgs.push(arg, rawArgs[++index]);
  } else if (arg.startsWith("--patch=")) {
    launcherArgs.push(arg);
  } else if (arg === "--host" && rawArgs[index + 1]) {
    listenHost = rawArgs[index + 1];
    index += 1;
  } else if (arg.startsWith("--host=")) {
    listenHost = arg.slice("--host=".length);
  } else if (arg === "--port" && rawArgs[index + 1]) {
    listenPort = Number.parseInt(rawArgs[index + 1], 10);
    index += 1;
  } else if (arg.startsWith("--port=")) {
    listenPort = Number.parseInt(arg.slice("--port=".length), 10);
  } else {
    dshArgs.push(arg);
  }
}

if (!Number.isInteger(listenPort) || listenPort < 1 || listenPort > 65534) {
  throw new Error(`invalid DeepSeek Harness Web port: ${String(listenPort)}`);
}

const upstreamHost = "127.0.0.1";
const upstreamPort = Number.parseInt(
  process.env.DSH_WEB_UPSTREAM_PORT || String(listenPort + 1),
  10,
);
if (
  !Number.isInteger(upstreamPort) ||
  upstreamPort < 1 ||
  upstreamPort > 65535 ||
  upstreamPort === listenPort
) {
  throw new Error(`invalid DeepSeek Harness upstream port: ${String(upstreamPort)}`);
}
const publicPrefix = (
  process.env.DSH_WEB_PROXY_PREFIX || `/proxy/${String(listenPort)}`
).replace(/\/$/u, "");
const dshBin = process.env.DSH_BIN || "/config/.npm-global/bin/dsh";
let launchToken;

// DSH 0.2 prints a process-scoped launch URL. Keep its token inside this
// loopback proxy; browsers receive only DSH's signed HttpOnly session cookie.
function relayStartup(stream, output) {
  let pending = "";
  function line(value) {
    const match = value.match(/^dsh web: (http:\/\/[^\s]+)$/u);
    if (match) {
      const url = new URL(match[1]);
      if (url.origin === `http://${upstreamHost}:${upstreamPort}` &&
          url.pathname === "/" && /^[A-Za-z0-9_-]+$/u.test(url.searchParams.get("token") || "")) {
        launchToken = url.searchParams.get("token");
      }
    }
    output.write(value.replace(/([?&]token=)[^\s&]+/gu, "$1[redacted]") + "\n");
  }
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    pending += chunk;
    let end;
    while ((end = pending.indexOf("\n")) !== -1) {
      line(pending.slice(0, end));
      pending = pending.slice(end + 1);
    }
    if (pending.length > 1024 * 1024) {
      pending = "";
      output.write("[deepseek-harness-proxy] oversized startup line omitted\n");
    }
  });
  stream.on("end", () => { if (pending) line(pending); });
}

function trustedRequest(request) {
  if (request.headers["sec-fetch-site"] === "cross-site") return false;
  const origin = request.headers.origin;
  if (origin === undefined) return true;
  try {
    const parsed = new URL(origin);
    return ["http:", "https:"].includes(parsed.protocol) &&
      parsed.host.toLowerCase() === String(request.headers.host || "").toLowerCase();
  } catch {
    return false;
  }
}

function upstreamHeaders(request) {
  const headers = { ...request.headers };
  headers.host = `${upstreamHost}:${String(upstreamPort)}`;
  // Validate the original browser origin before translating both authorities.
  // Harness's privileged RPC methods intentionally require a loopback origin.
  if (headers.origin) headers.origin = `http://${headers.host}`;
  return headers;
}

function upstreamPath(requestUrl = "/") {
  const parsed = new URL(requestUrl, "http://agent-workspace.local");
  if (parsed.pathname === publicPrefix) {
    parsed.pathname = "/";
  } else if (parsed.pathname.startsWith(`${publicPrefix}/`)) {
    parsed.pathname = parsed.pathname.slice(publicPrefix.length);
  }
  return `${parsed.pathname}${parsed.search}`;
}

function rewriteBrowserPaths(value) {
  const roots = "(?:(?:assets|plugins)(?:/|(?=[^A-Za-z0-9_.-]))|manifest\\.webmanifest|favicon\\.svg)";
  const quotedRoot = new RegExp(
    "([\"'\\u0060])/(?=" + roots + ")",
    "gu",
  );
  const attributeRoot = new RegExp(
    `(\\b(?:src|href|action)=)/(?=${roots})`,
    "giu",
  );
  return value
    .replace(quotedRoot, `$1${publicPrefix}/`)
    .replace(attributeRoot, `$1${publicPrefix}/`);
}

function browserCompatibility(value, headers) {
  if (!String(headers["content-type"] || "").includes("text/html")) return value;
  // Local NAS HTTP is not a secure context: randomUUID is absent even though
  // getRandomValues is available. Keep the official bundle unchanged.
  const script = '<script>if(globalThis.crypto&&!crypto.randomUUID){crypto.randomUUID=()=>{const b=crypto.getRandomValues(new Uint8Array(16));b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=Array.from(b,x=>x.toString(16).padStart(2,"0")).join("");return h.slice(0,8)+"-"+h.slice(8,12)+"-"+h.slice(12,16)+"-"+h.slice(16,20)+"-"+h.slice(20)}}<\/script>';
  // https://user:pass@host/ URLs break relative fetch(); reload without the userinfo.
  const clean = '<script>(()=>{try{const u=new URL(location.href);if(u.username||u.password){u.username="";u.password="";location.replace(u.href)}}catch{}})()<\/script>';
  return value.replace(/<head\b[^>]*>/iu, (head) => head + clean + script);
}

function isTextResponse(headers) {
  const type = String(headers["content-type"] || "").toLowerCase();
  // DSH resolves transports against document.baseURI itself. JavaScript also
  // contains logical RPC channels such as /api; prefixing those breaks both
  // channel validation and WebSocket URL resolution. Pass bundles through.
  // API JSON and SSE carry user messages and must remain unchanged too.
  return /(?:text\/html|text\/css|manifest)/u.test(type);
}

const child = spawn(
  process.execPath,
  [
    "--expose-internals",
    dshBin,
    "--profile",
    "web",
    ...launcherArgs,
    ...dshArgs,
    "--host",
    upstreamHost,
    "--port",
    String(upstreamPort),
  ],
  {
    cwd: process.env.DSH_WORKSPACE || "/config/Workspace",
    env: process.env,
    stdio: ["inherit", "pipe", "pipe"],
  },
);
relayStartup(child.stdout, process.stdout);
relayStartup(child.stderr, process.stderr);

child.once("error", (error) => {
  console.error(`[deepseek-harness-proxy] failed to start dsh: ${error.message}`);
  process.exitCode = 1;
});
child.once("exit", (code, signal) => {
  console.error(
    `[deepseek-harness-proxy] dsh exited (${signal || String(code ?? 1)})`,
  );
  process.exit(code ?? 1);
});
process.once("exit", () => {
  if (!child.killed) child.kill("SIGTERM");
});

const server = http.createServer((request, response) => {
  if (!trustedRequest(request)) {
    response.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
    response.end("Forbidden origin");
    return;
  }
  const headers = upstreamHeaders(request);
  headers["accept-encoding"] = "identity";

  function forward(path, bootstrap = false) {
  const proxyRequest = http.request(
    {
      host: upstreamHost,
      port: upstreamPort,
      method: request.method,
      path,
      headers,
    },
    (proxyResponse) => {
      // Only a trusted initial index navigation can establish a browser
      // session. APIs and WebSockets must present the resulting cookie.
      if (!bootstrap && request.method === "GET" && path === "/" &&
          proxyResponse.statusCode === 401 && launchToken) {
        proxyResponse.resume();
        forward(`/?token=${encodeURIComponent(launchToken)}`, true).end();
        return;
      }
      const responseHeaders = { ...proxyResponse.headers };
      if (Array.isArray(responseHeaders["set-cookie"])) {
        responseHeaders["set-cookie"] = responseHeaders["set-cookie"].map(
          (value) => value.replace(/; Path=\/;/u, `; Path=${publicPrefix}/;`),
        );
      }
      if (responseHeaders.location === "./") {
        responseHeaders.location = `${publicPrefix}/`;
      } else
      if (
        typeof responseHeaders.location === "string" &&
        responseHeaders.location.startsWith("/")
      ) {
        responseHeaders.location = `${publicPrefix}${responseHeaders.location}`;
      }

      if (!isTextResponse(responseHeaders)) {
        response.writeHead(proxyResponse.statusCode || 502, responseHeaders);
        proxyResponse.pipe(response);
        return;
      }

      const chunks = [];
      proxyResponse.on("data", (chunk) => chunks.push(chunk));
      proxyResponse.on("end", () => {
        const body = browserCompatibility(rewriteBrowserPaths(Buffer.concat(chunks).toString("utf8")), responseHeaders);
        delete responseHeaders["content-length"];
        delete responseHeaders["content-encoding"];
        delete responseHeaders["transfer-encoding"];
        delete responseHeaders.etag;
        responseHeaders["content-length"] = Buffer.byteLength(body);
        response.writeHead(proxyResponse.statusCode || 502, responseHeaders);
        response.end(body);
      });
    },
  );

  proxyRequest.once("error", (error) => {
    if (!response.headersSent) {
      response.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    response.end(`DeepSeek Harness is starting: ${error.message}\n`);
  });
  return proxyRequest;
  }
  request.pipe(forward(upstreamPath(request.url)));
});

server.on("upgrade", (request, socket, head) => {
  if (!trustedRequest(request)) {
    socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
    return;
  }
  const upstream = net.connect(upstreamPort, upstreamHost);
  upstream.once("connect", () => {
    const lines = [
      `${request.method || "GET"} ${upstreamPath(request.url)} HTTP/${request.httpVersion}`,
    ];
    for (const [name, rawValue] of Object.entries(upstreamHeaders(request))) {
      if (name.toLowerCase() === "host" || rawValue === undefined) continue;
      const values = Array.isArray(rawValue) ? rawValue : [rawValue];
      for (const value of values) lines.push(`${name}: ${value}`);
    }
    lines.push(`host: ${upstreamHost}:${String(upstreamPort)}`, "", "");
    upstream.write(lines.join("\r\n"));
    if (head.length > 0) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.once("error", () => socket.destroy());
});

server.listen(listenPort, listenHost, () => {
  console.log(
    `[deepseek-harness-proxy] http://${listenHost}:${String(listenPort)} -> ${upstreamHost}:${String(upstreamPort)} (${publicPrefix}/)`,
  );
});

function shutdown(signal) {
  server.close();
  if (!child.killed) child.kill(signal);
  setTimeout(() => process.exit(0), 1500).unref();
}

process.once("SIGINT", () => shutdown("SIGINT"));
process.once("SIGTERM", () => shutdown("SIGTERM"));
