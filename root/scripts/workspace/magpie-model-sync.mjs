// Keep dsh's preset "magpie" route listing the models Magpie's gateway serves.
// dsh rejects a custom route without models ("resolves no models"), so the list is
// synced from GET /v1/models. Only a list WeHarbor owns is touched: `models: []`
// or one carrying the SYNC_MARK; a list Magpie itself writes is left alone.
import fs from 'node:fs';
import path from 'node:path';

export const SYNC_MARK = '# weharbor: synced from magpie /v1/models';
const BLOCK_START = /^- id: llm-pi-ai # magpie\s*$/;

/**
 * Return patch text with the magpie route's models replaced by `ids`, or the
 * original text when the block is absent or its list is not WeHarbor's.
 */
export function syncPatchText(text, ids) {
  const lines = text.split('\n');
  const start = lines.findIndex(line => BLOCK_START.test(line));
  if (start < 0) return text;
  let end = lines.findIndex((line, index) => index > start && /^- /.test(line));
  if (end < 0) end = lines.length;
  let modelsAt = -1;
  for (let i = start + 1; i < end; i++) if (/^\s+models:/.test(lines[i])) { modelsAt = i; break; }
  if (modelsAt < 0) return text;
  const indent = lines[modelsAt].match(/^(\s*)/)[1];
  const rest = lines[modelsAt].slice(indent.length + 'models:'.length).trim();
  if (rest !== '[]' && rest !== SYNC_MARK) return text;
  let listEnd = modelsAt + 1;
  while (listEnd < end && lines[listEnd].trim() !== '' &&
         lines[listEnd].match(/^(\s*)/)[1].length > indent.length) listEnd++;
  const unique = [...new Set(ids.filter(id => typeof id === 'string' && id.trim()))];
  const replacement = unique.length
    ? [`${indent}models: ${SYNC_MARK}`, ...unique.map(id => `${indent}  - id: ${JSON.stringify(id)}`)]
    : [`${indent}models: []`];
  const next = [...lines.slice(0, modelsAt), ...replacement, ...lines.slice(listEnd)].join('\n');
  return next;
}

export async function fetchModelIds(gateway, key, fetchImpl = fetch) {
  const response = await fetchImpl(`http://${gateway}/v1/models`, {
    headers: {authorization: `Bearer ${key}`}, signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`magpie /v1/models: HTTP ${response.status}`);
  const body = await response.json();
  return (Array.isArray(body?.data) ? body.data : []).map(model => model?.id).filter(Boolean);
}

export async function syncOnce({patchPath, gateway, key, fetchImpl}) {
  let text;
  try { text = fs.readFileSync(patchPath, 'utf8'); } catch { return false; }
  const ids = await fetchModelIds(gateway, key, fetchImpl);
  const next = syncPatchText(text, ids);
  if (next === text) return false;
  const temp = path.join(path.dirname(patchPath), `.${path.basename(patchPath)}.weharbor-${process.pid}`);
  fs.writeFileSync(temp, next, {mode: fs.statSync(patchPath).mode & 0o777});
  fs.renameSync(temp, patchPath);
  return true;
}

export function startModelSync({patchPath, gateway, key, intervalMs = 15000, log = console.error}) {
  let lastError = '';
  const tick = async () => {
    try {
      if (await syncOnce({patchPath, gateway, key})) log('magpie: synced dsh model list from /v1/models');
      lastError = '';
    } catch (error) {
      const message = String(error?.message || error);
      if (message !== lastError) log('magpie: model sync skipped: ' + message);
      lastError = message;
    }
  };
  setTimeout(tick, 3000);
  return setInterval(tick, intervalMs);
}
