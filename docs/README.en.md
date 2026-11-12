# WeHarbor

Official Linux WeChat, analytics, Magpie gateway and an AI assistant in **one browser workspace**.
Self-hosted WeChat desktop, chat analysis, an AI assistant and notifications in one container. WeHarbor builds directly on the LinuxServer.io Selkies 2.0 base image
(Debian trixie) and installs the official Linux WeChat, unmodified.

Version 0.1.0 includes WeChat 4.1.13.23, WeChatDataAnalysis (fork), Magpie 0.1.1734, DeepSeek Harness 0.2.1-rc.2 and Selkies 2.0.0
(`ghcr.io/linuxserver/baseimage-selkies:debiantrixie`, pinned by digest), on
linux/amd64 only. Source: [fliaping/weharbor](https://github.com/fliaping/weharbor).

## Build and start

Requirements: Docker Engine with Compose v2 / Buildx, Python 3.10+, amd64 host.

~~~bash
git clone https://github.com/fliaping/weharbor.git
cd weharbor
./scripts/init.sh
./scripts/build.sh
docker compose up -d
~~~

The pinned WeChat deb (component-assets Release) and other components are
downloaded and SHA256-verified. WECHAT_DOWNLOAD_URL can override the address.

Open https://localhost:3001 with CUSTOM_USER / PASSWORD from .env, then follow
the [first-run guide](first-run.en.md): log in to WeChat, get the database key in
Analysis, add a model provider in Magpie, and ask the assistant.

WeChat receives focus and only its main window is maximized once after login.
PWA installation is supported over trusted HTTPS (see [pwa.md](pwa.md)).
All state persists in ./data mounted at /config.

Compared with earlier WeHarbor releases, WeChat auto-login clicking, nightly
restarts and the Alpha desktop app were removed, and no Chinese IME is
preinstalled. Existing profiles are migrated automatically (see [operations](operations.md)).

[First-run guide](first-run.en.md) · [Workspace and MCP](workspace.md) · [Operations](operations.md) ·
[Third-party notices](../THIRD_PARTY_NOTICES.md)

AI tools that speak MCP can connect to `https://<host>/workspace/mcp` with the
bearer token in `/config/.config/weharbor/workspace.token`; the portable skill is
served at `/workspace/skill/SKILL.md`.

WeHarbor integration code is MIT licensed. Vendor components keep their own
licenses; see the third-party notices.

## Remote access

Optional, off by default: Tailscale (userspace networking, Headscale/DERP friendly),
Cloudflare Tunnel and frp. Configure them in Connections (Alt+5) → 远程访问 or with
`TAILSCALE_*`, `CLOUDFLARE_TUNNEL_*` and `FRP_*` environment variables (env wins).
Use a strong `PASSWORD` before exposing WeHarbor publicly; add Cloudflare Access, and use
frp token auth with TLS. Details (Chinese): [remote-access.md](remote-access.md).
