#!/usr/bin/with-contenv bash
set -e
export HOME=/config
export PYTHONPATH=/scripts/workspace
exec s6-setuidgid abc /opt/weharbor/python/bin/python -m uvicorn \
    server:app --host 127.0.0.1 --port 8766
