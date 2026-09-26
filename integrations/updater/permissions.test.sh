#!/usr/bin/env bash
# Runs as root during the image build, with real setpriv and Git.
set -Eeuo pipefail
entrypoint="${1:?entrypoint path required}"
fixture="$(mktemp -d)"
chmod 755 "$fixture"
workspace="$fixture/workspace"
mkdir -p "$workspace/scripts"
chown 10001:10001 "$workspace"
git -c safe.directory="$workspace" init -q "$workspace"
printf 'data\n' > "$workspace/tracked.txt"
chmod 600 "$workspace/tracked.txt"
touch "$fixture/socket" "$fixture/outside"
chown 0:10002 "$fixture/socket"
ln -s "$fixture/outside" "$workspace/outside-link"
cat > "$workspace/scripts/auto-update.sh" <<'EOF'
set -Eeuo pipefail
test "$(id -u)" = 10001
test "$(id -g)" = 10001
case " $(id -G) " in *' 10002 '*) ;; *) exit 1 ;; esac
test -w "$DOCKER_CONFIG"
git config --global user.name 'Permission test'
git config --global user.email 'test@example.invalid'
cd "$MANGAKA_INSTALL_ROOT"
git add tracked.txt
git commit -qm 'Test owner preservation'
test "$(stat -c %u .git/index)" = 10001
umask 077
printf 'backup\n' > .git/mangaka-update/backup
test "$(stat -c %u .git/mangaka-update/backup)" = 10001
test "$(stat -c %a .git/mangaka-update/backup)" = 600
EOF
MANGAKA_INSTALL_ROOT="$workspace" MANGAKA_DOCKER_SOCKET="$fixture/socket" \
    bash "$entrypoint" update-once
test "$(stat -c %u "$fixture/outside")" = 0
test "$(stat -c %u "$workspace/tracked.txt")" = 10001
test "$(stat -c %a "$workspace/tracked.txt")" = 600
# Fresh installers also receive a root-created bind directory from Docker.
api="$fixture/api"
mkdir "$api"
chmod 700 "$api"
cp /opt/mangaka-install.sh "$fixture/original-install.sh"
cat > /opt/mangaka-install.sh <<'EOF'
set -Eeuo pipefail
test "$(id -u)" = 10001
umask 077
printf 'secret\n' > "$MANGAKA_INSTALL_ROOT/.env"
printf 'source\n' > "$MANGAKA_INSTALL_API/package.json"
EOF
MANGAKA_INSTALL_ROOT="$workspace" MANGAKA_INSTALL_API="$api" \
    MANGAKA_DOCKER_SOCKET="$fixture/socket" bash "$entrypoint" install
mv "$fixture/original-install.sh" /opt/mangaka-install.sh
test "$(stat -c %u "$api/package.json")" = 10001
test "$(stat -c %u "$workspace/.env")" = 10001
test "$(stat -c %a "$workspace/.env")" = 600
test -z "$(find /tmp -maxdepth 1 -name 'mangaka-user.*' -print)"
echo 'Permission regression passed: Git, backup ownership, socket group and symlink isolation.'
