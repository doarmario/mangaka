FROM docker:28-cli AS base

RUN apk add --no-cache bash git util-linux openssl jq

COPY --chmod=755 loop.sh /opt/mangaka-update-loop.sh
COPY --chmod=755 install.sh /opt/mangaka-install.sh
COPY --chmod=755 entrypoint.sh /opt/mangaka-entrypoint.sh

FROM base AS test

COPY permissions.test.sh /tmp/permissions.test.sh

RUN bash /tmp/permissions.test.sh /opt/mangaka-entrypoint.sh && touch /permissions-passed

FROM base AS runtime

COPY --from=test /permissions-passed /permissions-passed

ENTRYPOINT ["/bin/bash", "/opt/mangaka-entrypoint.sh"]
CMD ["update"]
