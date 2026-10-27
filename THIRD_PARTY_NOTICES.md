# Third-party notices

The MIT license at the repository root covers WeHarbor's integration code.
It does not relicense vendor applications, base-image packages or native libraries.

| Component | Source / origin | License and handling |
| --- | --- | --- |
| LinuxServer.io baseimage-selkies | https://github.com/linuxserver/docker-baseimage-selkies | Pinned `debiantrixie` image digest. GPL-3.0 (LinuxServer.io); bundled Debian packages keep their own notices. |
| Selkies 2.0.0 | https://github.com/selkies-project/selkies | Provided by the base image. Mozilla Public License 2.0. |
| Official Linux WeChat | https://linux.weixin.qq.com/ | Proprietary vendor distribution. The original deb is mirrored in the component-assets Release with its pinned SHA256; it is installed unmodified with dpkg. Verify redistribution terms before publishing a combined image. |
| Alpha 0.2.0 | https://github.com/xunchahaha/alpha-releases | Closed-source, unsigned binary release; the deb control file declares `License: unknown`. Installed unmodified from the pinned SHA256. Redistribution terms are unverified: do not publish a combined image until they are clarified. Bundled Electron/Chromium/ffmpeg notices remain under /opt/Alpha. |

Additional workspace components:

| Component | Source | License and handling |
| --- | --- | --- |
| WeChatDataAnalysis Linux fork | https://github.com/fliaping/WeChatDataAnalysis (upstream LifeArchiveProject/WeChatDataAnalysis) | Upstream has no repository-wide LICENSE file at the pinned revision. Retain its existing notices; WeHarbor MIT does not relicense it. Source and web UI are included at /opt/weharbor/analysis. |
| wcdb-key-tool | https://github.com/TANGandXUE/wcdb-key-tool | MIT; unchanged capture tool, LICENSE and attribution included in the analysis fork. |
| DeepSeek Harness | https://github.com/deepseek-ai/deepseek-harness | MIT; official npm distributions and dependencies retain their package licenses under /opt/weharbor/harness/node_modules. |
| Magpie | https://github.com/yetone/magpie | MIT; pinned official Linux CLI/web gateway binary at /opt/weharbor/magpie/magpie. |
| Tailscale | https://github.com/tailscale/tailscale | BSD-3-Clause; official archive retains its LICENSE under /opt/weharbor/network. |
| cloudflared | https://github.com/cloudflare/cloudflared | Apache-2.0; pinned official binary. |
| Node.js | https://nodejs.org/ | MIT and bundled third-party notices; official distribution retains LICENSE under /opt/weharbor/node. |

Qibox informed the Action design; no Qibox code, application files, memory
offsets, or captured user data are included in this repository.

WeHarbor does not modify the WeChat or Alpha vendor packages. Image notices are
installed at /usr/share/doc/weharbor; original application notices remain in
their vendor locations.

WeHarbor is an independent community integration. Its name does not imply
endorsement by Tencent, the Alpha authors, LinuxServer.io or the Selkies maintainers.
