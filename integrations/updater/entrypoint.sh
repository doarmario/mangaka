#!/usr/bin/env bash
set -Eeuo pipefail

workspace="${MANGAKA_INSTALL_ROOT:-/workspace}"
api="${MANGAKA_INSTALL_API:-/upstream}"
mode="${1:-update}"
case "$mode" in
    install) command=(/bin/bash /opt/mangaka-install.sh) ;;
    update) command=(/bin/bash /opt/mangaka-update-loop.sh) ;;
    update-once) command=(/bin/bash "$workspace/scripts/auto-update.sh") ;;
    *) echo "Modo desconhecido: $mode" >&2; exit 1 ;;
esac

owner_uid="$(stat -c '%u' "$workspace")"
owner_gid="$(stat -c '%g' "$workspace")"
socket="${MANGAKA_DOCKER_SOCKET:-/var/run/docker.sock}"

if [[ "$(id -u)" == 0 ]]; then
    # Repair files left by older root-based releases. Never follow symlinks or
    # cross into other mounts, and preserve files belonging to other users.
    [[ -d "$workspace/.git" && ! -L "$workspace/.git" ]] || {
        echo "O instalador requer um clone Git com diretório .git local." >&2; exit 1;
    }
    mkdir -p "$workspace/.git/mangaka-update"
    exec 9>"$workspace/.git/mangaka-update/lock"
    flock 9
    find "$workspace" -xdev -user 0 -exec chown -h "$owner_uid:$owner_gid" {} +
    if [[ "$mode" == install && -d "$api" ]]; then
        find "$api" -xdev -user 0 -exec chown -h "$owner_uid:$owner_gid" {} +
    fi
    flock -u 9
    exec 9>&-
elif [[ "$(id -u)" != "$owner_uid" ]]; then
    echo "Execute com o usuário dono do projeto (UID $owner_uid)." >&2
    exit 1
fi

# A cycle launched by the scheduler can reuse its already-owned runtime.
if [[ "${MANGAKA_RUNTIME_UID:-}" == "$(id -u)" &&
      "$(id -u)" == "$owner_uid" && -w "${DOCKER_CONFIG:-/nonexistent}" &&
      -w "${GIT_CONFIG_GLOBAL:-/nonexistent}" ]]; then
    exec "${command[@]}"
fi

# Neither Git nor the Docker CLI should need access to /root after dropping UID.
runtime="$(mktemp -d /tmp/mangaka-user.XXXXXX)"
trap 'rm -rf -- "$runtime"' EXIT
mkdir "$runtime/docker" "$runtime/config" "$runtime/cache"
export GIT_CONFIG_GLOBAL="$runtime/gitconfig"
touch "$GIT_CONFIG_GLOBAL"
export DOCKER_CONFIG="$runtime/docker"
export XDG_CONFIG_HOME="$runtime/config"
export XDG_CACHE_HOME="$runtime/cache"
export MANGAKA_RUNTIME_UID="$owner_uid"
if [[ "$(id -u)" == 0 ]]; then
    chown -R "$owner_uid:$owner_gid" "$runtime"
    socket_gid="$(stat -c '%g' "$socket")"
    # The socket group permits Compose operations; Git and files use the host UID.
    setpriv --reuid="$owner_uid" --regid="$owner_gid" --groups="$socket_gid" -- "${command[@]}" &
else
    "${command[@]}" &
fi
child=$!
trap 'kill -TERM "$child" 2>/dev/null || true' TERM INT
status=0
wait "$child" || status=$?
# A signal may interrupt wait before the child has released the deployment lock.
if kill -0 "$child" 2>/dev/null; then
    wait "$child" || status=$?
fi
exit "$status"
