// Behavior checks for the dock's pure helpers and its early capture-phase key hook.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const listeners = [];
const store = {};
const win = {
  addEventListener: (type, fn, options) => listeners.push({type, fn, options}),
};
const context = {
  window: win, navigator: {platform: "Linux x86_64"},
  document: {readyState: "loading", addEventListener: () => {}},
  localStorage: {getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }},
};
context.globalThis = context;
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context);
const dock = context.WeHarborDock;
const {matchShortcut, nextView, distanceToRect, shortcutLabel, VIEW_ORDER, NEAR_PX, COLLAPSE_DELAY_MS} = dock.logic;

const key = (code, mods = {}) => ({code, ctrlKey: false, altKey: true, shiftKey: false, metaKey: false, ...mods});
assert.deepEqual({...matchShortcut(key("Digit1"))}, {type: "view", view: "desktop"});
assert.deepEqual({...matchShortcut(key("Digit3"))}, {type: "view", view: "magpie"});
assert.deepEqual({...matchShortcut(key("Digit5"))}, {type: "view", view: "connections"});
assert.equal(matchShortcut(key("Digit6")), null);
assert.equal(matchShortcut(key("Digit9")), null);
assert.equal(matchShortcut(key("Backquote")).type, "cycle");
assert.equal(matchShortcut(key("Digit0")).type, "panel");
assert.equal(matchShortcut(key("Space")).type, "panel");
// macOS Option+digit types "¡™£" etc.: matching uses the physical code, not event.key.
assert.deepEqual({...matchShortcut({...key("Digit2"), key: "™"})}, {type: "view", view: "analysis"});
// Only Alt alone: Ctrl+Alt (AltGr on Windows layouts), Shift, Meta and plain keys pass through,
// as do numpad digits (Windows Alt+numpad character entry) and IME composition.
assert.equal(matchShortcut(key("Digit1", {altKey: false})), null);
assert.equal(matchShortcut(key("Digit1", {ctrlKey: true})), null);
assert.equal(matchShortcut(key("Digit1", {shiftKey: true})), null);
assert.equal(matchShortcut(key("Digit1", {metaKey: true})), null);
assert.equal(matchShortcut(key("Numpad1")), null);
assert.equal(matchShortcut(key("KeyS")), null, "WeChat's Alt+S send and Alt+A screenshot are untouched");
assert.equal(matchShortcut(key("KeyA")), null);
assert.equal(matchShortcut(key("Tab")), null);
assert.equal(matchShortcut(key("F4")), null);
assert.equal(matchShortcut(key("Digit1", {isComposing: true})), null);
assert.equal(matchShortcut({code: "Digit1"}), null);
assert.equal(nextView("desktop"), "analysis");
assert.equal(nextView(VIEW_ORDER.at(-1)), "desktop");
assert.equal(nextView("desktop", -1), VIEW_ORDER.at(-1));
assert.equal(shortcutLabel("assistant"), "Alt+4");
const handle = {left: 990, right: 1000, top: 300, bottom: 352};
assert.equal(distanceToRect(995, 320, handle), 0);
assert.equal(distanceToRect(950, 320, handle), 40);
assert.ok(distanceToRect(900, 320, handle) > NEAR_PX);
assert.ok(NEAR_PX >= 48 && NEAR_PX <= 64);
assert.ok(COLLAPSE_DELAY_MS >= 300 && COLLAPSE_DELAY_MS <= 600);

// The window keydown hook is capture-phase and installed at script evaluation time.
const keydown = listeners.find((l) => l.type === "keydown");
assert.ok(keydown && keydown.options === true, "keydown hook must use capture");
const keyup = listeners.find((l) => l.type === "keyup");
const event = (code, extra = {}) => {
  const e = {...key(code), repeat: false, prevented: 0, stopped: 0, ...extra};
  e.preventDefault = () => { e.prevented++; };
  e.stopImmediatePropagation = () => { e.stopped++; };
  return e;
};
// Before the dock mounts, shortcuts pass through untouched.
let e = event("Digit2"); keydown.fn(e); assert.equal(e.prevented, 0);
const actions = [];
dock.handleShortcut = (a) => actions.push(a);
e = event("Digit2"); keydown.fn(e);
assert.equal(e.prevented, 1); assert.equal(e.stopped, 1);
assert.equal(actions.at(-1).view, "analysis");
const up = event("Digit2"); keyup.fn(up); assert.equal(up.stopped, 1, "matching keyup is swallowed too");
const other = event("KeyA", {altKey: false}); keydown.fn(other); keyup.fn(other);
assert.equal(other.prevented + other.stopped, 0, "ordinary keys reach the remote desktop");
e = event("Digit2", {repeat: true}); keydown.fn(e); assert.equal(actions.length, 1, "auto-repeat doesn't re-trigger");
// Disabling shortcuts in dock settings lets the keys through.
store["weharbor-dock-shortcuts"] = "false";
e = event("Digit3"); keydown.fn(e); assert.equal(e.prevented, 0); assert.equal(actions.length, 1);

console.log("dock logic ok");

// Chrome hides user:pass@ from location.href but keeps it in document.URL, which relative
// fetches and iframe src resolve against: the dock reloads clean before mounting anything.
{
  const replaced = [];
  const ctx = {
    window: {addEventListener: () => { throw new Error("must not hook before the clean reload"); }},
    navigator: {platform: "Linux x86_64"},
    document: {URL: "https://u:p%40ss@127.0.0.1:3301/?x=1#h", readyState: "loading", addEventListener: () => {}},
    location: {href: "https://127.0.0.1:3301/?x=1#h", replace: (url) => replaced.push(url)},
    localStorage: {getItem: () => null, setItem: () => {}},
    URL,
  };
  ctx.globalThis = ctx;
  vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), ctx);
  assert.deepEqual(replaced, ["https://127.0.0.1:3301/?x=1#h"]);
  assert.equal(ctx.WeHarborDock, undefined);
}
console.log("dock credential reload ok");

// macOS labels the same physical shortcuts with the Option key.
{
  const ctx = {window: {addEventListener: () => {}}, navigator: {platform: "MacIntel"},
    document: {readyState: "loading", addEventListener: () => {}}, localStorage: {getItem: () => null, setItem: () => {}}};
  ctx.globalThis = ctx;
  vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), ctx);
  assert.equal(ctx.WeHarborDock.logic.shortcutLabel("magpie"), "⌥3");
  assert.equal(ctx.WeHarborDock.logic.matchShortcut({code: "Digit3", key: "£", altKey: true}).view, "magpie");
}
console.log("dock mac labels ok");
