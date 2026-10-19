# Harness runtime

The official 0.1.1-rc.2 release loads plugins through peer services. This
manifest explicitly includes that release's peer-service closure, including
the compatible Cordis runtime, so `--legacy-peer-deps` does not silently omit
runtime imports or mix later Cordis APIs into this prerelease. package-lock.json
pins every resolved archive and integrity. Update the manifest and lock together
and boot the web profile with the WeHarbor MCP patch before accepting an update.

Use the Node/npm versions pinned in versions.lock.json. Install with
`npm ci --legacy-peer-deps`. The launcher supplies `--expose-internals` for the
release's HMR loader. No vendor source files are modified.
