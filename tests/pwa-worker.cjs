const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const handlers = {};
let calls = 0;
let fail = false;
const context = {
  self: {
    addEventListener: (name, fn) => { handlers[name] = fn; },
    skipWaiting: async () => {}, clients: { claim: async () => {} }
  },
  fetch: async () => {
    calls++;
    if (fail) throw new Error("offline");
    return new Response("Login required", {status: 401});
  },
  Response,
  // Access to persistent browser caches is a test failure.
  get caches() { throw new Error("must not persist authenticated data"); }
};
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context);
const run = (mode, method = "GET") => {
  let response;
  handlers.fetch({request: {mode, method}, respondWith: (r) => { response = r; }});
  return response;
};
(async () => {
  const denied = await run("navigate");
  assert.equal(denied.status, 401);
  assert.equal(await denied.text(), "Login required");
  assert.equal(run("cors"), undefined);
  assert.equal(run("same-origin"), undefined);
  assert.equal(run("navigate", "POST"), undefined);
  assert.equal(calls, 1);
  fail = true;
  const offline = await run("navigate");
  assert.equal(offline.status, 503);
  assert.equal(offline.headers.get("Cache-Control"), "no-store");
  assert.match(await offline.text(), /重新连接/);
  console.log("PWA Worker network, authentication and offline checks passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
