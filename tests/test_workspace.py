"""Safety-critical action, transport and MCP regression tests; no real desktop."""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

if importlib.util.find_spec('httpx') is None or importlib.util.find_spec('fastapi') is None:
    raise unittest.SkipTest('Install requirements-workspace-dev.txt for workspace tests')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'root/scripts/workspace'))
import actions
import reader
import desktop

class FakeReader:
    selected = {'kind': 'local'}
    def __init__(self):
        self.messages = [{'id': 'old', 'content': 'existing conversation', 'isSent': False}]
        self.fail_sync = False
    async def get(self, path, params):
        if path == 'chat/contacts':
            return {'contacts': [{'username': 'wxid_target', 'displayName': 'Unique Contact'}]}
        return {'messages': list(self.messages), 'refreshTime': 123}
    async def sync(self):
        if self.fail_sync:
            raise RuntimeError('offline')
    async def get_local(self, path, params):
        return await self.get(path, params)

class FakeDesktop:
    def __init__(self, owner): self.owner = owner
    def open_chat(self, binding): return {'verified': True, 'navigated': False}
    def status(self, binding=None): return {'state': 'ready', 'chat_verified': binding is not None}
    def ready(self, binding): return True
    def send(self, binding, text, submitted):
        submitted()
        self.owner.clicks += 1
        if self.owner.crash:
            raise RuntimeError('simulated lost acknowledgement')
        if self.owner.receipt_failure:
            self.owner.reader.fail_sync = True
        else:
            self.owner.reader.messages.insert(0, {'id': 'new', 'serverIdStr': '9007199254740999', 'content': text, 'isSent': True})

class ActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.reader = FakeReader()
        self.clicks = 0
        self.crash = self.receipt_failure = False
        self.actions = actions.Actions(self.reader, lambda: FakeDesktop(self), Path(self.directory.name))
        self.sleep = patch('actions.asyncio.sleep', new=self.no_sleep)
        self.sleep.start()
    async def asyncTearDown(self):
        self.sleep.stop(); self.directory.cleanup()
    async def no_sleep(self, seconds): pass
    async def prepare(self, key='once', text='Authorized synthetic message'):
        return await self.actions.prepare('account', 'wxid_target', text, key)
    async def test_idempotency_and_verified_isSent_receipt(self):
        first = await self.prepare()
        self.assertEqual(first['id'], (await self.prepare())['id'])
        sent = await self.actions.commit(first['id'])
        self.assertEqual(sent['status'], 'sent')
        self.assertEqual(json.loads(sent['receipt'])['message_id'], '9007199254740999')
        await self.actions.commit(first['id'])
        self.assertEqual(self.clicks, 1)
        with self.assertRaises(ValueError): await self.prepare(text='different payload')
    async def test_ambiguous_identity_blocks_before_prepare(self):
        with patch.object(FakeDesktop, 'ready', side_effect=RuntimeError('unverified')):
            with self.assertRaises(RuntimeError): await self.prepare()
        self.assertEqual(self.actions.list(), [])
        self.assertEqual(self.clicks, 0)
    async def test_changed_conversation_cancels_without_click(self):
        item = await self.prepare()
        self.reader.messages.append({'id':'incoming', 'content':'new incoming message'})
        with self.assertRaises(ValueError): await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'cancelled')
        self.assertEqual(self.clicks, 0)
    async def test_crash_after_submission_never_retries(self):
        item = await self.prepare(); self.crash = True
        with self.assertRaises(RuntimeError): await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'uncertain')
        await self.actions.commit(item['id'])
        self.assertEqual(self.clicks, 1)
    async def test_lost_receipt_becomes_uncertain_immediately(self):
        item = await self.prepare(); self.receipt_failure = True
        self.assertEqual((await self.actions.commit(item['id']))['status'], 'uncertain')
    async def test_cancel_prevents_submission(self):
        item = await self.prepare(); await self.actions.cancel(item['id'])
        self.assertEqual((await self.actions.commit(item['id']))['status'], 'cancelled')
        self.assertEqual(self.clicks, 0)
    async def test_recovery_marks_submitted_uncertain(self):
        item = await self.prepare(); self.actions.update(item['id'], 'submitted')
        recovered = actions.Actions(self.reader, state=Path(self.directory.name))
        self.assertEqual(recovered.get(item['id'])['status'], 'uncertain')
    async def test_remote_reader_cannot_prepare_local_send(self):
        self.reader.selected = {'kind': 'tailscale'}
        with self.assertRaises(ValueError): await self.prepare()
    async def test_fallback_to_remote_during_preparation_blocks_send(self):
        original = self.reader.get
        async def fallback(path, params):
            result = await original(path, params)
            if path == 'chat/messages': self.reader.selected = {'kind': 'direct'}
            return result
        self.reader.get = fallback
        with self.assertRaises(ValueError): await self.prepare()
        self.assertEqual(self.clicks, 0)
        self.assertEqual(self.actions.list(), [])
    async def test_idempotency_includes_schedule(self):
        due = time.time() + 600
        await self.actions.prepare('account', 'wxid_target', 'message', 'scheduled', due)
        with self.assertRaises(ValueError):
            await self.actions.prepare('account', 'wxid_target', 'message', 'scheduled', due + 60)

    async def test_desktop_binding_and_context_use_pinned_local_reader(self):
        from unittest.mock import AsyncMock
        local = self.reader.get_local = AsyncMock(side_effect=self.reader.get)
        # The shared selected connection can change independently of a result.
        # Neither the identity evidence nor the receipt may use that result.
        self.reader.get = AsyncMock(side_effect=AssertionError('automatic transport used'))
        context = await self.actions.context('account', 'wxid_target')
        binding = await self.actions.binding('account', 'wxid_target', context)
        self.assertEqual(binding['username'], 'wxid_target')
        self.assertEqual(local.await_count, 2)

    async def test_schedule_requires_commit_before_automatic_execution(self):
        due = time.time() + 600
        item = await self.actions.prepare('account', 'wxid_target', 'message', 'scheduled', due)
        self.assertEqual(item['status'], 'prepared')
        with self.actions.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM actions WHERE status='scheduled'").fetchone()[0], 0)
        self.assertEqual((await self.actions.commit(item['id']))['status'], 'scheduled')
        self.assertEqual(self.clicks, 0)
        with patch('actions.time.time', return_value=due + 1):
            self.assertEqual((await self.actions.commit(item['id']))['status'], 'sent')
        self.assertEqual(self.clicks, 1)

    async def test_scheduled_pre_input_block_can_recover_without_duplicate_submission(self):
        due = time.time() + 600
        item = await self.actions.prepare('account', 'wxid_target', 'message', 'scheduled-block', due)
        await self.actions.commit(item['id'])
        with patch('actions.time.time', return_value=due + 1), patch.object(FakeDesktop, 'send', side_effect=desktop.DesktopError('WECHAT_LOCKED')):
            with self.assertRaises(desktop.DesktopError): await self.actions.commit(item['id'])
        blocked = self.actions.get(item['id'])
        self.assertEqual(blocked['status'], 'blocked')
        self.assertEqual(json.loads(blocked['receipt'])['code'], 'WECHAT_LOCKED')
        self.assertEqual(self.clicks, 0)
        with patch('actions.time.time', return_value=due + 2):
            self.assertEqual((await self.actions.commit(item['id']))['status'], 'sent')
        self.assertEqual(self.clicks, 1)

    async def test_schedule_block_expires_instead_of_sending_late(self):
        due = time.time() + 600
        item = await self.actions.prepare('account', 'wxid_target', 'message', 'late-schedule', due)
        await self.actions.commit(item['id'])
        self.actions.update(item['id'], 'blocked')
        with patch('actions.time.time', return_value=due + 301):
            with self.assertRaises(ValueError): await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'expired')
        self.assertEqual(self.clicks, 0)

    async def test_reader_outage_waits_before_input_and_context_change_cancels(self):
        item = await self.prepare()
        self.reader.fail_sync = True
        with self.assertRaisesRegex(desktop.DesktopError, 'LOCAL_READER_UNAVAILABLE'):
            await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'blocked')
        self.reader.fail_sync = False
        self.reader.messages.append({'id':'incoming', 'content':'new context'})
        with self.assertRaisesRegex(ValueError, 'Conversation changed'):
            await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'cancelled')
        self.assertEqual(self.clicks, 0)

    async def test_never_retry_a_block_after_editor_write(self):
        item = await self.prepare()
        with patch.object(FakeDesktop, 'send', side_effect=desktop.DesktopError('WECHAT_DIALOG_OPEN', retry_safe=False)):
            with self.assertRaises(desktop.DesktopError): await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'failed')
        await self.actions.commit(item['id'])
        self.assertEqual(self.clicks, 0)

    async def test_cancel_blocked_action_and_expire_old_immediate_retry(self):
        item = await self.prepare()
        self.actions.update(item['id'], 'blocked')
        with patch('actions.time.time', return_value=item['created'] + 121):
            with self.assertRaises(ValueError): await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'expired')
        second = await self.prepare('second')
        self.actions.update(second['id'], 'blocked')
        self.assertEqual((await self.actions.cancel(second['id']))['status'], 'cancelled')

    async def test_future_preparation_still_expires_before_schedule_authorization(self):
        item = await self.actions.prepare('account', 'wxid_target', 'message', 'uncommitted', time.time() + 600)
        with patch('actions.time.time', return_value=item['created'] + 121):
            with self.assertRaises(ValueError): await self.actions.commit(item['id'])
        self.assertEqual(self.actions.get(item['id'])['status'], 'expired')

    async def test_read_only_status_and_open_chat_share_exact_local_binding(self):
        self.assertTrue((await self.actions.desktop_status('account', 'wxid_target'))['chat_verified'])
        with patch.object(FakeDesktop, 'open_chat', return_value={'verified': True, 'navigated': True}) as opened:
            self.assertTrue((await self.actions.open_chat('account', 'wxid_target'))['navigated'])
        self.assertEqual(opened.call_args.args[0]['username'], 'wxid_target')
        self.assertEqual(self.actions.list(), [])
        with self.assertRaises(ValueError): await self.actions.desktop_status('account')
    def test_revision_ignores_refresh_metadata(self):
        self.assertEqual(actions.revision({'messages':self.reader.messages,'time':1}),
                         actions.revision({'messages':self.reader.messages,'time':2}))

class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.file = Path(self.directory.name)/'connections.json'
        self.mock = patch.object(reader, 'CONFIG', self.file); self.mock.start()
    def tearDown(self): self.mock.stop(); self.directory.cleanup()
    def test_public_config_never_returns_tokens_and_preserves_saved_secret(self):
        c = {'id':'a','kind':'direct','url':'https://example.test','token':'private'}
        reader.save_config({'connections':[c]})
        public = reader.public_config()
        self.assertNotIn('private', json.dumps(public))
        reader.save_config(public)
        self.assertEqual(reader.load_config()['connections'][0]['token'], 'private')
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
    def test_bad_urls_duplicate_ids_and_malformed_config_rejected(self):
        for url in ['file:///etc/passwd','https://user:secret@example.test','https://example.test/?token=secret']:
            with self.assertRaises(ValueError):
                reader.save_config({'connections':[{'id':'a','kind':'direct','url':url}]})
        c = {'id':'a','kind':'direct','url':'https://example.test'}
        with self.assertRaises(ValueError): reader.save_config({'connections':[c,c]})
        with self.assertRaises(ValueError): reader.save_config([])

class ReaderTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        self.httpx = httpx
        self.requests = []
        self.client_class = httpx.AsyncClient

    def clients(self, handler):
        def record(request):
            self.requests.append(request)
            return handler(request)
        transport = self.httpx.MockTransport(record)
        return patch.object(reader.httpx, 'AsyncClient',
            side_effect=lambda **kwargs: self.client_class(transport=transport, **kwargs))

    async def test_local_is_preferred_over_reachable_authenticated_remote(self):
        def handler(request):
            return self.httpx.Response(200, json={'accounts':['a']} if request.url.path.endswith('accounts') else {'status':'ok'})
        remote = {'id':'direct','kind':'direct','url':'https://remote.test','token':'secret'}
        with self.clients(handler), patch.object(reader, 'load_config', return_value={'connections':[remote]}):
            r = reader.Reader()
            self.assertEqual((await r.probe())['selected'], 'local')
        outgoing = [x for x in self.requests if x.url.host == 'remote.test']
        self.assertTrue(outgoing)
        self.assertTrue(all(x.headers['authorization'] == 'Bearer secret' for x in outgoing))
        self.assertTrue(all('authorization' not in x.headers for x in self.requests if x.url.host != 'remote.test'))

    async def test_real_request_failure_falls_back_once(self):
        def handler(request):
            if request.url.path.endswith('chat/messages'):
                return self.httpx.Response(503) if request.url.host != 'remote.test' else self.httpx.Response(200, json={'messages':[{'id':'remote'}]})
            return self.httpx.Response(200, json={'accounts':['a']} if request.url.path.endswith('accounts') else {'status':'ok'})
        remote = {'id':'direct','kind':'direct','url':'https://remote.test','token':'secret'}
        with self.clients(handler), patch.object(reader, 'load_config', return_value={'connections':[remote]}):
            r = reader.Reader()
            self.assertEqual((await r.get('chat/messages'))['messages'][0]['id'], 'remote')
            self.assertEqual(r.selected['id'], 'direct')
        self.assertEqual(sum(x.url.path.endswith('chat/messages') for x in self.requests), 2)

    async def test_local_action_reads_never_fall_back_to_remote(self):
        with self.clients(lambda request: self.httpx.Response(503)):
            r = reader.Reader()
            r.selected = {'id':'direct','kind':'direct','url':'https://remote.test','token':'secret'}
            with self.assertRaisesRegex(RuntimeError, 'Local desktop'):
                await r.get_local('chat/messages')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(str(self.requests[0].url), reader.LOCAL + '/api/chat/messages')

    async def test_sync_failure_has_recoverable_local_service_error(self):
        with self.clients(lambda request: self.httpx.Response(503)):
            with self.assertRaisesRegex(RuntimeError, 'synchronization is unavailable'):
                await reader.Reader().sync()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(str(self.requests[0].url), reader.LOCAL + '/api/linux/sync')

class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'WEHARBOR_TOKEN_FILE':self.directory.name+'/token', 'WEHARBOR_WORKSPACE_STATE':self.directory.name+'/state'})
        self.env.start()
        with patch.object(reader, 'STATE', Path(self.directory.name)/'state'), patch.object(actions, 'STATE', Path(self.directory.name)/'state'):
            # Actions' default argument was evaluated at import time.
            original = actions.Actions
            with patch.object(actions, 'Actions', lambda r: original(r, state=Path(self.directory.name)/'state')):
                import server
                self.server = server
        from fastapi.testclient import TestClient
        self.client = TestClient(self.server.app)
    async def asyncTearDown(self): self.env.stop(); self.directory.cleanup()
    async def test_auth_origin_and_guard(self):
        self.assertEqual(self.client.get('/actions').status_code,401)
        headers={'Authorization':'Bearer '+self.server.TOKEN}
        self.assertEqual(self.client.get('/actions',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/actions',headers=headers|{'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.post('/sync',headers={'X-WeHarbor-Browser':'authenticated'}).status_code,403)
    async def test_mcp_initialize_list_and_type_validation(self):
        initialize = await self.server.rpc({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})
        self.assertEqual(initialize['result']['protocolVersion'],'2025-11-25')
        result = await self.server.rpc({'id':2,'method':'tools/list'})
        self.assertIn('wechat_commit_send',[x['name'] for x in result['result']['tools']])
        bad = await self.server.rpc({'id':3,'method':'tools/call','params':{'name':'wechat_messages','arguments':{'account':'a','username':'u','limit':True}}})
        self.assertTrue(bad['result']['isError'])
        self.assertIsNone(await self.server.rpc({'method':'notifications/initialized'}))
        malformed = await self.server.rpc({'id':4,'method':'tools/call','params':[]})
        self.assertEqual(malformed['error']['code'], -32602)

    async def test_navigation_auth_schema_and_structured_block_recovery(self):
        from unittest.mock import AsyncMock
        headers = {'Authorization': 'Bearer ' + self.server.TOKEN}
        self.assertEqual(self.client.post('/desktop/open', json={'account':'a','username':'u'}).status_code, 401)
        self.assertEqual(self.client.post('/desktop/open', headers=headers, json={'account':'a','username':'u','text':'no'}).status_code, 400)
        with patch.object(self.server.actions, 'open_chat', new=AsyncMock(side_effect=desktop.DesktopError('EXISTING_DRAFT'))):
            response = self.client.post('/desktop/open', headers=headers, json={'account':'a','username':'u'})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['code'], 'EXISTING_DRAFT')
            self.assertTrue(response.json()['recovery'])
            result = await self.server.rpc({'id':5, 'method':'tools/call', 'params':{'name':'wechat_open_chat','arguments':{'account':'a','username':'u'}}})
            self.assertTrue(result['result']['isError'])
            self.assertEqual(json.loads(result['result']['content'][0]['text'])['code'], 'EXISTING_DRAFT')

class DesktopIdentityTests(unittest.TestCase):
    class Node:
        def __init__(self, name='', role='label', states=(), children=()):
            self.name, self.role, self.states = name, role, set(states)
            self.children, self.parent = list(children), None
            for child in children: child.parent = self
        def get_name(self): return self.name
        def get_role_name(self): return self.role
        def get_state_set(self): return self
        def contains(self, state): return state in self.states
        def get_child_count(self): return len(self.children)
        def get_child_at_index(self, i): return self.children[i]
        def get_parent(self): return self.parent
    def driver(self, fingerprints, visible=True, sidebar=False):
        n = self.Node
        editor = n(states=['show','edit','multi'])
        send = n('Send', 'button', ['show'])
        evidence = [n('Unique Contact', states=['show'] if visible else [])] + [n(v, states=['show'] if visible else []) for v in fingerprints]
        chat = n(role='panel', children=[editor, send] + ([] if sidebar else evidence))
        frame = n(role='frame', children=[chat] + (evidence if sidebar else []))
        d = object.__new__(desktop.Desktop)
        d.a = SimpleNamespace(StateType=SimpleNamespace(EDITABLE='edit', MULTI_LINE='multi', SHOWING='show'))
        d.nodes = lambda: d._subtree(frame)
        d._account = lambda account: None
        d._identity = lambda binding: None
        d._foreground = lambda editor: None
        return d
    def test_visible_unique_title_is_still_required_after_memory_identity(self):
        binding = {'account':'a','username':'wxid_target','names':['Unique Contact'],'messages':['recent message one','recent message two']}
        self.driver(binding['messages'])._controls(binding)
        self.driver([])._controls(binding)
        for d in [self.driver(binding['messages'], sidebar=True), self.driver([], visible=False)]:
            with self.assertRaises(desktop.DesktopError): d._controls(binding)
        driver = self.driver([])
        driver._identity = lambda _: (_ for _ in ()).throw(desktop.DesktopError('wrong session'))
        with self.assertRaises(desktop.DesktopError): driver._controls(binding)

    def test_qt_search_editor_and_disabled_send_are_not_ambiguous(self):
        binding = {'account':'a','username':'target','names':['Unique Contact']}
        d = self.driver([])
        frame = d.nodes()[0]
        chat = frame.children[0]
        editor, send = chat.children[:2]
        chat.children.remove(send)
        for name in ['发送收藏', '发送文件']:
            child = self.Node(name, 'button', ['show']); child.parent = chat
            chat.children.append(child)
        search = self.Node(role='text', states=['show','edit','multi'])
        search.parent = frame; frame.children.append(search)
        self.assertEqual(d._controls(binding), (editor, None))
        with self.assertRaises(desktop.DesktopError):
            d._controls(binding, require_send=True)
        chat.children.append(send)
        self.assertEqual(d._controls(binding, require_send=True), (editor, send))

    def test_two_composers_in_the_titled_pane_fail_closed(self):
        d = self.driver([])
        chat = d.nodes()[1]
        extra = self.Node(states=['show','edit','multi']); extra.parent = chat
        chat.children.append(extra)
        with self.assertRaises(desktop.DesktopError):
            d._controls({'account':'a','username':'target','names':['Unique Contact']})

    def test_text_interface_uses_gi_static_dispatch(self):
        d = self.driver([])
        d.a.Text = SimpleNamespace(get_text=lambda node, start, end: '')
        binding = {'account':'a','username':'target','names':['Unique Contact']}
        self.assertTrue(d.ready(binding))
        d.a.Text.get_text = lambda node, start, end: 'existing draft'
        with self.assertRaisesRegex(desktop.DesktopError, 'EXISTING_DRAFT'):
            d.ready(binding)
