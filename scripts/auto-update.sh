#!/usr/bin/env bash
# Run from a dedicated, clean installation checkout.
set -Eeuo pipefail
umask 077
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ "$(id -u)" != "$(stat -c '%u' "$ROOT_DIR")" ]]; then
    echo "Atualização bloqueada: execute como o dono do projeto. No Docker, use /opt/mangaka-entrypoint.sh update-once." >&2
    exit 1
fi
# Always use only the application stack. The updater must not rebuild or stop
# itself, nor resolve host bind mounts from inside its container.
compose() { docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/compose.yaml" "$@"; }
STATE_DIR="$(git rev-parse --absolute-git-dir)/mangaka-update"
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/lock"
flock -n 9 || exit 0
trap 'echo "Atualização falhou. Consulte os logs antes de reiniciar os serviços; nenhum rollback de banco foi executado." >&2' ERR

if [[ -n "$(git status --porcelain)" ]]; then
    echo "Atualização bloqueada: existem alterações locais. Faça commit ou use uma instalação separada." >&2
    exit 1
fi
[[ -f .env ]] || { echo "Execute a instalação primeiro (.env ausente)." >&2; exit 1; }
BRANCH="$(git symbolic-ref --short HEAD)"
REMOTE="$(git config --get "branch.$BRANCH.remote")"
[[ "$REMOTE" != . ]] || { echo "Configure um remoto para esta branch." >&2; exit 1; }
git fetch --prune "$REMOTE"
TARGET="$(git rev-parse '@{upstream}')"
git merge-base --is-ancestor HEAD "$TARGET" || {
    echo "Atualização bloqueada: histórico local diverge do remoto." >&2; exit 1;
}
if [[ -f "$STATE_DIR/deployed" && "$(cat "$STATE_DIR/deployed")" == "$TARGET" ]]; then
    echo "Instalação já atualizada: $TARGET"
    exit 0
fi
compose version >/dev/null
docker info >/dev/null
git merge --ff-only "$TARGET"
compose config --quiet
# Build first, while the current site is still available.
compose build web manga-novel qiscans
compose up -d --wait mysql redis
compose stop web updates-worker
mkdir -p "$STATE_DIR/backups"
BACKUP="$STATE_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ)-$TARGET.sql"
compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysqldump -u "$MYSQL_USER" --single-transaction --no-tablespaces "$MYSQL_DATABASE"' > "$BACKUP.partial"
test -s "$BACKUP.partial"
mv "$BACKUP.partial" "$BACKUP"
compose run --rm --no-deps web flask --app app db upgrade
compose up -d --wait --wait-timeout 180 web updates-worker manga-novel qiscans
printf '%s\n' "$TARGET" > "$STATE_DIR/deployed"
echo "Atualização concluída: $TARGET. Backup: $BACKUP"
