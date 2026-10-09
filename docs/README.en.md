# WeHarbor

A self-hosted WeChat desktop, local data API and message notifications in one
container. WeHarbor combines the pinned minimal wechat-selkies image, official
Linux WeChat and an unmodified WeFlow distribution.

Version 0.1.0 currently includes WeChat 4.1.13.23 and WeFlow 6.3.2, on linux/amd64.
Source: [fliaping/weharbor](https://github.com/fliaping/weharbor).
The prebuilt image has not been published yet.

## Build and start

Requirements: Docker Engine with Compose v2 / Buildx, Python 3.10+ and an amd64 host.
The pinned WeFlow 6.3.2 archive and WeChat deb are downloaded automatically from
this repository's component-assets Release. Every package must match the pinned
SHA256. The Release contains only original installers and their checksums, with
no user profiles or credentials. WEFLOW_DOWNLOAD_URL / WECHAT_DOWNLOAD_URL can
override the download addresses while retaining checksum verification.

~~~bash
git clone https://github.com/fliaping/weharbor.git
cd weharbor
./scripts/init.sh
./scripts/build.sh
docker compose up -d
~~~

Open https://localhost:3001 with the browser credentials stored in .env.

WeFlow initially opens minimized and WeChat receives focus. After login, only
the identified WeChat main window is maximized once. Later child windows keep
their own size; manually restoring the main window is respected. Set
ENABLE_WINDOW_DEFAULTS=false to disable the helper.

PWA installation is supported: open the desktop over HTTPS with a trusted
certificate and click “安装 WeHarbor” when Chrome/Edge offers installation.
On iPhone/iPad, use Safari's Share → Add to Home Screen. Plain HTTP on a LAN IP
and untrusted certificates may prevent installation. Installed apps still need
the server and network; chat data and desktop frames are never cached by the
Service Worker. See [installation details](pwa.md).
init.sh generates a random password and detects your UID/GID without overwriting
existing settings. The default bind address is localhost. Set BIND_ADDRESS=0.0.0.0
to permit access from other machines while retaining browser authentication.

Follow the [first-run guide](first-run.en.md) after opening the desktop.
First log in to create local data, then configure the database in WeFlow.
Linux key acquisition restarts WeChat: disable automatic login, log out,
start acquisition, and confirm login only after WeFlow is ready.
The usual database path is /config/Documents/xwechat_files.
Verify readable messages in WeFlow before enabling the API or installing a skill.
Enable WeFlow's HTTP API on 0.0.0.0:5031, generate an API token, and enable its
message push feature. Browser notifications require HTTPS or localhost and an
open desktop page. API ports are published to host loopback by default.

All profiles, databases and settings persist in ./data, mounted at /config.
Keep this directory and .env out of Git. Stop the container before backing it up.

The image workflow builds and tests main pushes, PRs, version tags and manual
runs. Successful main builds publish GHCR edge / sha tags; matching version tags
publish the version / latest. No additional download variables are required.
PRs never publish, and only the exact image that passed the smoke test is pushed.

[First-run guide](first-run.en.md) · [API usage](api.md) · [Operations](operations.md) ·
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
