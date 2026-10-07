#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
./scripts/init.sh
target_image="$(docker compose config --images)"
if [[ "$target_image" == weharbor:* ]]; then
    if ! docker image inspect "$target_image" >/dev/null 2>&1; then
        ./scripts/build.sh --tag "$target_image" --load
    fi
else
    docker compose pull
fi
docker compose up -d
printf '%s\n' 'WeHarbor started. Open the HTTPS port configured in .env (default https://localhost:3001).'
printf '%s\n' 'Browser username and password are stored in .env.'
