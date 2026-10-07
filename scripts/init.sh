#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python3 - <<'PY'
import os, secrets
from pathlib import Path
target = Path('.env')
if target.exists():
    print('.env already exists; preserved existing settings')
else:
    text = Path('.env.example').read_text()
    text = text.replace('PASSWORD=\n', 'PASSWORD=' + secrets.token_urlsafe(24) + '\n')
    text = text.replace('PUID=1000\n', f'PUID={os.getuid()}\n')
    text = text.replace('PGID=1000\n', f'PGID={os.getgid()}\n')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    print('Created .env with a random browser login password (mode 600)')
    print('Browser username: weharbor; read PASSWORD in .env locally')
PY
