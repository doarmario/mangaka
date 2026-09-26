#!/usr/bin/env bash
# Run in the updater image as root with the repository mounted read-only at /fixture.
set -Eeuo pipefail
mkdir -p /workspace/scripts /workspace/integrations/updater /upstream
cp /fixture/scripts/auto-update.sh /workspace/scripts/
cp /fixture/integrations/updater/entrypoint.sh /workspace/integrations/updater/
git init -q /workspace
git -C /workspace config user.name Test
git -C /workspace config user.email test@example.invalid
printf 'original\n' > /workspace/tracked.txt
git -C /workspace add .
git -C /workspace commit -qm initial
# Old releases have left root-owned, private metadata in a user-owned clone.
chown 10001:10001 /workspace
chmod 700 /workspace/.git
chmod 600 /workspace/.git/index
touch /workspace/.env
chmod 600 /workspace/.env
mkdir -p /workspace/.git/mangaka-update/backups
printf 'private\n' > /workspace/.git/mangaka-update/backups/test.sql
chmod 600 /workspace/.git/mangaka-update/backups/test.sql
# Foreign files and symlink targets must not be appropriated by the repair.
touch /workspace/foreign /tmp/outside
chown 10003:10003 /workspace/foreign
ln -s /tmp/outside /workspace/outside
mkdir /fakebin
cat > /fakebin/docker <<'DOCKER'
#!/bin/sh
exit 91
DOCKER
chmod 755 /fakebin/docker
export PATH="/fakebin:$PATH"
touch /tmp/socket
chown 0:10002 /tmp/socket
export MANGAKA_DOCKER_SOCKET=/tmp/socket
# The deliberately dirty clone must stop BEFORE deployment, but AFTER recovery.
for cycle in 1 2; do
    if bash /workspace/scripts/auto-update.sh > /tmp/result 2>&1; then
        echo 'Expected dirty checkout to stop deployment' >&2; exit 1
    fi
    cat /tmp/result
    grep -q 'existem alterações locais' /tmp/result
    test "$(stat -c %u /workspace/.git/index)" = 10001
    test "$(stat -c %u /workspace/.env)" = 10001
    test "$(stat -c %a /workspace/.env)" = 600
    test "$(stat -c %u /workspace/.git/mangaka-update/backups/test.sql)" = 10001
    test "$(stat -c %a /workspace/.git/mangaka-update/backups/test.sql)" = 600
    test "$(stat -c %u /workspace/foreign)" = 10003
    test "$(stat -c %u /tmp/outside)" = 0
    test -z "$(find /tmp -maxdepth 1 -name 'mangaka-user.*' -print)"
done
# Match the UID used by a new image, and verify repeated cycles need no root.
setpriv --reuid=10001 --regid=10001 --clear-groups -- \
    bash /workspace/integrations/updater/entrypoint.sh update-once > /tmp/nonroot-result 2>&1 && exit 1
grep -q 'existem alterações locais' /tmp/nonroot-result
test -z "$(find /tmp -maxdepth 1 -name 'mangaka-user.*' -print)"
echo 'Legacy root and current non-root cycles recover safely; modes and ownership preserved.'
