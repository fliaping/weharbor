# WeHarbor contributor notes

- Keep upstream WeChat and Alpha application files unmodified (install the
  pinned debs with dpkg/apt; never patch /opt/wechat or /opt/Alpha).
- Build on the pinned plain LinuxServer.io Selkies base (debiantrixie digest
  in versions.lock.json). Keep only our integration files under root/.
- versions.lock.json is the source of component versions and checksums.
- Only linux/amd64 is supported (Alpha and WeChat are pinned amd64 debs).
- All runtime state belongs under /config; never check data/, .env,
  package archives, credentials, or user databases into Git.
- Preserve browser authentication and Alpha's own bearer-token API auth.
  Alpha binds 127.0.0.1 only; nginx republishes it on ALPHA_API_PROXY_PORT
  (5032) and rejects browser Origin headers.
- Changes to initialization must preserve existing profiles and user settings
  (see init-weharbor-profile for the legacy WeFlow/wechat-selkies migration).
- Run python3 scripts/check.py; for image changes, build and run
  scripts/smoke-test.sh IMAGE with an empty, temporary profile.
- Keep the public skill in skills/alpha-api self-contained and portable.
  Credentials come from the user's environment or local token file.
- MIT covers this repository's integration code. Vendor components retain
  their own licenses; see THIRD_PARTY_NOTICES.md.
