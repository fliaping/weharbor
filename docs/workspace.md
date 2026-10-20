# Integrated workspace

The edge handle switches fullscreen views without disconnecting the Selkies
desktop: Desktop, WeChatDataAnalysis (`/analysis/`), DeepSeek Harness
(`/assistant/`), and Connections (`/workspace/`). Each iframe remains loaded
when switching away. Existing browser authentication covers these pages.

## Local Linux data

The pinned fork is `fliaping/WeChatDataAnalysis`; the source revision and archive
checksum are in `versions.lock.json`. The Linux adapter first uses existing
account-specific WeFlow keys, verifies decrypted SQLite/WAL snapshots, and
verifies image AES/XOR keys against actual V2 images. Original encrypted files
are never overwritten. Refresh runs every 30 seconds and can be triggered in
the UI or through MCP. Decrypted copies and verified keys remain under
`/config/.local/share/weharbor/analysis`, with private permissions.
Linux chat auto-update uses snapshot revision events over SSE: after a validated
sync, the page refreshes sessions and the selected conversation. Reconnecting
also refreshes the page data. This is periodic synchronization (roughly 30 seconds
plus decryption time), not a native WCDB connection; imported archives remain
static. Unchanged sync attempts do not trigger repeated chat refreshes.

If no usable key exists, the Linux source card offers an explicit wcdb-key-tool
capture job. Start capture, then manually log out/in to WeChat within 120
seconds. The adapter uses the tool's GDB capture only; Python performs database
decryption and validates the captured key before saving it. Image key capture
uses read-only process memory and validates candidates against local images.
The API stays unprivileged. Only the image's fixed root-owned capture helper has
sudo access; it accepts JSON capture requests and no shell arguments. The
container still requires `SYS_PTRACE` for capture. Reusing a verified WeFlow key
does not require attaching to WeChat.

## Network and MCP

Connections accepts an authenticated remote WeHarbor origin and its workspace
Bearer token. Direct domain and Cloudflare origins use HTTP(S); Cloudflare
requires HTTPS. Tailscale uses its userspace outbound HTTP proxy, requiring no
TUN device or NET_ADMIN. Configure the remote service origin, not an individual
API URL. Reachable services are probed; failed reads can fall back to another
configured transport. The local reader is preferred.

Use Tailscale Login to authorize this device in your own tailnet. For public
Cloudflare access, create a named tunnel, route its hostname to
`http://127.0.0.1:3000`, and enter its token in Connections. Keep browser
authentication enabled. Domain access can also use your existing authenticated
HTTPS reverse proxy to port 3000. Connector state and tunnel tokens are under
`/config/.local/share/weharbor/workspace`; remote service configuration is
`/config/.config/weharbor/connections.json`. Secret files use mode 0600. Tokens are never returned
by the settings API. A running cloudflared process alone does not prove DNS or
Cloudflare routing works.

MCP: `https://<your-host>/workspace/mcp` (Streamable HTTP POST, Bearer auth).
Read-only remote data: `/workspace/data/*` with the same Bearer token.
The private token is `/config/.config/weharbor/workspace.token`; provision it
through a local shell/secret manager, never through a public unauthenticated
endpoint. The portable skill is `/workspace/skill/SKILL.md`; its MCP resource
URI is `weharbor://skill`. These transport endpoints do not use browser Basic
auth. Foreign browser Origin headers are rejected.

## AI and Actions

Official `@deepseek-ai/dsh` is pinned through npm's integrity lock. The web
launcher adds the local WeHarbor MCP client, and the assistant workspace contains
the portable skill. Configure your model credentials in Harness's own setup UI;
WeHarbor does not copy Alpha/WeFlow credentials into Harness. Its state is
`/config/.local/share/weharbor/harness`.

Read, search, summarize and suggest replies use message MCP tools. Sending is a
separate prepare/commit action with an exact username, idempotency key, context
revision, desktop checks and persistent receipt. Scheduling uses the same
checks and requires the selected target chat to remain ready at the due time.
Preparation alone never schedules a send: commit activates a future action.
The independent AT-SPI driver does not patch WeChat or copy Qibox code/offsets.
It verifies the open account from process file descriptors and binds the visible
chat using unique DB contact names plus an ID or recent message fingerprints.
Unsupported or ambiguous layouts fail closed. Existing drafts and manual input
are preserved; an interrupted submission is never retried automatically.

A `sent` receipt means the new self-message appeared in the database, not
recipient delivery. Account login, real accessibility layouts, model API access,
Tailscale authorization and Cloudflare routing require deployment validation;
synthetic unit tests cannot prove them. See [the validation report](workspace-validation.md) for the actual
checks performed on this deployment.
