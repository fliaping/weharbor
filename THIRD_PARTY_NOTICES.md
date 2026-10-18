# Third-party notices

The MIT license at the repository root covers WeHarbor's integration code.
It does not relicense vendor applications, base-image packages or native libraries.

| Component | Source / origin | License and handling |
| --- | --- | --- |
| LinuxServer.io baseimage-selkies | https://github.com/linuxserver/docker-baseimage-selkies | Pinned `debiantrixie` image digest. GPL-3.0 (LinuxServer.io); bundled Debian packages keep their own notices. |
| Selkies 2.0.0 | https://github.com/selkies-project/selkies | Provided by the base image. Mozilla Public License 2.0. |
| Official Linux WeChat | https://linux.weixin.qq.com/ | Proprietary vendor distribution. The original deb is mirrored in the component-assets Release with its pinned SHA256; it is installed unmodified with dpkg. Verify redistribution terms before publishing a combined image. |
| Alpha 0.2.0 | https://github.com/xunchahaha/alpha-releases | Closed-source, unsigned binary release; the deb control file declares `License: unknown`. Installed unmodified from the pinned SHA256. Redistribution terms are unverified: do not publish a combined image until they are clarified. Bundled Electron/Chromium/ffmpeg notices remain under /opt/Alpha. |

WeHarbor does not unpack, patch or rebuild vendor packages. Image notices are
installed at /usr/share/doc/weharbor; original application notices remain in
their vendor locations.

WeHarbor is an independent community integration. Its name does not imply
endorsement by Tencent, the Alpha authors, LinuxServer.io or the Selkies maintainers.
