#!/usr/bin/env python3
"""MCP stdio transport for local agents; only stdlib is required."""
import json
import os
import sys
import urllib.request
from pathlib import Path

base = os.environ.get('WEHARBOR_API_BASE', 'http://127.0.0.1:8766').rstrip('/')
token_file = os.environ.get('WEHARBOR_API_TOKEN_FILE', '/config/.config/weharbor/workspace.token')
token = os.environ.get('WEHARBOR_API_TOKEN') or Path(token_file).read_text().strip()
for line in sys.stdin:
    try:
        payload = json.loads(line)
        request = urllib.request.Request(base + '/mcp', data=json.dumps(payload).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json', 'Accept':'application/json, text/event-stream'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=660) as r:
            body = r.read()
        if body:
            print(body.decode(), flush=True)
    except Exception as exc:
        if isinstance(locals().get('payload'), dict) and 'id' in payload:
            print(json.dumps({'jsonrpc':'2.0','id':payload['id'],'error':{'code':-32603,'message':type(exc).__name__}}), flush=True)
