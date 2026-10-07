# WeHarbor

A self-hosted WeChat desktop, local data API and message notifications in one
container. WeHarbor combines the pinned minimal wechat-selkies image, official
Linux WeChat and an unmodified WeFlow distribution.

Version 0.1.0 currently includes WeChat 4.1.13.23 and WeFlow 6.3.2, on linux/amd64.
Source: [fliaping/weharbor](https://github.com/fliaping/weharbor).
The prebuilt image has not been published yet.

## Build and start

Requirements: Docker Engine with Compose v2 / Buildx, Python 3.10+ and an amd64 host.
Provide the original WeFlow 6.3.2 archive; its historical public download URL has
not yet been confirmed. Alternatively set WEFLOW_DOWNLOAD_URL to a trusted HTTPS
asset URL. Every package must match the pinned SHA256.

~~~bash
git clone https://github.com/fliaping/weharbor.git
cd weharbor
mkdir -p downloads
cp /path/to/WeFlow-6.3.2-Setup.tar.gz downloads/weflow.tar.gz
./scripts/init.sh
./scripts/build.sh
docker compose up -d
~~~

Open https://localhost:3001 with the browser credentials stored in .env.
init.sh generates a random password and detects your UID/GID without overwriting
existing settings. The default bind address is localhost. Set BIND_ADDRESS=0.0.0.0
to permit access from other machines while retaining browser authentication.

Log in to WeChat using your phone, then configure your account and database key
inside WeFlow. The usual database path is /config/Documents/xwechat_files.
Enable WeFlow's HTTP API on 0.0.0.0:5031, generate an API token, and enable its
message push feature. Browser notifications require HTTPS or localhost and an
open desktop page. API ports are published to host loopback by default.

All profiles, databases and settings persist in ./data, mounted at /config.
Keep this directory and .env out of Git. Stop the container before backing it up.

[API usage](api.md) · [Operations](operations.md) ·
[AI skill installation](install-skill.md) ·
[Third-party notices](../THIRD_PARTY_NOTICES.md)

Install the bundled weflow-api Agent Skill from your AI project directory:

~~~bash
npx --yes skills add https://github.com/fliaping/weharbor --skill weflow-api --yes
~~~

Give your AI this installation URL:
https://raw.githubusercontent.com/fliaping/weharbor/main/docs/install-skill.md
The client needs Python 3.10+, a reachable WEFLOW_API_BASE and a locally configured
WEFLOW_API_TOKEN (or WEFLOW_API_TOKEN_FILE). No pip dependencies are required.
Installation does not configure or disclose account credentials.

WeHarbor integration code is MIT licensed. Vendor components keep their own
licenses. WeFlow's published source license includes a noncommercial condition;
the exact 6.3.2 binary and native component redistribution terms must still be
confirmed before publishing a combined image. The repository's MIT license does
not apply to every component inside the image.
