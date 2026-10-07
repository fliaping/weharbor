#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python3 scripts/prepare-assets.py
project_version="$(python3 -c 'import json; print(json.load(open("versions.lock.json"))["project_version"])')"
base_image="$(python3 -c 'import json; print(json.load(open("versions.lock.json"))["base_image"])')"
project_revision="$(git rev-parse HEAD 2>/dev/null || true)"
args=(--platform linux/amd64 --build-arg "BASE_IMAGE=$base_image"
      --build-arg "PROJECT_VERSION=$project_version" --build-arg "PROJECT_REVISION=$project_revision")
if [[ -n "${PROJECT_SOURCE:-}" ]]; then args+=(--build-arg "PROJECT_SOURCE=$PROJECT_SOURCE"); fi
if [[ -n "${APT_MIRROR:-}" ]]; then args+=(--build-arg "APT_MIRROR=$APT_MIRROR"); fi
if [[ $# -eq 0 ]]; then
    args+=(--tag "weharbor:$project_version" --load)
else
    args+=("$@")
fi
docker buildx build "${args[@]}" .
