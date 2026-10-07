# First run: from WeChat login to your first readable message

This guide targets WeHarbor 0.1.0 with Linux WeChat 4.1.13.23 and WeFlow 6.3.2.
Other versions may have different labels or key acquisition steps.
Complete [build and startup](README.en.md#build-and-start) before continuing.

WeFlow reads your local account's chat database using its database key.
WeChat login, database access and API authentication are separate steps.
Installing the Agent Skill does not configure the account or acquire its key.

| Stage | Evidence of success |
| --- | --- |
| Desktop | Both application windows are available in the browser |
| WeChat login | Conversations appear and local account data exists |
| Database key | WeFlow reports success and selects the matching account |
| Database connection | A conversation opens in WeFlow with readable messages |
| API | Health works, then authenticated sessions and messages work |
| AI | The AI's execution environment reaches the API and reads a few messages |

## Open the desktop and log in once

Open `https://localhost:3001` on the Docker host and log in using `CUSTOM_USER`
and `PASSWORD` from your local `.env`. Use your configured HTTPS port if different.
The initial certificate is self-signed. For a remote host, an SSH tunnel keeps
the default loopback binding usable:

~~~bash
ssh -N -L 3001:127.0.0.1:3001 user@your-docker-host
~~~

Open the same URL on the computer running that tunnel. Use the floating app
switcher to select WeChat. Scan its QR code with your phone, confirm login,
and wait for conversations and recent messages to appear. Open a conversation
to confirm text is available. This first login creates the local account data.

WeFlow reads what this Linux instance has stored locally. It does not
automatically obtain the phone's complete history. Compare missing history
with what the Linux WeChat client itself can display.

## Select the database directory

WeFlow's first-run wizard has Welcome, Database Directory, Cache Directory,
Decryption Key, Image Key and Security steps. The current UI labels are
“欢迎”, “数据库目录”, “缓存目录”, “解密密钥”, “图片密钥” and “安全防护”.

Choose “自动检测” in the database step. The usual root is
`/config/Documents/xwechat_files`, a compatibility link to
`/config/xwechat_files`. If detection fails, browse to the actual root and
compare it with WeChat's storage location. Use container paths, not the
host's `./data` path. An account subdirectory must contain `db_storage`.

Leave the cache directory empty for the default. Custom caches should also
be under `/config` so they survive container replacement.

## Acquire the database key, then confirm login

**On Linux, expect another login. Wait for WeFlow to prepare before confirming it.**
Version 6.3.2 stops and relaunches WeChat, then uses its bundled helper to
capture the database key during login.

1. Disable WeChat's automatic login and log out, leaving it at the login screen.
   If your `.env` has `ENABLE_WECHAT_AUTO_LOGIN=true`, temporarily set it to
   `false` and run `docker compose up -d` before acquisition. The startup
   script and WeChat's own automatic login option are separate controls.
2. In “解密密钥”, select “自动获取密钥” and confirm its instructions.
   WeChat closing and reopening is part of this version's preparation.
3. Wait for WeFlow to indicate it is ready for login, or waiting for the key
   after authorization. Complete an authorization dialog if one appears.
   WeHarbor includes `SYS_PTRACE`, polkit and container authorization rules.
4. Switch to WeChat, scan or select login, and confirm on your phone.
5. Wait for “密钥获取成功”. Verify that the key field is populated and the
   selected account matches the one you just logged in to.

If WeFlow cannot launch WeChat, open it from the desktop and use
“我已看到登录窗口，继续”. Still wait for preparation before confirming login.
If it times out or you logged in too early, log out and repeat this sequence.
Keep the database key in WeFlow's local configuration; it is not an API token
and does not need to be sent to an AI or committed to GitHub.

## Finish configuration and verify messages

Image XOR / AES keys decode images and are separate from the database key.
The image step tries to calculate them from local caches. If no suitable
images are cached, open a few images in WeChat, wait for downloads, and use
“重新计算”. “内存扫描” is another option while WeChat is running.

The first-run wizard can continue without image keys. Verify text first and
configure image keys later if needed. The optional application lock has its
own password, separate from the desktop password and API token.

Select “完成配置”. WeFlow tests and opens the database. Open a conversation
and compare a few text messages with WeChat. You can also use
Settings → “数据库连接” → “测试连接”. Container health alone does not verify this.

## Enable and test the API

In Settings → “API 服务”, turn off a running HTTP API before editing its
address or port. Set the address to `0.0.0.0`, set the port to your `.env`
`WEFLOW_API_PORT` (default `5031`), generate an Access Token with
“随机生成”, and enable the HTTP API. Its status should be “运行中”.

Listening on all container interfaces allows Docker forwarding. The default
Compose configuration still publishes the API only to the host loopback.
Changing `.env` does not update WeFlow's persisted API settings. Enable
“主动推送” only when you need notifications or SSE, and check its session filters.

Use the [API examples](api.md) to check health, query a few authenticated
sessions, then pass a returned session's `username` as the messages `talker`.
The sessions and messages responses should have `success: true` and contain
the data you verified in WeFlow. `/health` only checks that the server is alive.

## Connect the AI skill

Follow the [skill installation page](install-skill.md). Configure
`WEFLOW_API_BASE` and `WEFLOW_API_TOKEN`, or `WEFLOW_API_TOKEN_FILE`, in
the AI's execution environment. Its `localhost` is not necessarily your
Docker host. Another container on the same Docker network can use
`http://weharbor:5031`; remote tools need an appropriate network or tunnel.

Ask the AI to check health, list a few sessions, and read a few messages
from a conversation you select. Configure summaries or SSE after this works.
Do not paste the database key or actual API token into the AI conversation.

## Troubleshooting

| Symptom | Check first |
| --- | --- |
| Healthy container but no messages | Wizard completion, account selection and database connection |
| No account / missing `db_storage` | Initial WeChat login and the container's database root path |
| Key acquisition times out | Automatic or premature login; log out and repeat the preparation sequence |
| Authorization / Hook fails | Compose retains `SYS_PTRACE`; polkit is running; inspect a redacted error |
| Connection fails with a key | Directory, key and selected account belong together |
| Text works but images fail | Downloaded local media and separate image keys |
| Missing history | Whether Linux WeChat itself has those messages |
| API connection refused | API running, `0.0.0.0` inside the container, matching port settings |
| API returns 401 | Correct API token rather than desktop password or database key |
| No SSE events | Push enabled, matching filters, WeChat online and actual new messages |
| Skill installed but cannot read | AI network access and credentials in the execution environment |

Retain the same `/config` volume after restarting. Valid account settings and
keys persist, although WeChat may ask you to confirm login again. Reacquire a
key when needed for an account change or invalid key, not on every restart.
Back up the complete profile before upgrades; see [operations](operations.md).
When filing an issue, share versions, the failing stage and a redacted error,
not complete logs, databases, account configuration or screenshots of keys.
