#!/usr/bin/env python3
"""Dependency-free CLI for a configured WeFlow HTTP API."""
from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


class APIError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def time_filter(value):
    if len(value) == 8 and value.isdigit():
        try:
            datetime.strptime(value, '%Y%m%d')
            return value
        except ValueError:
            pass
    elif len(value) in (10, 13) and value.isdigit():
        return str(int(value) * 1000) if len(value) == 10 else value
    raise argparse.ArgumentTypeError('Use a valid YYYYMMDD date or 10/13-digit Unix timestamp')


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('Must be a finite positive number')
    return value


def bounded_int(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f'Must be between {low} and {high}')
        return number
    return parse


class Client:
    def __init__(self, base, token=None, timeout=30):
        parsed = urllib.parse.urlsplit(base)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise APIError('API base must be an HTTP(S) URL without credentials, query or fragment')
        self.base = base.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.opener = urllib.request.build_opener(NoRedirect())

    def open(self, path, params=None, *, auth=True, stream=False, last_event_id=None, timeout=None):
        if auth and not self.token:
            raise APIError('Set WEFLOW_API_TOKEN or WEFLOW_API_TOKEN_FILE locally')
        url = self.base + path
        query = {key: value for key, value in (params or {}).items() if value is not None}
        if query:
            url += '?' + urllib.parse.urlencode(query)
        headers = {'Accept': 'text/event-stream' if stream else 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.token
        if last_event_id:
            headers['Last-Event-ID'] = last_event_id
        request = urllib.request.Request(url, headers=headers, method='GET')
        try:
            return self.opener.open(request, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as error:
            error.close()
            advice = {401: 'Check the API token locally', 403: 'Check API access permissions',
                      404: 'Check the API base and whether this WeFlow version supports the endpoint'}
            raise APIError(f'HTTP {error.code}. ' + advice.get(error.code, 'API request failed; inspect WeFlow locally')) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise APIError('Cannot connect to the configured API; check address, service and network') from None

    def get(self, path, params=None, *, auth=True):
        with self.open(path, params, auth=auth) as response:
            try:
                result = json.load(response)
            except (ValueError, UnicodeError):
                raise APIError('API returned invalid JSON') from None
        if isinstance(result, dict) and result.get('success') is False:
            raise APIError('API reported failure; inspect account/database configuration in WeFlow')
        return result


def read_token():
    token = os.environ.get('WEFLOW_API_TOKEN', '').strip()
    if not token and os.environ.get('WEFLOW_API_TOKEN_FILE'):
        try:
            token = Path(os.environ['WEFLOW_API_TOKEN_FILE']).read_text().strip()
        except (OSError, UnicodeError):
            raise APIError('Cannot read WEFLOW_API_TOKEN_FILE') from None
    if '\r' in token or '\n' in token:
        raise APIError('API token must be a single line')
    return token


def sse_events(response, duration, max_events):
    deadline = time.monotonic() + duration
    event, event_id, data = 'message', None, []
    count = 0
    while time.monotonic() < deadline and count < max_events:
        # urllib exposes its HTTP connection socket here. Limit each blocking
        # read to the remaining observation window, including on an idle stream.
        connection = getattr(getattr(response.fp, 'raw', None), '_sock', None)
        if connection is not None:
            connection.settimeout(max(0.001, deadline - time.monotonic()))
        try:
            raw = response.readline(65537)
        except (TimeoutError, socket.timeout):
            return
        if not raw:
            return
        if len(raw) > 65536:
            raise APIError('SSE line exceeds 64 KiB')
        line = raw.decode('utf-8-sig', errors='replace').rstrip('\r\n')
        if not line:
            if data:
                text = '\n'.join(data)
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = text
                yield {'event': event, 'id': event_id, 'data': payload}
                count += 1
            event, data = 'message', []
        elif not line.startswith(':'):
            field, _, value = line.partition(':')
            value = value.removeprefix(' ')
            if field == 'event':
                event = value
            elif field == 'id' and '\x00' not in value:
                event_id = value
            elif field == 'data':
                data.append(value)
                if sum(len(part) for part in data) > 1024 * 1024:
                    raise APIError('SSE event exceeds 1 MiB')


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument('--base', default=os.environ.get('WEFLOW_API_BASE', 'http://127.0.0.1:5031'))
    root.add_argument('--timeout', type=positive, default=30)
    sub = root.add_subparsers(dest='command', required=True)
    sub.add_parser('health')
    for name in ('sessions', 'contacts', 'chatlab-sessions'):
        item = sub.add_parser(name)
        item.add_argument('--keyword')
        item.add_argument('--limit', type=bounded_int(1, 10000), default=100)
    for name in ('messages', 'sns-timeline'):
        item = sub.add_parser(name)
        if name == 'messages':
            item.add_argument('--talker', required=True)
            item.add_argument('--media', action='store_true')
        else:
            item.add_argument('--usernames', help='Comma-separated usernames')
        item.add_argument('--keyword')
        item.add_argument('--start', type=time_filter)
        item.add_argument('--end', type=time_filter)
        item.add_argument('--limit', type=bounded_int(1, 10000 if name == 'messages' else 200), default=100 if name == 'messages' else 20)
        item.add_argument('--offset', type=bounded_int(0, 2**53 - 1), default=0)
    members = sub.add_parser('group-members')
    members.add_argument('--chatroom-id', required=True)
    members.add_argument('--counts', action='store_true')
    pull = sub.add_parser('chatlab-messages')
    pull.add_argument('--session-id', required=True)
    pull.add_argument('--since', type=bounded_int(0, 10**10))
    pull.add_argument('--end', type=bounded_int(0, 10**10))
    pull.add_argument('--limit', type=bounded_int(1, 5000), default=100)
    pull.add_argument('--offset', type=bounded_int(0, 2**53 - 1), default=0)
    sub.add_parser('sns-usernames')
    stats = sub.add_parser('sns-export-stats')
    stats.add_argument('--fast', action='store_true')
    media = sub.add_parser('media')
    media.add_argument('relative_path')
    media.add_argument('--output', required=True)
    stream = sub.add_parser('sse')
    stream.add_argument('--duration', type=positive, default=30)
    stream.add_argument('--max-events', type=bounded_int(1, 10000), default=20)
    stream.add_argument('--last-event-id')
    return root


def run(args):
    client = Client(args.base, None if args.command == 'health' else read_token(), args.timeout)
    command = args.command
    params = {key: value for key, value in vars(args).items()
              if key in ('keyword', 'limit', 'offset', 'start', 'end', 'talker', 'usernames', 'since')}
    endpoints = {'sessions': '/sessions', 'contacts': '/contacts', 'messages': '/messages',
                 'chatlab-sessions': '/sessions', 'group-members': '/group-members',
                 'sns-timeline': '/sns/timeline', 'sns-usernames': '/sns/usernames',
                 'sns-export-stats': '/sns/export/stats'}
    if command == 'health':
        result = client.get('/health', auth=False)
        if not isinstance(result, dict) or result.get('status') != 'ok':
            raise APIError('WeFlow health is not ok')
    elif command == 'sse':
        try:
            with client.open('/api/v1/push/messages', stream=True,
                             last_event_id=args.last_event_id, timeout=args.duration) as response:
                if 'text/event-stream' not in response.headers.get('Content-Type', ''):
                    raise APIError('API did not return an SSE stream')
                for event in sse_events(response, args.duration, args.max_events):
                    print(json.dumps(event, ensure_ascii=False), flush=True)
        except (TimeoutError, socket.timeout):
            pass
        return
    elif command == 'media':
        path = args.relative_path
        if not path or path.startswith('/') or any(part in ('.', '..') for part in path.split('/')):
            raise APIError('Use a relative media path without dot segments')
        with client.open('/api/v1/media/' + urllib.parse.quote(path, safe='/')) as response:
            try:
                with open(args.output, 'xb') as output:
                    os.chmod(args.output, 0o600)
                    try:
                        while chunk := response.read(65536):
                            output.write(chunk)
                    except Exception:
                        Path(args.output).unlink(missing_ok=True)
                        raise
            except FileExistsError:
                raise APIError('Output already exists; choose another file') from None
        result = {'success': True, 'output': args.output}
    else:
        path = endpoints.get(command)
        if command == 'chatlab-messages':
            path = '/sessions/' + urllib.parse.quote(args.session_id, safe='') + '/messages'
        elif command == 'chatlab-sessions':
            params['format'] = 'chatlab'
        elif command == 'group-members':
            params.update(chatroomId=args.chatroom_id, includeMessageCounts='1' if args.counts else '0')
        elif command == 'messages':
            params['media'] = '1' if args.media else '0'
        elif command == 'sns-timeline':
            params.update(media='0', inline='0')
        elif command == 'sns-export-stats':
            params['fast'] = '1' if args.fast else '0'
        result = client.get('/api/v1' + path, params)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    args = parser().parse_args()
    try:
        run(args)
    except (APIError, OSError, ValueError, UnicodeError):
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, APIError) else 'Request or local file operation failed'
        print(json.dumps({'success': False, 'error': message}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
