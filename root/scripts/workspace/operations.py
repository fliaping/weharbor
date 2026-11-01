"""Durable desktop operations with exact identities and at-most-once effects."""
import asyncio
import hashlib
import json
import os
import stat
import time
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

from actions import message_id, revision, rows
from desktop import Desktop
from labels import LABEL_WRITES

DEFINITIONS = {
    'send-file': {'path': 'string'},
    'send-image': {'path': 'string'},
    'send-video': {'path': 'string'},
    'chat-mark-read': {},
    'chat-set-mute': {'muted': 'boolean'},
    'contact-remark': {'text': 'string'},
    'group-rename': {'text': 'string'},
    'group-my-nick': {'text': 'string'},
    'group-notice': {'text': 'string'},
    'contact-create-label': {'name': 'string'},
    'contact-set-labels': {'labels': 'array'},
    'contact-rename-label': {'name': 'string', 'new_name': 'string'},
    'contact-delete-label': {'name': 'string'},
}
MEDIA = {'send-file', 'send-image', 'send-video'}
MAX_ATTACHMENT = 100 * 1024 * 1024
UPLOADS = Path(os.environ.get('WEHARBOR_UPLOAD_DIR', '/config/.local/share/weharbor/uploads'))


def validate(operation, account, username, parameters, key):
    if operation not in DEFINITIONS:
        raise ValueError('Unsupported desktop operation')
    if not all(isinstance(v, str) and v.strip() and len(v) <= 256 for v in [account, username, key]) or len(key) > 128:
        raise ValueError('Account, exact username and idempotency key are required')
    fields = DEFINITIONS[operation]
    if not isinstance(parameters, dict) or set(parameters) != set(fields):
        raise ValueError('Expected operation fields: ' + ', '.join(fields))
    for name, kind in fields.items():
        if type(parameters[name]) is not {'string': str, 'boolean': bool, 'array': list}[kind]:
            raise ValueError('Invalid type for ' + name)
    if operation.startswith('group-') and not username.endswith('@chatroom'):
        raise ValueError('Group operations require an exact @chatroom username')
    if operation in {'contact-remark', 'contact-set-labels'} and username.endswith('@chatroom'):
        raise ValueError('Use group operations for a chatroom')
    if operation in LABEL_WRITES:
        names = parameters['labels'] if operation == 'contact-set-labels' else list(parameters.values())
        if len(names) > 100 or any(not isinstance(v, str) or not v.strip() or v != v.strip() or len(v) > 64 or any(ord(c) < 32 for c in v) for v in names):
            raise ValueError('Labels require distinct names of 1 to 64 characters, at most 100 labels')
        if operation == 'contact-set-labels' and len(set(names)) != len(names):
            raise ValueError('Duplicate labels are not allowed')
    if 'text' in parameters:
        limit = 2000 if operation == 'group-notice' else 128
        if len(parameters['text']) > limit or '\x00' in parameters['text'] or (operation == 'group-rename' and not parameters['text'].strip()):
            raise ValueError('Invalid setting text or text exceeds the limit')


def attachment(parameters, operation, uploads=None):
    """Only explicitly uploaded, private regular files can leave this machine."""
    root = (uploads or UPLOADS).resolve()
    raw = Path(parameters['path'])
    path = raw.resolve()
    if not raw.is_absolute() or not path.is_relative_to(root) or raw.is_symlink():
        raise ValueError('Attachments must be regular files inside the WeHarbor upload directory')
    # Reject symlinked directories too; never follow an uploaded link to secrets.
    if any(p.is_symlink() for p in [raw, *raw.parents] if p != root.parent and p.is_relative_to(root)):
        raise ValueError('Attachment symlinks are not supported')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ATTACHMENT or info.st_mode & 0o022:
            raise ValueError('Attachment must be a nonempty private regular file of at most 100 MiB')
        sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
        head, total = b'', 0
        while chunk := source.read(1024 * 1024):
            head = head or chunk[:32]
            total += len(chunk)
            if total > MAX_ATTACHMENT:
                raise ValueError('Attachment exceeds the limit')
            sha.update(chunk); md5.update(chunk)
        if total != info.st_size:
            raise ValueError('Attachment changed while reading')
    if operation == 'send-image' and not (head.startswith((b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'GIF87a', b'GIF89a', b'BM')) or (head.startswith(b'RIFF') and head[8:12] == b'WEBP')):
        raise ValueError('Unsupported image signature; upload JPEG, PNG, GIF, BMP or WebP')
    if operation == 'send-video' and not (head[4:8] == b'ftyp' or head.startswith(b'\x1aE\xdf\xa3')):
        raise ValueError('Unsupported video signature; upload MP4/MOV or WebM')
    return {'path': str(path), 'size': total, 'sha256': sha.hexdigest(), 'md5': md5.hexdigest()}


def matches_attachment(message, operation, metadata):
    """A new same-type message alone is never proof of the uploaded bytes."""
    if message.get('isSent', message.get('isSend', message.get('is_send', message.get('isSelf')))) not in [True, 1]:
        return False
    value = message.get('type', message.get('localType', message.get('local_type', message.get('msgType'))))
    try:
        kind = int(value) & 0xffffffff
    except (TypeError, ValueError):
        return False
    if kind != {'send-file': 49, 'send-image': 3, 'send-video': 43}[operation]:
        return False
    content = message.get('rawContent') or message.get('raw_content') or message.get('content') or ''
    if not isinstance(content, str) or len(content) > 1024 * 1024 or '<!DOCTYPE' in content.upper() or '<!ENTITY' in content.upper():
        return False
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return False
    if operation == 'send-file':
        app = root if root.tag == 'appmsg' else root.find('.//appmsg')
        if app is None or app.findtext('type') != '6' or app.findtext('title') != Path(metadata['path']).name:
            return False
        try:
            if int(app.findtext('appattach/totallen') or '-1') != metadata['size']:
                return False
        except ValueError:
            return False
        hashes = [app.findtext('md5'), app.findtext('appattach/filemd5'), app.findtext('appattach/md5')]
    else:
        element = root if root.tag == ('img' if operation == 'send-image' else 'videomsg') else root.find('.//' + ('img' if operation == 'send-image' else 'videomsg'))
        if element is None:
            return False
        hashes = [element.get('md5'), element.get('filemd5'), element.get('rawmd5')]
    return any(isinstance(h, str) and h.lower() == metadata['md5'] for h in hashes)


class Operations:
    def __init__(self, actions, desktop_factory=Desktop, uploads=None):
        self.actions, self.reader = actions, actions.reader
        self.desktop_factory, self.uploads = desktop_factory, uploads
        # One lock coordinates text, attachment, profile and scheduled actions.
        self.lock = actions.lock
        with actions.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, idem TEXT UNIQUE, operation TEXT, account TEXT, username TEXT, payload TEXT, status TEXT, created REAL, baseline TEXT, receipt TEXT)')
            db.execute("UPDATE operations SET status='uncertain' WHERE status='submitted'")

    def get(self, identifier):
        with self.actions.db() as db:
            row = db.execute('SELECT * FROM operations WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Unknown desktop operation')
        return dict(row) | {'parameters': json.loads(row['payload']), 'idempotency_key': row['idem']}

    def list(self):
        with self.actions.db() as db:
            return [dict(row) | {'idempotency_key': row['idem']} for row in db.execute('SELECT id,idem,operation,account,username,status,created,receipt FROM operations ORDER BY created DESC LIMIT 100')]

    def update(self, identifier, status, receipt):
        with self.actions.db() as db:
            db.execute('UPDATE operations SET status=?,receipt=? WHERE id=?', (status, json.dumps(receipt, ensure_ascii=False), identifier))

    def submitted(self, identifier, operation, parameters, metadata):
        # Check bytes again immediately before selecting the file. A change
        # while the desktop chooser was open must not submit different content.
        if operation in MEDIA and attachment(parameters, operation, self.uploads) != metadata:
            raise RuntimeError('Attachment changed before submission')
        self.update(identifier, 'submitted', {'reason': 'Effect boundary reached; never automatically retry'})

    async def context(self, account, username):
        # Pin both transport and data source, independent of connection probes.
        return await self.reader.get_local('chat/messages', {'account': account, 'username': username, 'source': 'decrypted', 'limit': 20, 'order': 'desc'})

    async def binding(self, account, username, context):
        return await self.actions.binding(account, username, context)

    async def list_labels(self, account, username):
        if not all(isinstance(v, str) and v.strip() and len(v) <= 256 for v in [account, username]):
            raise ValueError('Account and exact anchor contact username are required')
        async with self.lock:
            current = await self.context(account, username)
            binding = await self.binding(account, username, current)
            result = await asyncio.to_thread(self.desktop_factory().label_snapshot, binding, 'contact-list-labels')
            return {'account': account, **result, 'complete': True, 'source': 'wechat-accessibility'}

    async def prepare(self, operation, account, username, parameters, idempotency_key):
        validate(operation, account, username, parameters, idempotency_key)
        async with self.lock:
            with self.actions.db() as db:
                if db.execute('SELECT 1 FROM actions WHERE idem=?', (idempotency_key,)).fetchone():
                    raise ValueError('Idempotency key already belongs to a text action')
                old = db.execute('SELECT id FROM operations WHERE idem=?', (idempotency_key,)).fetchone()
            if old:
                item = self.get(old['id'])
                if (item['operation'], item['account'], item['username'], item['parameters']) != (operation, account, username, parameters):
                    raise ValueError('Idempotency key already belongs to another payload')
                return item
            metadata = await asyncio.to_thread(attachment, parameters, operation, self.uploads) if operation in MEDIA else None
            current = await self.context(account, username)
            binding = await self.binding(account, username, current)
            # Mark-read explicitly navigates the chat at commit. Preparation
            # must not mark it read as a side effect.
            if operation != 'chat-mark-read':
                await asyncio.to_thread(self.desktop_factory().ready, binding)
            labels = await asyncio.to_thread(self.desktop_factory().label_snapshot, binding, operation) if operation in LABEL_WRITES else None
            identifier = uuid.uuid4().hex
            with self.actions.db() as db:
                db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)', (identifier, idempotency_key, operation, account, username, json.dumps(parameters, ensure_ascii=False), 'prepared', time.time(), json.dumps({'messages': current, 'attachment': metadata, 'labels': labels}, ensure_ascii=False), ''))
            return self.get(identifier)

    async def commit(self, identifier):
        async with self.lock:
            item = self.get(identifier)
            if item['status'] != 'prepared':
                return item
            if time.time() - item['created'] > 120:
                self.update(identifier, 'expired', {'reason': 'Preparation expired'})
                return self.get(identifier)
            baseline = json.loads(item['baseline'])
            operation, parameters = item['operation'], item['parameters']
            try:
                if operation in MEDIA:
                    metadata = await asyncio.to_thread(attachment, parameters, operation, self.uploads)
                    if metadata != baseline['attachment']:
                        self.update(identifier, 'cancelled', {'reason': 'Attachment bytes changed after preparation'})
                        return self.get(identifier)
                await self.reader.sync()
                current = await self.context(item['account'], item['username'])
                if revision(current) != revision(baseline['messages']):
                    self.update(identifier, 'cancelled', {'reason': 'Conversation changed; prepare again'})
                    return self.get(identifier)
                binding = await self.binding(item['account'], item['username'], current)
                if operation in LABEL_WRITES:
                    labels = await asyncio.to_thread(self.desktop_factory().label_snapshot, binding, operation)
                    if labels != baseline.get('labels'):
                        self.update(identifier, 'cancelled', {'reason': 'Labels changed after preparation; prepare again'})
                        return self.get(identifier)
                result = await asyncio.to_thread(self.desktop_factory().operation, binding, operation, parameters,
                    lambda: self.submitted(identifier, operation, parameters, baseline['attachment']))
                if operation not in MEDIA:
                    if not isinstance(result, dict) or result.get('verified') is not True:
                        raise RuntimeError('Desktop mutation has no verified readback')
                    self.update(identifier, 'completed', result)
                    return self.get(identifier)
                if self.get(identifier)['status'] != 'submitted':
                    raise RuntimeError('Attachment driver did not persist its submission boundary')
                before = {message_id(m) for m in rows(current, 'messages', 'items')}
                for _ in range(6):
                    await asyncio.sleep(2)
                    await self.reader.sync()
                    after = await self.context(item['account'], item['username'])
                    found = [m for m in rows(after, 'messages', 'items') if message_id(m) and message_id(m) not in before and matches_attachment(m, operation, metadata)]
                    if len(found) == 1:
                        self.update(identifier, 'sent', {'message_id': message_id(found[0]), 'sha256': metadata['sha256'], 'meaning': 'matching attachment hash observed in a new local self-message; not recipient delivery'})
                        return self.get(identifier)
                self.update(identifier, 'uncertain', {'reason': 'No unique attachment hash receipt; inspect WeChat, do not resend'})
            except BaseException:
                submitted = self.get(identifier)['status'] == 'submitted'
                self.update(identifier, 'uncertain' if submitted else 'failed', {'reason': 'Operation interrupted after submission; do not retry' if submitted else 'Desktop precondition or validation failed before submission'})
                raise
            return self.get(identifier)

    async def cancel(self, identifier):
        async with self.lock:
            if self.get(identifier)['status'] != 'prepared':
                raise ValueError('Only prepared operations can be cancelled')
            self.update(identifier, 'cancelled', {'reason': 'Cancelled before submission'})
            return self.get(identifier)

    async def execute(self, operation, account, username, idempotency_key, **parameters):
        item = await self.prepare(operation, account, username, parameters, idempotency_key)
        return await self.commit(item['id'])
