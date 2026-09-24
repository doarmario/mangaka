FROM docker:28-cli
RUN apk add --no-cache bash git util-linux
COPY loop.sh /opt/mangaka-update-loop.sh
ENTRYPOINT ["/bin/bash", "/opt/mangaka-update-loop.sh"]
