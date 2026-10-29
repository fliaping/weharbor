// Behavior checks for syncing dsh's magpie route models from Magpie's /v1/models.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const {syncPatchText, syncOnce, SYNC_MARK} = await import(process.argv[2]);

const seeded = `- id: llm-pi-ai # magpie
  name: "@deepseek-ai/dsh-llm-pi-ai"
  config:
    providers:
      magpie:
        displayName: Magpie
        apiKeyEnv: MAGPIE_GATEWAY_KEY
        api: openai-completions
        baseURL: http://127.0.0.1:3425/v1
        models: []
- id: ui-settings-general
  name: "@deepseek-ai/dsh-client-ui-settings-general"
  config:
    welcomeNoticeVersion: 2026-09-28.1
`;
const synced = syncPatchText(seeded, ['deepseek-chat', 'qwen/qwen3', 'deepseek-chat']);
assert.ok(synced.includes(`        models: ${SYNC_MARK}\n          - id: "deepseek-chat"\n          - id: "qwen/qwen3"\n- id: ui-settings-general`));
assert.equal(synced.match(/deepseek-chat/g).length, 1, 'duplicates collapse');
assert.ok(synced.endsWith('welcomeNoticeVersion: 2026-09-28.1\n'), 'other entries untouched');
assert.equal(syncPatchText(synced, ['deepseek-chat', 'qwen/qwen3']), synced, 'idempotent');
const replaced = syncPatchText(synced, ['glm-5']);
assert.ok(replaced.includes('          - id: "glm-5"\n- id: ui-settings-general') && !replaced.includes('qwen'));
assert.equal(syncPatchText(replaced, []), seeded, 'empty upstream returns to models: []');
// A list Magpie (or the user) wrote is not WeHarbor's to rewrite.
const owned = seeded.replace('models: []', 'models:\n          - id: "picked-by-magpie"');
assert.equal(syncPatchText(owned, ['other']), owned);
assert.equal(syncPatchText('[]\n', ['x']), '[]\n', 'no magpie block, no change');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'magpie-sync-'));
const patchPath = path.join(dir, 'cordis.patch.yml');
fs.writeFileSync(patchPath, seeded, {mode: 0o600});
let auth = '';
const fetchImpl = async (url, init) => {
  assert.equal(url, 'http://127.0.0.1:3425/v1/models');
  auth = init.headers.authorization;
  return new Response(JSON.stringify({object: 'list', data: [{id: 'm1'}, {id: 'm2'}]}), {status: 200});
};
assert.equal(await syncOnce({patchPath, gateway: '127.0.0.1:3425', key: 'magpie', fetchImpl}), true);
assert.equal(auth, 'Bearer magpie');
assert.ok(fs.readFileSync(patchPath, 'utf8').includes('- id: "m2"'));
assert.equal(fs.statSync(patchPath).mode & 0o777, 0o600, 'mode preserved');
assert.equal(await syncOnce({patchPath, gateway: '127.0.0.1:3425', key: 'magpie', fetchImpl}), false);
await assert.rejects(syncOnce({patchPath, gateway: '127.0.0.1:3425', key: 'magpie',
  fetchImpl: async () => new Response('no', {status: 401})}));
fs.rmSync(dir, {recursive: true});
console.log('magpie model sync ok');
