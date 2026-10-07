# Third-party notices

The MIT license at the repository root covers WeHarbor's integration code.
It does not relicense vendor applications, base-image packages or native libraries.

| Component | Source / origin | License and handling |
| --- | --- | --- |
| wechat-selkies | https://github.com/nickrunning/wechat-selkies | MIT; pinned minimal base image. The original notice is in licenses/wechat-selkies.MIT.txt. |
| LinuxServer.io / Selkies | Dependencies provided by the pinned base image | Their upstream licenses and installed package notices remain applicable. |
| Official Linux WeChat | https://linux.weixin.qq.com/ | Proprietary vendor distribution. The integration downloads the official deb and preserves its application and package files. Verify redistribution terms before publishing a combined image. |
| WeFlow | https://github.com/hicccc77/WeFlow | Published source carries CC BY-NC-SA 4.0. A reference license is retained in licenses/WeFlow.CC-BY-NC-SA-4.0.txt. Exact 6.3.2 binary/native redistribution terms remain unverified. |
| Electron / Chromium / WeFlow native libraries | Included in the original WeFlow archive | Original files and embedded notices are retained unchanged under /opt/weflow. |

The WeFlow reference license was retained from a previously provided upstream
distribution. It documents the published source license and is not evidence that
every component of the 6.3.2 binary has the same license.

WeHarbor does not unpack/rebuild app.asar, patch database libraries or claim
ownership of upstream applications. The ASAR checksum is verified before packaging.
Image notices are installed at /usr/share/doc/weharbor; original application
notices remain in their vendor locations.

WeHarbor is an independent community integration. Its name does not imply
endorsement by Tencent, WeFlow, LinuxServer.io or the Selkies maintainers.
