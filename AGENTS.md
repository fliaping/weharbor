# WeHarbor contributor notes

- Keep upstream WeChat application files unmodified (install the pinned deb
  with dpkg/apt; never patch /opt/wechat). Alpha is no longer part of WeHarbor;
  do not reintroduce it or depend on it.
- Build on the pinned plain LinuxServer.io Selkies base (debiantrixie digest
  in versions.lock.json). Keep only our integration files under root/.
- versions.lock.json is the source of component versions and checksums.
- Only linux/amd64 is supported (WeChat is a pinned amd64 deb).
- All runtime state belongs under /config; never check data/, .env,
  package archives, credentials, or user databases into Git.
- Preserve browser authentication and the workspace bearer-token auth for
  /workspace/mcp and /workspace/data; reject foreign browser Origin headers.
- Changes to initialization must preserve existing profiles and user settings
  (see init-weharbor-profile for the legacy profile migration).
- Run python3 scripts/check.py; for image changes, build and run
  scripts/smoke-test.sh IMAGE with an empty, temporary profile.
- Keep the public skill in skills/weharbor-api self-contained and portable.
  Credentials come from the user's environment or local token file.
- MIT covers this repository's integration code. Vendor components retain
  their own licenses; see THIRD_PARTY_NOTICES.md.
