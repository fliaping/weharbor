# WeHarbor contributor notes

- Keep upstream WeChat and WeFlow application files unmodified.
- Reuse the pinned wechat-selkies minimal image; keep only our integration
  files under root/. Avoid copying the complete upstream repository.
- versions.lock.json is the source of component versions and checksums.
- Only linux/amd64 is supported by the current WeFlow archive.
- All runtime state belongs under /config; never check data/, .env,
  package archives, credentials, or user databases into Git.
- Preserve browser authentication and the WeFlow API's own token authentication.
- Changes to initialization must preserve existing profiles and user settings.
- Run python3 scripts/check.py; for image changes, build and run
  scripts/smoke-test.sh IMAGE with an empty, temporary profile.
- Keep the public WeFlow skill in skills/weflow-api self-contained and portable.
  Credentials come from the user's environment or local token file. Verify
  client behavior and installation when changing the skill or its scripts.
- MIT covers this repository's integration code. Vendor components retain
  their own licenses; see THIRD_PARTY_NOTICES.md.
