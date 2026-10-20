"""Persistent prepare/commit actions, at-most-once submission and DB receipts."""
import asyncio
import hashlib
import json
import os
import sqlite3
import time
import uuid
from reader import STATE
from desktop import Desktop, DesktopError

def rows(payload, *keys):
    if isinstance(payload, list):
        return payload
    for key in keys + ('data',):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            found = rows(value, *keys)
            if found:
                return found
    return []

def message_id(m):
    return str(m.get('serverIdStr') or m.get('serverId') or m.get('server_id') or m.get('id') or m.get('localId') or m.get('local_id') or '')

def revision(payload):
    # Ignore refresh timing and pagination metadata, preserve message changes.
    messages = rows(payload, 'messages', 'items')
    return hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

class Actions:
    def __init__(self, reader, desktop_factory=Desktop, state=STATE):
        self.reader, self.desktop_factory = reader, desktop_factory
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = state / 'actions.sqlite3'
        self.lock = asyncio.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, idem TEXT UNIQUE, account TEXT, username TEXT, text TEXT, status TEXT, created REAL, due REAL, baseline TEXT, receipt TEXT)')
            # A crash after submission is not permission for a second click.
            db.execute("UPDATE actions SET status='uncertain' WHERE status='submitted'")
        os.chmod(self.path, 0o600)

    def db(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def get(self, action_id):
        with self.db() as db:
            r = db.execute('SELECT * FROM actions WHERE id=?', (action_id,)).fetchone()
        if not r:
            raise ValueError('Unknown action')
        return dict(r)

    def list(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT id,account,username,status,created,due,receipt FROM actions ORDER BY created DESC LIMIT 100')]

    def update(self, action_id, status, receipt=''):
        with self.db() as db:
            db.execute('UPDATE actions SET status=?, receipt=? WHERE id=?', (status, receipt, action_id))

    async def context(self, account, username):
        result = await self.reader.get_local('chat/messages', {'account': account, 'username': username, 'limit': 20, 'order': 'desc', 'source': 'decrypted'})
        self.require_local()
        return result

    def require_local(self):
        if not self.reader.selected or self.reader.selected['kind'] != 'local':
            raise ValueError('Sending requires the local account and desktop')

    async def binding(self, account, username, context):
        contacts = rows(await self.reader.get_local('chat/contacts', {'account': account, 'source': 'decrypted'}), 'contacts', 'items')
        self.require_local()
        target = [c for c in contacts if (c.get('username') or c.get('userName')) == username]
        if len(target) != 1:
            raise ValueError('The exact username must resolve to one contact')
        names = {target[0].get(k) for k in ['displayName', 'remark', 'nickname'] if target[0].get(k)}
        names = {name.strip() for name in names if isinstance(name, str) and name.strip()}
        unique = sorted(name for name in names if sum(any(c.get(k) == name for k in ['displayName', 'remark', 'nickname']) for c in contacts) == 1)
        fingerprints = list(dict.fromkeys(m.get('content') or m.get('text') for m in rows(context, 'messages', 'items')
            if isinstance(m.get('content') or m.get('text'), str) and 8 <= len(m.get('content') or m.get('text')) <= 2000))
        alias = target[0].get('alias')
        if not isinstance(alias, str):
            alias = None
        return {'account': account, 'username': username, 'names': sorted(names), 'alias': alias,
                'search_queries': list(dict.fromkeys(unique + ([alias] if alias else []) + sorted(names))),
                'messages': fingerprints}

    async def desktop_status(self, account=None, username=None):
        if bool(account) != bool(username):
            raise ValueError('Provide both account and exact username, or neither')
        async with self.lock:
            binding = None
            if account:
                binding = await self.binding(account, username, {})
            return await asyncio.to_thread(self.desktop_factory().status, binding)

    async def open_chat(self, account, username):
        if not all(isinstance(x, str) and x.strip() for x in [account, username]):
            raise ValueError('Account and exact username are required')
        async with self.lock:
            binding = await self.binding(account, username, {})
            return await asyncio.to_thread(self.desktop_factory().open_chat, binding)

    def failure(self, item, exc):
        submitted = self.get(item['id'])['status'] == 'submitted'
        detail = exc.public() if isinstance(exc, DesktopError) else {
            'code': 'ACTION_FAILED', 'message': '操作未完成', 'recovery': '检查微信和服务状态。', 'retryable': False}
        status = ('uncertain' if submitted else 'expired' if detail['code'] == 'ACTION_EXPIRED'
                  else 'blocked' if detail['retryable'] else 'failed')
        self.update(item['id'], status, json.dumps(detail, ensure_ascii=False))

    async def prepare(self, account, username, text, idempotency_key, due=None):
        if not all(isinstance(x, str) and x.strip() for x in [account, username, text, idempotency_key]):
            raise ValueError('Account, exact username, text and idempotency_key are required')
        if len(text) > 4000 or len(idempotency_key) > 128:
            raise ValueError('Text or idempotency key exceeds the limit')
        if due is not None and (isinstance(due, bool) or not isinstance(due, (int, float)) or not time.time() < due < time.time() + 366 * 86400):
            raise ValueError('Schedule must be in the next year (Unix seconds)')
        async with self.lock:
            with self.db() as db:
                old = db.execute('SELECT id,account,username,text,due FROM actions WHERE idem=?', (idempotency_key,)).fetchone()
            if old:
                if (old['account'], old['username'], old['text'], old['due']) != (account, username, text, due):
                    raise ValueError('Idempotency key already belongs to another payload')
                return self.get(old['id'])
            contacts = await self.reader.get('chat/contacts', {'account': account, 'source': 'decrypted'})
            matches = [c for c in rows(contacts, 'contacts', 'items') if (c.get('username') or c.get('userName')) == username]
            if len(matches) != 1:
                raise ValueError('The exact username must resolve to one contact')
            # Remote readers cannot authorize local desktop actions.
            self.require_local()
            baseline = await self.context(account, username)
            binding = await self.binding(account, username, baseline)
            driver = self.desktop_factory()
            await asyncio.to_thread(driver.open_chat, binding)
            await asyncio.to_thread(driver.ready, binding)
            action_id = uuid.uuid4().hex
            with self.db() as db:
                db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (action_id, idempotency_key, account, username, text, 'prepared', time.time(), due, json.dumps(baseline), ''))
            return self.get(action_id)

    async def commit(self, action_id):
        async with self.lock:
            item = self.get(action_id)
            if item['status'] not in ['prepared', 'scheduled', 'blocked']:
                return item
            if (((item['status'] == 'prepared' or not item['due']) and time.time() - item['created'] > 120)
                    or (item['due'] and time.time() > item['due'] + 300)):
                self.update(action_id, 'expired')
                raise ValueError('Prepared action expired; prepare again')
            if item['due'] and item['due'] > time.time():
                if item['status'] == 'prepared':
                    self.update(action_id, 'scheduled', 'Authorized for the requested due time')
                return self.get(action_id)
            try:
                await self.reader.sync()
                current = await self.context(item['account'], item['username'])
            except (OSError, RuntimeError):
                exc = DesktopError('LOCAL_READER_UNAVAILABLE')
                self.failure(item, exc)
                raise exc from None
            if revision(current) != revision(json.loads(item['baseline'])):
                self.update(action_id, 'cancelled', 'Conversation changed; prepare a new action')
                raise ValueError('Conversation changed')
            try:
                driver = self.desktop_factory()
                binding = await self.binding(item['account'], item['username'], current)
                binding['expires_at'] = item['due'] + 300 if item['due'] else item['created'] + 120
                await asyncio.to_thread(driver.send, binding, item['text'],
                    lambda: self.update(action_id, 'submitted'))
            except Exception as exc:
                self.failure(item, exc)
                raise
            baseline_ids = {message_id(m) for m in rows(current, 'messages', 'items')}
            for _ in range(6):
                await asyncio.sleep(2)
                try:
                    await self.reader.sync()
                    after = await self.context(item['account'], item['username'])
                except Exception:
                    self.update(action_id, 'uncertain', 'Submitted, but receipt service is unavailable; do not resend')
                    return self.get(action_id)
                found = []
                for m in rows(after, 'messages', 'items'):
                    own = m.get('isSent', m.get('isSend', m.get('is_send', m.get('isSelf', False))))
                    content = m.get('content') or m.get('text')
                    if own in [1, True] and content == item['text'] and message_id(m) and message_id(m) not in baseline_ids:
                        found.append(m)
                if len(found) == 1:
                    self.update(action_id, 'sent', json.dumps({'message_id': message_id(found[0]), 'meaning': 'observed in local sent-message database'}))
                    return self.get(action_id)
            self.update(action_id, 'uncertain', 'No unique matching self-message was observed; do not resend automatically')
            return self.get(action_id)

    async def cancel(self, action_id):
        async with self.lock:
            if self.get(action_id)['status'] not in ['prepared', 'scheduled', 'blocked']:
                raise ValueError('Only pending actions can be cancelled')
            self.update(action_id, 'cancelled')
            return self.get(action_id)

    async def scheduler(self):
        while True:
            with self.db() as db:
                due = [r[0] for r in db.execute("SELECT id FROM actions WHERE status IN ('scheduled','blocked') AND due IS NOT NULL AND due<=?", (time.time(),))]
            for action_id in due:
                try:
                    await self.commit(action_id)
                except Exception:
                    if self.get(action_id)['status'] == 'scheduled':
                        self.update(action_id, 'failed', 'Scheduled action could not be verified')
            await asyncio.sleep(5)
