# syntax=docker/dockerfile:1
ARG BASE_IMAGE=ghcr.io/nickrunning/wechat-selkies:0.0.14-minimal@sha256:32b9094316b0bd267dc7d1778116a91a6a349fce20bb8dd652dbb9b38e0ef6ee
FROM ${BASE_IMAGE} AS weflow-extracted
ARG TARGETARCH
COPY versions.lock.json /tmp/versions.lock.json
COPY scripts/verify-assets.py /tmp/verify-assets.py
COPY downloads/weflow.tar.gz /tmp/weflow.tar.gz
RUN test "${TARGETARCH:-amd64}" = amd64 \
    && python3 /tmp/verify-assets.py weflow \
        --lock /tmp/versions.lock.json --asset /tmp/weflow.tar.gz \
        --extract /opt/weflow

FROM ${BASE_IMAGE} AS integration-files
COPY root/ /integration/
# A checkout copied from a private home can inherit restrictive directory modes.
# Normalize the overlay before merging it into existing image directories.
RUN find /integration -type d -exec chmod 0755 {} + \
    && find /integration -type f -exec chmod 0644 {} +

FROM ${BASE_IMAGE}
ARG PROJECT_VERSION=0.1.0
ARG PROJECT_SOURCE
ARG PROJECT_REVISION
ARG APT_MIRROR
LABEL org.opencontainers.image.title="WeHarbor" \
      org.opencontainers.image.description="Self-hosted WeChat desktop, WeFlow APIs and message notifications in one container" \
      org.opencontainers.image.version="${PROJECT_VERSION}" \
      org.opencontainers.image.source="${PROJECT_SOURCE}" \
      org.opencontainers.image.revision="${PROJECT_REVISION}"

RUN if [ -n "${APT_MIRROR}" ]; then \
        sed -i "s#http://archive.ubuntu.com/ubuntu/#${APT_MIRROR%/}/#g" /etc/apt/sources.list; \
    fi \
    && apt-get update -o Dir::Etc::sourcelist="sources.list" -o Dir::Etc::sourceparts="-" \
    && apt-get install -y --no-install-recommends pkexec \
    && rm -rf /var/lib/apt/lists/*

COPY versions.lock.json /usr/share/weharbor/versions.lock.json
COPY scripts/verify-assets.py /tmp/verify-assets.py
COPY downloads/wechat.deb /tmp/wechat.deb
RUN python3 /tmp/verify-assets.py wechat \
        --lock /usr/share/weharbor/versions.lock.json --asset /tmp/wechat.deb --install \
    && rm /tmp/wechat.deb /tmp/verify-assets.py

COPY --from=weflow-extracted /opt/weflow /opt/weflow
RUN chmod -R a+rX /opt/weflow \
    && ln -s /opt/weflow/weflow /usr/local/bin/weflow \
    && cp /opt/weflow/resources/icon.png /usr/share/pixmaps/weflow.png

COPY --from=integration-files /integration/ /
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/doc/weharbor/
COPY licenses/ /usr/share/doc/weharbor/licenses/
RUN test -f /defaults/default.conf \
    && chmod -R a+rX /usr/share/doc/weharbor \
    && sed -i '\|location SUBFOLDERfiles {|i\  include /defaults/notification-proxy.conf;' /defaults/default.conf \
    && sed -i 's#</body>#<script src="./browser-notifications.js"></script></body>#' \
        /usr/share/selkies/selkies-dashboard/index.html \
    && cp /usr/share/selkies/selkies-dashboard/browser-notifications.js \
        /usr/share/selkies/web/browser-notifications.js \
    && chmod 0755 \
        /etc/s6-overlay/s6-rc.d/svc-app-switcher/run \
        /etc/s6-overlay/s6-rc.d/svc-polkitd/run \
        /scripts/app-switcher/app-switcher.py \
        /scripts/notifications/*.sh /scripts/notifications/*.py \
        /scripts/weflow/*.sh /scripts/weharbor/* \
        /usr/local/bin/stalonetray /usr/local/bin/weharbor-health

ENV TITLE="WeHarbor · 微港" \
    AUTO_START_WECHAT="true" \
    AUTO_START_QQ="false" \
    AUTO_START_WEFLOW="true" \
    ENABLE_APP_SWITCHER="true" \
    ENABLE_BROWSER_NOTIFICATIONS="true"
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD /usr/local/bin/weharbor-health
