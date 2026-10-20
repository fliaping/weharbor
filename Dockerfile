# syntax=docker/dockerfile:1
# Plain LinuxServer.io Selkies base (Debian trixie, Selkies 2.0.0, X11/Openbox).
ARG BASE_IMAGE=ghcr.io/linuxserver/baseimage-selkies:debiantrixie@sha256:5b3f10459933740554081efbca9c8d5e006faf5116b54ab40b7bfad7c8111849
FROM ${BASE_IMAGE} AS integration-files
COPY root/ /integration/
# A checkout copied from a private home can inherit restrictive directory modes.
# Normalize the overlay before merging it into existing image directories.
RUN find /integration -type d -exec chmod 0755 {} + \
    && find /integration -type f -exec chmod 0644 {} +

FROM ${BASE_IMAGE} AS workspace-runtime
COPY downloads/node.tar.xz downloads/analysis.tar.gz downloads/tailscale.tgz downloads/cloudflared /tmp/assets/
COPY versions.lock.json /tmp/versions.lock.json
RUN python3 -c "import hashlib,json,pathlib; lock=json.load(open('/tmp/versions.lock.json')); [(lambda p,c: (None if hashlib.sha256(p.read_bytes()).hexdigest()==c['sha256'] else (_ for _ in ()).throw(ValueError(str(p)))))(pathlib.Path('/tmp/assets')/lock[n]['filename'],lock[n]) for n in ['node','analysis','tailscale','cloudflared']]" \
    && mkdir -p /opt/weharbor/node /opt/weharbor/analysis /opt/weharbor/network \
    && python3 -c "import lzma,shutil; shutil.copyfileobj(lzma.open('/tmp/assets/node.tar.xz'),open('/tmp/node.tar','wb'))" \
    && tar -xf /tmp/node.tar --strip-components=1 -C /opt/weharbor/node \
    && tar -xzf /tmp/assets/analysis.tar.gz --strip-components=1 -C /opt/weharbor/analysis \
    && tar -xzf /tmp/assets/tailscale.tgz --strip-components=1 -C /opt/weharbor/network \
    && cp /tmp/assets/cloudflared /opt/weharbor/network/cloudflared \
    && chmod 0755 /opt/weharbor/network/cloudflared
ENV PATH="/opt/weharbor/node/bin:${PATH}"
WORKDIR /opt/weharbor/analysis/frontend
RUN npm ci --no-audit --no-fund \
    && NUXT_APP_BASE_URL=/analysis/ NUXT_PUBLIC_API_BASE=/analysis/api npm run generate \
    && mv .output/public /opt/weharbor/analysis/ui \
    && rm -rf /opt/weharbor/analysis/frontend /opt/weharbor/analysis/data /opt/weharbor/analysis/output /opt/weharbor/analysis/.git
COPY runtime/harness/package*.json /opt/weharbor/harness/
WORKDIR /opt/weharbor/harness
RUN npm ci --omit=dev --no-audit --no-fund \
    && node node_modules/@deepseek-ai/dsh-subprocess-local/scripts/ensure-spawn-helper.mjs \
    && node -e "require('node-pty'); require('koffi')"

FROM ${BASE_IMAGE}
ARG TARGETARCH
ARG PROJECT_VERSION=0.1.0
ARG PROJECT_SOURCE
ARG PROJECT_REVISION
ARG APT_MIRROR
LABEL org.opencontainers.image.title="WeHarbor" \
      org.opencontainers.image.description="Self-hosted WeChat desktop, Alpha data APIs and message notifications in one container" \
      org.opencontainers.image.version="${PROJECT_VERSION}" \
      org.opencontainers.image.source="${PROJECT_SOURCE}" \
      org.opencontainers.image.revision="${PROJECT_REVISION}"

# Desktop integration packages that wechat-selkies used to provide, plus the
# Secret Service Alpha needs for Electron safeStorage.
RUN test "${TARGETARCH:-amd64}" = amd64 \
    && sed -i -e '/^deb-src /d' \
        -e 's#http://security.debian.org/debian-security/*#http://deb.debian.org/debian-security#' \
        /etc/apt/sources.list \
    && if [ -n "${APT_MIRROR}" ]; then \
        sed -i "s#http://deb.debian.org/#${APT_MIRROR%/}/#g" /etc/apt/sources.list; \
    fi \
    && echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-weharbor-retries \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        dbus-x11 gnome-keyring libsecret-1-0 inotify-tools stalonetray \
        python3-dbus python3-xlib python3-gi gir1.2-atspi-2.0 at-spi2-core \
        python3-venv python3-dev build-essential gdb sudo \
        tesseract-ocr tesseract-ocr-chi-sim \
        libatomic1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
        libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
        libxkbcommon-x11-0 libnss3 libgbm1 libasound2t64 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=workspace-runtime /opt/weharbor/ /opt/weharbor/
RUN /usr/bin/python3 -m venv --system-site-packages /opt/weharbor/python \
    && /opt/weharbor/python/bin/pip install --no-cache-dir -r /opt/weharbor/analysis/requirements-linux.txt \
    && /opt/weharbor/python/bin/python -c "import gi,fastapi,cryptography,pilk; gi.require_version('Atspi','2.0')"

COPY versions.lock.json /usr/share/weharbor/versions.lock.json
COPY scripts/verify-assets.py /tmp/verify-assets.py
COPY downloads/wechat.deb /tmp/wechat.deb
COPY downloads/alpha.deb /tmp/alpha.deb
RUN apt-get update \
    && python3 /tmp/verify-assets.py wechat \
        --lock /usr/share/weharbor/versions.lock.json --asset /tmp/wechat.deb --install \
    && python3 /tmp/verify-assets.py alpha \
        --lock /usr/share/weharbor/versions.lock.json --asset /tmp/alpha.deb --install \
    && rm -rf /var/lib/apt/lists/* /tmp/wechat.deb /tmp/alpha.deb /tmp/verify-assets.py \
    && icon="$(find /usr/share/icons/hicolor -name alpha.png | sort -V | tail -1)" \
    && cp "$icon" /usr/share/pixmaps/alpha.png \
    && cp /usr/share/icons/hicolor/128x128/apps/wechat.png /usr/share/selkies/www/icon.png

COPY --from=integration-files /integration/ /
COPY skills/weharbor-api/ /usr/share/weharbor/skills/weharbor-api/
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/doc/weharbor/
RUN test -f /defaults/default.conf \
    && chmod -R a+rX /usr/share/doc/weharbor /usr/share/weharbor/skills \
    && sed -i '\|location SUBFOLDERapi {|i\  include /defaults/notification-proxy.conf;' /defaults/default.conf \
    && grep -q notification-proxy.conf /defaults/default.conf \
    && sed -i '\|location SUBFOLDERapi {|i\  include /defaults/workspace-proxy.conf;' /defaults/default.conf \
    && cat /defaults/alpha-api-proxy.conf >> /defaults/default.conf \
    && sed -i 's#</body>#<script src="./browser-notifications.js"></script></body>#' \
        /usr/share/selkies/selkies-dashboard/index.html \
    && python3 /scripts/weharbor/install-web.py \
    && sed -i '/<dock>/,/<\/dock>/s/<noStrut>no<\/noStrut>/<noStrut>yes<\/noStrut>/' /etc/xdg/openbox/rc.xml \
    && ln -sfn /scripts/weharbor/wechat-launch.py /usr/bin/wechat \
    && chmod 0755 \
        /etc/s6-overlay/s6-rc.d/svc-app-switcher/run \
        /etc/s6-overlay/s6-rc.d/init-weharbor-profile/run \
        /scripts/app-switcher/app-switcher.py \
        /scripts/notifications/*.sh /scripts/notifications/*.py \
        /scripts/alpha/*.sh /scripts/wechat/*.sh /scripts/weharbor/* \
        /scripts/workspace/*.sh /etc/s6-overlay/s6-rc.d/svc-analysis/run \
        /etc/s6-overlay/s6-rc.d/svc-workspace/run /etc/s6-overlay/s6-rc.d/svc-harness/run \
        /usr/local/bin/stalonetray /usr/local/bin/weharbor-health /usr/local/bin/weharbor-capture-key \
    && chmod 0440 /etc/sudoers.d/weharbor-capture \
    && visudo -cf /etc/sudoers.d/weharbor-capture

ENV TITLE="WeHarbor｜微港" \
    SELKIES_UI_TITLE="WeHarbor｜微港" \
    TZ="Asia/Shanghai" \
    LC_ALL="zh_CN.UTF-8" \
    AUTO_START_WECHAT="true" \
    AUTO_START_ALPHA="true" \
    ALPHA_API_PORT="5031" \
    ALPHA_API_PROXY_PORT="5032" \
    ENABLE_APP_SWITCHER="true" \
    APP_SWITCHER_MODE="web" \
    ENABLE_WINDOW_DEFAULTS="true" \
    ENABLE_BROWSER_NOTIFICATIONS="true"
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD /usr/local/bin/weharbor-health
