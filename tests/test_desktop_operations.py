"""Synthetic operation receipts and AT-SPI controls; never uses a real account."""
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

if importlib.util.find_spec('httpx') is None or importlib.util.find_spec('fastapi') is None:
    raise unittest.SkipTest('Install requirements-workspace-dev.txt for operation tests')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'root/scripts/workspace'))
import actions
import desktop
import operations


class LocalReader:
    selected = {'kind': 'local'}
    def __init__(self):
        self.messages = [{'id': 'old', 'content': 'existing message'}]
    async def get_local(self, path, params):
        if path == 'chat/contacts':
            return {'contacts': [{'username': 'wxid_target', 'displayName': 'Only Target'},
                                 {'username': 'group@chatroom', 'displayName': 'Only Group'}]}
        return {'messages': list(self.messages)}
    async def sync(self):
        return {}


class OperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.uploads = self.root / 'uploads'
        self.uploads.mkdir(mode=0o700)
        self.file = self.uploads / 'example.txt'
        self.file.write_bytes(b'authorized attachment')
        self.file.chmod(0o600)
        self.reader = LocalReader()
        self.base = actions.Actions(self.reader, state=self.root / 'state')
        self.effects, self.ready = 0, 0
        self.crash = self.no_receipt = self.no_boundary = self.bad_readback = False
        owner = self
        class Driver:
            def ready(self, binding):
                owner.ready += 1
            def operation(self, binding, operation, parameters, submitted):
                if not owner.no_boundary:
                    submitted()
                owner.effects += 1
                if owner.crash:
                    raise RuntimeError('simulated interrupted effect')
                if operation in operations.MEDIA:
                    if not owner.no_receipt:
                        data = operations.attachment(parameters, operation, owner.uploads)
                        owner.reader.messages.insert(0, owner.message(data))
                    return {'submitted': True}
                return {'verified': not owner.bad_readback, 'meaning': 'synthetic UI readback'}
        self.ops = operations.Operations(self.base, Driver, self.uploads)
        self.sleep = patch('operations.asyncio.sleep', new=AsyncMock())
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def message(self, metadata, identifier='new', md5=None):
        digest = md5 or metadata['md5']
        return {'id': identifier, 'isSent': True, 'type': 49,
                'rawContent': '<msg><appmsg><title>example.txt</title><type>6</type><md5>' + digest + '</md5><appattach><totallen>' + str(metadata['size']) + '</totallen></appattach></appmsg></msg>'}

    async def prepare(self, operation='send-file', parameters=None, key='one'):
        if parameters is None:
            parameters = {'path': str(self.file)}
        return await self.ops.prepare(operation, 'account', 'wxid_target', parameters, key)

    async def test_prepare_preserves_draft_and_idempotency_then_submits_once(self):
        item = await self.prepare()
        self.assertEqual(self.effects, 0)
        self.assertEqual(item['id'], (await self.prepare())['id'])
        first, second = await asyncio.gather(self.ops.commit(item['id']), self.ops.commit(item['id']))
        self.assertEqual([first['status'], second['status']], ['sent', 'sent'])
        self.assertEqual(self.effects, 1)
        self.assertEqual(json.loads(first['receipt'])['message_id'], 'new')
        self.assertEqual(self.ops.list()[0]['idempotency_key'], 'one')

    async def test_key_cannot_switch_target_operation_or_bytes(self):
        await self.prepare()
        with self.assertRaises(ValueError):
            await self.ops.prepare('chat-set-mute', 'account', 'wxid_target', {'muted': True}, 'one')
        with self.assertRaises(ValueError):
            await self.ops.prepare('send-file', 'account', 'group@chatroom', {'path': str(self.file)}, 'one')

    async def test_changed_attachment_cancels_before_any_desktop_effect(self):
        item = await self.prepare()
        self.file.write_bytes(b'changed')
        self.assertEqual((await self.ops.commit(item['id']))['status'], 'cancelled')
        self.assertEqual(self.effects, 0)

    async def test_text_and_desktop_actions_cannot_share_a_key(self):
        await self.prepare()
        with self.assertRaisesRegex(ValueError, 'desktop operation'):
            await self.base.prepare('account', 'wxid_target', 'authorized text', 'one')
        with self.base.db() as db:
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)',
                       ('text-id', 'text-key', 'account', 'wxid_target', 'text', 'prepared', time.time(), None, '{}', ''))
        with self.assertRaisesRegex(ValueError, 'text action'):
            await self.prepare(key='text-key')
        self.assertEqual(self.effects, 0)

    async def test_changed_conversation_cancels_before_any_desktop_effect(self):
        item = await self.prepare()
        self.reader.messages.append({'id': 'incoming', 'content': 'new incoming'})
        self.assertEqual((await self.ops.commit(item['id']))['status'], 'cancelled')
        self.assertEqual(self.effects, 0)

    async def test_expired_and_cancelled_actions_never_click(self):
        item = await self.prepare()
        with patch('operations.time.time', return_value=time.time() + 121):
            self.assertEqual((await self.ops.commit(item['id']))['status'], 'expired')
        item2 = await self.prepare(key='two')
        await self.ops.cancel(item2['id'])
        self.assertEqual((await self.ops.commit(item2['id']))['status'], 'cancelled')
        self.assertEqual(self.effects, 0)

    async def test_interruption_and_restart_never_resubmit(self):
        item = await self.prepare()
        self.crash = True
        with self.assertRaises(RuntimeError):
            await self.ops.commit(item['id'])
        self.assertEqual(self.ops.get(item['id'])['status'], 'uncertain')
        await self.ops.commit(item['id'])
        self.assertEqual(self.effects, 1)
        self.ops.update(item['id'], 'submitted', {})
        recovered = operations.Operations(self.base, uploads=self.uploads)
        self.assertEqual(recovered.get(item['id'])['status'], 'uncertain')

    async def test_missing_or_ambiguous_hash_receipt_is_uncertain(self):
        self.no_receipt = True
        item = await self.prepare()
        self.assertEqual((await self.ops.commit(item['id']))['status'], 'uncertain')
        await self.ops.commit(item['id'])
        self.assertEqual(self.effects, 1)

    async def test_failure_before_submission_is_not_uncertain(self):
        item = await self.prepare()
        self.ops.desktop_factory = lambda: SimpleNamespace(operation=lambda *a: (_ for _ in ()).throw(RuntimeError('no accessible control')))
        with self.assertRaises(RuntimeError):
            await self.ops.commit(item['id'])
        self.assertEqual(self.ops.get(item['id'])['status'], 'failed')

    async def test_driver_cannot_claim_sent_without_persisted_boundary(self):
        item = await self.prepare()
        self.no_boundary = True
        with self.assertRaises(RuntimeError):
            await self.ops.commit(item['id'])
        self.assertNotEqual(self.ops.get(item['id'])['status'], 'sent')

    async def test_settings_require_readback_and_preserve_boolean(self):
        item = await self.prepare('chat-set-mute', {'muted': False})
        self.assertEqual((await self.ops.commit(item['id']))['status'], 'completed')
        self.bad_readback = True
        second = await self.prepare('contact-remark', {'text': 'Authorized remark'}, 'two')
        with self.assertRaises(RuntimeError):
            await self.ops.commit(second['id'])
        self.assertEqual(self.ops.get(second['id'])['status'], 'uncertain')

    async def test_mark_read_preparation_does_not_navigate(self):
        item = await self.prepare('chat-mark-read', {})
        self.assertEqual((self.ready, self.effects), (0, 0))
        self.assertEqual((await self.ops.commit(item['id']))['status'], 'completed')

    async def test_group_and_parameter_validation(self):
        for operation, values in [('group-rename', {'text': 'Group'}), ('chat-set-mute', {'muted': 1}),
                                  ('contact-remark', {'text': 'a', 'extra': 'b'})]:
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                await self.prepare(operation, values)
        item = await self.ops.prepare('group-rename', 'account', 'group@chatroom', {'text': 'Group'}, 'group')
        self.assertEqual(item['status'], 'prepared')

    async def test_final_boundary_rechecks_file_after_chooser_delay(self):
        item = await self.prepare()
        def change_then_submit(binding, operation, parameters, before):
            self.file.write_bytes(b'replaced while chooser was open')
            before()
        self.ops.desktop_factory = lambda: SimpleNamespace(operation=change_then_submit)
        with self.assertRaisesRegex(RuntimeError, 'changed before'):
            await self.ops.commit(item['id'])
        self.assertEqual(self.ops.get(item['id'])['status'], 'failed')

    def test_attachment_rejects_links_external_files_fifo_and_wrong_media(self):
        link = self.uploads / 'link'
        link.symlink_to(self.file)
        fifo = self.uploads / 'pipe'
        os.mkfifo(fifo)
        for path, operation in [(link, 'send-file'), (fifo, 'send-file'), (self.root / 'outside', 'send-file'), (self.file, 'send-image'), (self.file, 'send-video')]:
            with self.subTest(path=path, operation=operation), self.assertRaises((ValueError, OSError)):
                operations.attachment({'path': str(path)}, operation, self.uploads)
        self.file.chmod(0o666)
        with self.assertRaises(ValueError):
            operations.attachment({'path': str(self.file)}, 'send-file', self.uploads)

    def test_attachment_receipt_checks_direction_type_name_size_and_digest(self):
        metadata = operations.attachment({'path': str(self.file)}, 'send-file', self.uploads)
        good = self.message(metadata)
        self.assertTrue(operations.matches_attachment(good, 'send-file', metadata))
        for bad in [good | {'isSent': False}, good | {'type': 3}, self.message(metadata, md5='0' * 32),
                    good | {'rawContent': good['rawContent'].replace('example.txt', 'other.txt')},
                    good | {'rawContent': good['rawContent'].replace(str(metadata['size']), '999')},
                    good | {'rawContent': '<!DOCTYPE msg><msg/>'}]:
            self.assertFalse(operations.matches_attachment(bad, 'send-file', metadata))


class AccessibleNode:
    def __init__(self, name='', role='label', states=('show',), children=(), text='', action=None):
        self.name, self.role, self.states = name, role, set(states)
        self.children, self.text, self.action, self.parent = list(children), text, action, None
        for child in self.children:
            child.parent = self
    def get_name(self): return self.name
    def get_role_name(self): return self.role
    def get_state_set(self): return self
    def contains(self, state): return state in self.states
    def get_child_count(self): return len(self.children)
    def get_child_at_index(self, i): return self.children[i]
    def get_parent(self): return self.parent
    def get_text_iface(self): return self
    def get_text(self, start, end): return self.text
    def get_editable_text_iface(self): return self
    def set_text_contents(self, value): self.text = value; return True
    def get_component_iface(self): return self
    def grab_focus(self): return True
    def get_action_iface(self): return self if self.action else None
    def get_n_actions(self): return 1
    def get_action_name(self, i): return 'click'
    def do_action(self, i): self.action(); return True


class AccessibleDriverTests(unittest.TestCase):
    def driver(self):
        d = object.__new__(desktop.Desktop)
        d.a = SimpleNamespace(StateType=SimpleNamespace(EDITABLE='edit', MULTI_LINE='multi', SHOWING='show', CHECKED='checked'))
        d._account = lambda account: None
        d._foreground = lambda node: None
        return d

    def test_moments_refresh_only_activates_exact_refresh_control_and_rechecks_account(self):
        events = []
        refresh = AccessibleNode('刷新', 'button', action=lambda: events.append('refresh'))
        like = AccessibleNode('赞', 'button', action=lambda: self.fail('interaction must not be clicked'))
        panel = AccessibleNode('朋友圈', 'frame', children=[refresh, like])
        d = self.driver()
        d.nodes = lambda: [panel, refresh, like]
        d._account = lambda account: events.append(('account', account))
        result = d.refresh_moments('exact')
        self.assertTrue(result['refresh_requested'])
        self.assertEqual(events, [('account', 'exact'), ('account', 'exact'), 'refresh'])

        second = AccessibleNode('Moments', 'dialog')
        entry = AccessibleNode('朋友圈', 'button', action=lambda: self.fail('must not navigate ambiguous windows'))
        d.nodes = lambda: [panel, second, entry]
        with self.assertRaisesRegex(desktop.DesktopError, 'AMBIGUOUS'):
            d.refresh_moments('exact')

    def test_moments_refresh_rejects_drafts_ambiguous_controls_and_changed_accounts(self):
        refresh = AccessibleNode('刷新', 'button', action=lambda: self.fail('must not click'))
        panel = AccessibleNode('朋友圈', 'frame', children=[refresh])
        draft = AccessibleNode(states=['show', 'edit', 'multi'], text='preserve draft')
        d = self.driver()
        d.nodes = lambda: [draft, panel, refresh]
        with self.assertRaisesRegex(desktop.DesktopError, 'EXISTING_DRAFT'):
            d.refresh_moments('exact')
        draft.text = ''
        duplicate = AccessibleNode('刷新', 'button', action=lambda: self.fail('ambiguous click'))
        panel.children.append(duplicate)
        with self.assertRaisesRegex(desktop.DesktopError, 'AMBIGUOUS'):
            d.refresh_moments('exact')
        panel.children.pop()
        checks = []
        def account_check(account):
            checks.append(account)
            if len(checks) == 2:
                raise desktop.DesktopError('ACCOUNT_CHANGED')
        d._account = account_check
        with self.assertRaisesRegex(desktop.DesktopError, 'ACCOUNT_CHANGED'):
            d.refresh_moments('exact')

    def test_mute_sets_explicit_state_and_never_toggles_an_already_correct_value(self):
        n = AccessibleNode
        checkbox = n('消息免打扰', 'check box')
        calls = []
        def toggle():
            calls.append('toggle')
            checkbox.states.symmetric_difference_update({'checked'})
        checkbox.action = toggle
        panel = n(role='panel', children=[checkbox])
        d = self.driver()
        d._settings = lambda binding: panel
        result = d.operation({'account': 'a'}, 'chat-set-mute', {'muted': True}, lambda: calls.append('submitted'))
        self.assertTrue(result['muted'])
        d.operation({'account': 'a'}, 'chat-set-mute', {'muted': True}, lambda: calls.append('submitted'))
        self.assertEqual(calls, ['submitted', 'toggle'])

    def test_duplicate_setting_controls_fail_before_effect(self):
        panel = AccessibleNode(role='panel', children=[AccessibleNode('消息免打扰', 'check box'), AccessibleNode('消息免打扰', 'check box')])
        d = self.driver()
        d._settings = lambda binding: panel
        with self.assertRaisesRegex(desktop.DesktopError, 'AMBIGUOUS'):
            d.operation({'account': 'a'}, 'chat-set-mute', {'muted': True}, lambda: self.fail('must not submit'))

    def test_search_preserves_existing_draft_and_rejects_fuzzy_results(self):
        d = self.driver()
        draft = AccessibleNode(states=['show', 'edit', 'multi'], text='user draft')
        search = AccessibleNode('搜索', 'entry', states=['show', 'edit'])
        binding = {'account': 'a', 'username': 'wxid_exact', 'names': ['Only Target'], 'messages': []}
        d.nodes = lambda: [draft, search]
        with self.assertRaisesRegex(desktop.DesktopError, 'EXISTING_DRAFT'):
            d.open_chat(binding, lambda: self.fail('must not submit'))
        draft.text = ''
        fuzzy = AccessibleNode('Only Target', 'list item', children=[AccessibleNode('Only Target')], action=lambda: self.fail('fuzzy result clicked'))
        d.nodes = lambda: [draft, search, fuzzy]
        d._wait = lambda find: find()
        with self.assertRaisesRegex(desktop.DesktopError, 'SEARCH_IDENTITY_UNVERIFIED'):
            d.open_chat(binding, lambda: self.fail('must not submit'))
        self.assertEqual(search.text, '')

    def test_search_selects_only_one_exact_identity_and_restores_search(self):
        d = self.driver()
        search = AccessibleNode('搜索', 'entry', states=['show', 'edit'])
        events = []
        target = AccessibleNode(role='list item', children=[AccessibleNode('Only Target'), AccessibleNode('微信号：alias_exact')], action=lambda: events.append('open'))
        d.nodes = lambda: [search, target]
        d._wait = lambda find: find()
        d._controls = lambda binding: events.append('verify')
        binding = {'account': 'a', 'username': 'wxid_exact', 'alias': 'alias_exact', 'names': ['Only Target']}
        self.assertTrue(d.open_chat(binding, lambda: events.append('submitted'))['verified'])
        self.assertEqual(events, ['submitted', 'open', 'verify'])
        self.assertEqual(search.text, '')

    def test_accessibility_inspection_cannot_activate_unnamed_actions(self):
        node = AccessibleNode('Send', 'button')
        d = self.driver()
        with self.assertRaisesRegex(desktop.DesktopError, 'UNAVAILABLE'):
            d._activate(node)

    def attachment_driver(self, preview_target='Only Target'):
        n, events = AccessibleNode, []
        field = n('File name', 'entry', states=['show', 'edit'])
        preview = n('Send File', 'dialog', children=[n('file.txt'), n(preview_target), n('Send', 'button', action=lambda: events.append('send'))])
        chooser = n('Open File', 'dialog', children=[field, n('Open', 'button')])
        visible = [chooser]
        def choose():
            events.append('open')
            visible[:] = [preview]
        chooser.children[1].action = choose
        pane = n(role='panel', children=[n('Send File', 'button', action=lambda: events.append('chooser'))])
        d = self.driver()
        d._blank = lambda binding: (None, None, pane)
        d._controls = lambda binding: events.append('identity')
        d.nodes = lambda: list(visible)
        return d, field, events

    def test_attachment_opens_exact_file_then_verifies_preview_target(self):
        d, field, events = self.attachment_driver()
        with patch('desktop.time.sleep'):
            result = d.operation({'account': 'a', 'names': ['Only Target']}, 'send-file', {'path': '/private/file.txt'}, lambda: events.append('submitted'))
        self.assertEqual(field.text, '/private/file.txt')
        self.assertEqual(events, ['chooser', 'identity', 'submitted', 'open', 'identity', 'send'])
        self.assertTrue(result['submitted'])

    def test_attachment_preview_cannot_send_to_a_different_target(self):
        d, field, events = self.attachment_driver(preview_target='Different Target')
        with patch('desktop.time.sleep'), self.assertRaisesRegex(desktop.DesktopError, 'IDENTITY_UNVERIFIED'):
            d.operation({'account': 'a', 'names': ['Only Target']}, 'send-file', {'path': '/private/file.txt'}, lambda: events.append('submitted'))
        self.assertIn('submitted', events)
        self.assertNotIn('send', events)

    def test_setting_save_requires_persisted_readback_after_reopening(self):
        field = AccessibleNode('Remark', 'entry', states=['show', 'edit'], text='Original')
        events = []
        panel = AccessibleNode(role='panel', children=[field, AccessibleNode('Save', 'button', action=lambda: events.append('save'))])
        d = self.driver()
        def settings(binding, reopen=False):
            if reopen:
                events.append('reopen')
                field.text = 'Original'  # Simulate a rejected server-side save.
            return panel
        d._settings = settings
        with self.assertRaisesRegex(desktop.DesktopError, 'SETTING_READBACK_FAILED'):
            d.operation({'account': 'a'}, 'contact-remark', {'text': 'Approved'}, lambda: events.append('submitted'))
        self.assertEqual(events, ['submitted', 'save', 'reopen'])


class OperationApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        factory = actions.Actions
        with patch.dict(os.environ, {'WEHARBOR_TOKEN_FILE': str(root / 'token')}), patch.object(actions, 'Actions', lambda r: factory(r, state=root / 'state')):
            spec = importlib.util.spec_from_file_location('operation_test_server', ROOT / 'root/scripts/workspace/server.py')
            self.server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.server)
        self.server.UPLOADS = root / 'uploads'
        from fastapi.testclient import TestClient
        self.client = TestClient(self.server.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer ' + self.server.TOKEN}

    def test_upload_authentication_private_mode_and_limit_cleanup(self):
        self.assertEqual(self.client.put('/attachments/file.txt', content=b'x').status_code, 401)
        mkdir = Path.mkdir
        def inherited_mode(path, *args, **kwargs):
            mkdir(path, *args, **kwargs)
            if path == self.server.UPLOADS or path.parent == self.server.UPLOADS:
                path.chmod(0o705)  # NAS inheritance can override mkdir(mode=0700).
        with patch.object(Path, 'mkdir', inherited_mode):
            response = self.client.put('/attachments/file.txt', content=b'uploaded', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        path = Path(response.json()['path'])
        self.assertEqual(path.read_bytes(), b'uploaded')
        self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.parent.parent.stat().st_mode & 0o777, 0o700)
        before = set(self.server.UPLOADS.iterdir())
        with patch.object(self.server, 'MAX_ATTACHMENT', 3):
            self.assertEqual(self.client.put('/attachments/large.txt', content=b'1234', headers=self.headers).status_code, 400)
        self.assertEqual(set(self.server.UPLOADS.iterdir()), before)
        self.assertEqual(self.client.put('/attachments/empty.txt', content=b'', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.put('/attachments/file.txt', content=b'x', headers=self.headers | {'Origin': 'https://evil.test'}).status_code, 403)

    def test_mcp_advertises_real_operations_and_accepts_boolean_without_integer_confusion(self):
        tools = asyncio.run(self.server.rpc({'id': 1, 'method': 'tools/list'}))['result']['tools']
        self.assertEqual(len(tools), 33)
        by_name = {t['name']: t for t in tools}
        self.assertFalse(by_name['wechat_chat_set_mute']['annotations']['readOnlyHint'])
        self.assertTrue(by_name['wechat_contact_lookup']['annotations']['readOnlyHint'])
        self.assertTrue(by_name['wechat_contact_list_labels']['annotations']['readOnlyHint'])
        self.assertEqual(by_name['wechat_contact_set_labels']['inputSchema']['properties']['labels']['items'], {'type': 'string'})
        self.assertNotIn('wechat_sns_like', by_name)
        self.assertNotIn('wechat_contact_search', by_name)
        mock = AsyncMock(return_value={'status': 'completed'})
        with patch.object(self.server.operations, 'execute', mock):
            response = asyncio.run(self.server.rpc({'id': 2, 'method': 'tools/call', 'params': {'name': 'wechat_chat_set_mute', 'arguments': {'account': 'a', 'username': 'u', 'muted': False, 'idempotency_key': 'key'}}}))
        self.assertNotIn('isError', response['result'])
        mock.assert_awaited_once_with('chat-set-mute', account='a', username='u', muted=False, idempotency_key='key')
