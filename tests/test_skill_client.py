import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/weflow-api'
spec = importlib.util.spec_from_file_location('skill_client', SKILL / 'scripts/weflow_api.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class APIStub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        self.server.requests.append((parsed.path, query, self.headers.get('Authorization')))
        mode = self.server.mode
        if mode == 'redirect':
            self.send_response(302)
            self.send_header('Location', self.server.redirect_url)
            self.end_headers()
            return
        if parsed.path == '/api/v1/push/messages':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            if mode == 'idle':
                self.wfile.flush()
                self.server.finished.wait(1)
            else:
                self.wfile.write(b': heartbeat\n\nevent: message.new\nid: 7\ndata: {"rawid":"example",\ndata: "content":"test"}\n\nevent: message.revoke\ndata: {"rawid":"example"}\n\n')
                self.wfile.flush()
            return
        status = 401 if mode == 'unauthorized' else 200
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if parsed.path == '/api/v1/media/images/example.png':
            self.wfile.write(b'example image bytes')
        elif mode == 'unauthorized':
            self.wfile.write(b'{"error":"' + self.server.test_token.encode() + b'"}')
        elif mode == 'failure':
            self.wfile.write(b'{"success":false,"error":"private database details"}')
        elif mode == 'bad-json':
            self.wfile.write(b'private invalid payload')
        elif parsed.path == '/health':
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.wfile.write(json.dumps({'success': True, 'count': 0, 'hasMore': False,
                                        'messages': [], 'query': query}).encode())


class SkillClientTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), APIStub)
        self.server.daemon_threads = True
        self.server.requests = []
        self.server.mode = 'normal'
        self.server.finished = threading.Event()
        self.server.test_token = 'mock-credential-not-a-real-secret'
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.finished.set()
        self.server.shutdown()
        self.server.server_close()

    def cli(self, *args, token=True, extra_env=None):
        env = {'WEFLOW_API_BASE': self.base}
        if token:
            env['WEFLOW_API_TOKEN'] = self.server.test_token
        env.update(extra_env or {})
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch('sys.argv', ['weflow_api.py', *args]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = client.main()
        self.assertNotIn(self.server.test_token, stdout.getvalue() + stderr.getvalue())
        return code, stdout.getvalue(), stderr.getvalue()

    def test_health_does_not_read_or_send_credentials(self):
        code, out, _ = self.cli('health', extra_env={'WEFLOW_API_TOKEN_FILE': '/nonexistent'})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['status'], 'ok')
        self.assertIsNone(self.server.requests[0][2])

    def test_missing_token_never_makes_authenticated_request(self):
        code, _, error = self.cli('sessions', token=False)
        self.assertEqual(code, 1)
        self.assertIn('WEFLOW_API_TOKEN', error)
        self.assertEqual(self.server.requests, [])

    def test_query_encoding_time_units_pagination_and_bearer_header(self):
        code, _, _ = self.cli('messages', '--talker', 'demo@chatroom', '--keyword', '项目 & 计划',
                              '--start', '1790812800', '--end', '20261007', '--offset', '100')
        self.assertEqual(code, 0)
        path, query, auth = self.server.requests[0]
        self.assertEqual(path, '/api/v1/messages')
        self.assertEqual(query['keyword'], ['项目 & 计划'])
        self.assertEqual(query['start'], ['1790812800000'])
        self.assertEqual(query['end'], ['20261007'])
        self.assertEqual(query['offset'], ['100'])
        self.assertEqual(query['media'], ['0'])
        self.assertEqual(auth, 'Bearer ' + self.server.test_token)
        self.assertNotIn('access_token', query)

    def test_group_chatlab_and_timeline_parameters(self):
        self.assertEqual(self.cli('group-members', '--chatroom-id', 'demo@chatroom', '--counts')[0], 0)
        self.assertEqual(self.server.requests[-1][1]['includeMessageCounts'], ['1'])
        self.assertEqual(self.cli('chatlab-messages', '--session-id', 'name/with space', '--since', '1790812800')[0], 0)
        self.assertIn('name%2Fwith%20space', self.server.requests[-1][0])
        self.assertEqual(self.server.requests[-1][1]['since'], ['1790812800'])
        self.assertEqual(self.cli('sns-timeline')[0], 0)
        self.assertEqual(self.server.requests[-1][1]['media'], ['0'])

    def test_token_file_and_invalid_multiline_token(self):
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / 'token'
            token_file.write_text(self.server.test_token + '\n')
            self.assertEqual(self.cli('sessions', token=False, extra_env={'WEFLOW_API_TOKEN_FILE': str(token_file)})[0], 0)
            count = len(self.server.requests)
            self.assertEqual(self.cli('sessions', extra_env={'WEFLOW_API_TOKEN': 'first\nsecond'})[0], 1)
            self.assertEqual(len(self.server.requests), count)

    def test_errors_do_not_echo_private_server_payloads(self):
        for mode in ('unauthorized', 'failure', 'bad-json'):
            self.server.mode = mode
            code, out, error = self.cli('sessions')
            self.assertEqual(code, 1)
            self.assertEqual(out, '')
            self.assertNotIn('private', error)
            if mode == 'unauthorized':
                self.assertIn('401', error)

    def test_redirect_is_rejected_without_following_or_forwarding_token(self):
        self.server.mode = 'redirect'
        self.server.redirect_url = self.base + '/unexpected'
        self.assertEqual(self.cli('sessions')[0], 1)
        self.assertEqual(len(self.server.requests), 1)

    def test_sse_multiline_data_event_id_and_event_limit(self):
        code, out, _ = self.cli('sse', '--duration', '1', '--max-events', '1')
        self.assertEqual(code, 0)
        events = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['event'], 'message.new')
        self.assertEqual(events[0]['id'], '7')
        self.assertEqual(events[0]['data']['rawid'], 'example')
        self.assertNotIn('access_token', self.server.requests[0][1])

    def test_idle_sse_stops_at_observation_deadline(self):
        self.server.mode = 'idle'
        started = time.monotonic()
        code, out, _ = self.cli('sse', '--duration', '0.1')
        self.assertEqual(code, 0)
        self.assertEqual(out, '')
        self.assertLess(time.monotonic() - started, 0.5)

    def test_media_download_permissions_and_existing_file_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'image.png'
            self.assertEqual(self.cli('media', 'images/example.png', '--output', str(output))[0], 0)
            self.assertEqual(output.read_bytes(), b'example image bytes')
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            output.write_bytes(b'existing private content')
            self.assertEqual(self.cli('media', 'images/example.png', '--output', str(output))[0], 1)
            self.assertEqual(output.read_bytes(), b'existing private content')

    def test_invalid_base_and_media_path_do_not_make_requests(self):
        for base in ('https://name:password@example.invalid', 'file:///etc/passwd', 'https://example.invalid?access_token=example'):
            self.assertEqual(self.cli('--base', base, 'sessions')[0], 1)
        self.assertEqual(self.cli('media', '../private', '--output', 'unused')[0], 1)
        self.assertEqual(self.server.requests, [])
