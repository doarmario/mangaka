FROM docker:28-cli
RUN apk add --no-cache bash git util-linux openssl jq
COPY loop.sh /opt/mangaka-update-loop.sh
COPY install.sh /opt/mangaka-install.sh
ENTRYPOINT ["/bin/bash", "/opt/mangaka-update-loop.sh"]
