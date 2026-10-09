/* A live remote desktop: never persist authenticated pages or chat data. */
"use strict";
self.addEventListener("install", (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate" || event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(() => new Response(
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="theme-color" content="#101c2d"><title>WeHarbor｜微港</title>' +
    '<style>body{margin:0;background:#101c2d;color:#edf5fc;font:17px system-ui;' +
    'min-height:100vh;display:grid;place-items:center}main{max-width:32em;padding:32px}' +
    'p{line-height:1.7;color:#bccddd}a{display:inline-block;padding:12px 18px;' +
    'background:#56dfbb;color:#101c2d;border-radius:12px;text-decoration:none}</style>' +
    '</head><body><main><h1>WeHarbor｜微港</h1><p>无法连接桌面。' +
    '请检查网络和服务器，恢复连接后重试。微信与 WeFlow 需要在线使用。</p>' +
    '<a href="./">重新连接</a></main></body></html>',
    {status: 503, headers: {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}}
  )));
});
