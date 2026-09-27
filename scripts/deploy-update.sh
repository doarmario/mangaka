#!/usr/bin/env bash
# Internal deployment phase; auto-update.sh owns the Git update and lock.
set -Eeuo pipefail
umask 077
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
[[ "$(id -u)" == "$(stat -c '%u' "$ROOT_DIR")" ]] || {
    echo "Implantação bloqueada: execute o atualizador como o dono do projeto." >&2; exit 1;
}
TARGET="${1:?Commit alvo ausente}"
STATE_DIR="$(git rev-parse --absolute-git-dir)/mangaka-update"
[[ /proc/$$/fd/9 -ef "$STATE_DIR/lock" ]] && flock -n 9 || {
    echo "Execute scripts/auto-update.sh para adquirir o lock da implantação." >&2; exit 1;
}
[[ "$(git rev-parse HEAD)" == "$TARGET" && -z "$(git status --porcelain)" ]] || {
    echo "O checkout mudou durante a atualização; implantação cancelada." >&2; exit 1;
}
trap 'echo "Implantação incompleta; será tentada novamente no próximo ciclo." >&2' ERR
# Only the application file: never rebuild or stop the updater itself.
compose() { docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/compose.yaml" "$@"; }
compose config --quiet
configured="$(compose config --services)"
services=()
while IFS= read -r service; do
    case "$service" in ''|init-db|auto-updater) continue ;; esac
    services+=("$service")
done <<< "$configured"
((${#services[@]})) || { echo "Nenhum serviço configurado para implantação." >&2; exit 1; }

services_ready() {
    local state healthy service
    state="$(compose ps --format json)" || return 2
    healthy="$(jq -sr 'flatten | .[] | select(.State == "running" and
        ((.Health // "") == "" or .Health == "healthy")) | .Service' <<< "$state")" || return 2
    for service in "${services[@]}"; do
        if ! grep -Fxq -- "$service" <<< "$healthy"; then
            echo "Serviço ausente, parado ou sem saúde: $service"
            return 1
        fi
    done
}
if [[ -f "$STATE_DIR/deployed" && "$(cat "$STATE_DIR/deployed")" == "$TARGET" ]]; then
    status=0
    services_ready || status=$?
    case "$status" in
        0) echo "Instalação já atualizada e serviços ativos: $TARGET"; exit 0 ;;
        1) echo "Reparando a implantação do commit $TARGET..."
           mv "$STATE_DIR/deployed" "$STATE_DIR/deployed.previous" ;;
        *) echo "Não foi possível verificar os containers." >&2; exit 1 ;;
    esac
fi
compose version >/dev/null
docker info >/dev/null
# Discover build targets from the current Compose, including newly added sources.
compose build "${services[@]}"
compose up -d --wait mysql redis
compose stop web updates-worker
mkdir -p "$STATE_DIR/backups"
BACKUP="$STATE_DIR/backups/$(date -u +%Y%m%dT%H%M%S)-$$-$TARGET.sql"
compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysqldump -u "$MYSQL_USER" --single-transaction --no-tablespaces "$MYSQL_DATABASE"' > "$BACKUP.partial"
test -s "$BACKUP.partial"
mv "$BACKUP.partial" "$BACKUP"
compose run --rm --no-deps web flask --app app db upgrade
compose up -d --wait --wait-timeout 180 "${services[@]}"
services_ready
printf '%s\n' "$TARGET" > "$STATE_DIR/deployed.pending"
mv "$STATE_DIR/deployed.pending" "$STATE_DIR/deployed"
echo "Atualização concluída: $TARGET. Backup: $BACKUP"
