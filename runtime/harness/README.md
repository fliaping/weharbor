# Harness runtime

The official npm `latest` release is pinned to 0.2.1-rc.2 (verified October 20,
2026). Its declared dependencies and npm-resolved peers are pinned, with archive
integrities, in package-lock.json. Update the manifest, lock and versions.lock.json
together and boot the web profile with the WeHarbor MCP patch before accepting
an update. This is an upstream release candidate.

Use the Node/npm versions pinned in versions.lock.json. Install with
`npm ci --omit=dev`. The launcher supplies `--expose-internals` for the
release's HMR loader and selects `--profile web` explicitly before global
`--patch` overlays and web arguments.
No vendor source files are modified.

The loopback proxy captures the process launch URL without logging its token.
A trusted initial page navigation exchanges it for the upstream signed HttpOnly
browser cookie, scoped to `/assistant/`. APIs and WebSockets still require that
cookie; cross-origin requests are rejected before origin translation. The outer
WeHarbor gateway remains the access boundary. Model credentials are configured
later in the official web UI.
