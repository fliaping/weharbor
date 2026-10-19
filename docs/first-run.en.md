# First run: from WeChat login to the first message

Applies to WeHarbor 0.1.0 with WeChat 4.1.13.23, Alpha 0.2.0 and Selkies 2.0.
Alpha wizard screens after the first step have not been verified in detail.
Alpha 0.2.0 has a known Linux automatic key acquisition failure; a passing
container smoke test does not verify key acquisition with a real account.

[中文](first-run.md)

1. **Open the desktop** at `https://localhost:3001` with `CUSTOM_USER`/`PASSWORD`
   from `.env`. WeChat and Alpha start automatically (Alpha minimized).
2. **Log in to WeChat** by scanning the QR code (or pressing 登录 for a saved
   account) and confirming on the phone. Automatic login clicking was removed.
3. **Run Alpha's setup wizard**: tick "我已了解", click "连接微信", pick the
   account and data directory `/config/Documents/xwechat_files`, let Alpha
   acquire the database key (WeChat must stay logged in; the container has
   SYS_PTRACE), optionally the image key, then confirm messages are visible.
4. **Enable the HTTP API** in Alpha's settings (port 5031) and copy the token.
   Host port 5031 maps to the in-container nginx proxy on 5032, which forwards
   to Alpha on 127.0.0.1:5031 and rejects browser Origin headers.
   For browser notifications, save the token to
   `/config/.config/weharbor/alpha-api-token` (mode 600).
5. **Connect an AI tool** with the alpha-api skill (see install-skill.md).

Alpha stores its API token with Electron safeStorage; the container runs a
password-less gnome-keyring, so the token is protected by the data volume's
access control. Alpha 0.2.0's key helper embeds an expiry of 2026-11-15.

`NATIVE_WECHAT_CAPTURE_PLATFORM_UNAVAILABLE` is tracked in upstream
xunchahaha/alpha-releases issue #5. On October 19, 2026, the maintainer said
it would be fixed in the next version. Adding SYS_PTRACE or privileged mode
does not fix it. Import an existing key for the same account manually in
Alpha, or wait for a verified upstream fix. Do not put keys in logs or Git.
