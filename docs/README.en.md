# WeHarbor

A self-hosted WeChat desktop, local data API and message notifications in one
container. WeHarbor builds directly on the LinuxServer.io Selkies 2.0 base image
(Debian trixie) and installs the official Linux WeChat and Alpha, unmodified.

Version 0.1.0 includes WeChat 4.1.13.23, Alpha 0.2.0, Magpie 0.1.1734, DeepSeek Harness 0.2.1-rc.2 and Selkies 2.0.0
(`ghcr.io/linuxserver/baseimage-selkies:debiantrixie`, pinned by digest), on
linux/amd64 only. Source: [fliaping/weharbor](https://github.com/fliaping/weharbor).

> The Alpha-based build has no published prebuilt image yet; build locally.
> Alpha is a closed-source, unsigned binary with no declared license, and its
> key helper embeds an expiry (2026-11-15) that requires upstream updates.

## Build and start

Requirements: Docker Engine with Compose v2 / Buildx, Python 3.10+, amd64 host.

~~~bash
git clone https://github.com/fliaping/weharbor.git
cd weharbor
./scripts/init.sh
./scripts/build.sh
docker compose up -d
~~~

The pinned WeChat deb (component-assets Release) and Alpha deb
(xunchahaha/alpha-releases v0.2.0) are downloaded and SHA256-verified.
WECHAT_DOWNLOAD_URL / ALPHA_DOWNLOAD_URL can override the addresses.

Open https://localhost:3001 with CUSTOM_USER / PASSWORD from .env, then follow
the [first-run guide](first-run.en.md): log in to WeChat, complete Alpha's setup
wizard, and enable Alpha's HTTP API (port 5031).

Alpha listens on 127.0.0.1:5031 inside the container and rejects foreign Host
and Origin headers. An in-container nginx proxy on 5032 forwards to it, and
Compose publishes that on host `${API_BIND_ADDRESS}:${API_PORT}` (default
127.0.0.1:5031). Alpha's bearer token is still required for every route except
/health. For browser notifications, save the token to
/config/.config/weharbor/alpha-api-token.

Alpha starts minimized and WeChat receives focus; only the WeChat main window
is maximized once after login. PWA installation is supported over trusted HTTPS
(see [pwa.md](pwa.md)). All state persists in ./data mounted at /config.

Compared with earlier WeHarbor releases, WeChat auto-login clicking
and nightly restarts were removed, and no Chinese IME is preinstalled.
Existing profiles are migrated automatically (see [operations](operations.md)).

[First-run guide](first-run.en.md) · [API usage](api.md) · [Operations](operations.md) ·
[AI skill installation](install-skill.md) · [Third-party notices](../THIRD_PARTY_NOTICES.md)

Install the bundled alpha-api Agent Skill from your AI project directory:

~~~bash
npx --yes skills add https://github.com/fliaping/weharbor --skill alpha-api --yes
~~~

Configure ALPHA_API_BASE and ALPHA_API_TOKEN (or ALPHA_API_TOKEN_FILE) locally.
Routes come from static analysis of Alpha 0.2.0; parameters and response
fields are not yet verified against a live instance.

WeHarbor integration code is MIT licensed. Vendor components keep their own
licenses; Alpha's redistribution terms are unclear, so do not publish a combined
image until they are confirmed.
