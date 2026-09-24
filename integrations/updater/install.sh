#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Instalação interrompida. Seus dados foram preservados. Corrija o erro acima e execute o mesmo comando novamente." >&2' ERR
ROOT_DIR="${MANGAKA_INSTALL_ROOT:-/workspace}"
API_DIR="${MANGAKA_INSTALL_API:-/upstream}"
cd "$ROOT_DIR"
git config --global --add safe.directory "$ROOT_DIR"
git config --global --add safe.directory "$API_DIR"
git rev-parse --is-inside-work-tree >/dev/null
docker info >/dev/null
# Resolve bind sources using the daemon, not container-local paths. This also
# works with paths translated by Docker Desktop on Windows.
mounts="$(docker inspect "$HOSTNAME" --format '{{json .Mounts}}')"
export MANGAKA_HOST_WORKSPACE="$(jq -er '.[] | select(.Destination == "/workspace") | .Source' <<< "$mounts")"
export MANGAKA_HOST_UPSTREAM="$(jq -er '.[] | select(.Destination == "/upstream") | .Source' <<< "$mounts")"
export DOCKER_SOCKET_PATH="$(jq -er '.[] | select(.Destination == "/var/run/docker.sock") | .Source' <<< "$mounts")"

state_dir="$(git rev-parse --absolute-git-dir)/mangaka-update"
mkdir -p "$state_dir"
exec 9>"$state_dir/lock"
flock -n 9 || { echo "Já existe uma instalação ou atualização em andamento. Aguarde e tente novamente." >&2; exit 1; }
if [[ ! -f .env ]]; then
    echo "[1/5] Criando configuração e senhas aleatórias..."
    # Publish only after all credentials have been generated successfully.
    (umask 077
     cp .env.example .env.installing
     secret_key="$(openssl rand -hex 32)"
     db_password="$(openssl rand -hex 24)"
     root_password="$(openssl rand -hex 24)"
     sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$secret_key/" .env.installing
     sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=$db_password/" .env.installing
     sed -i "s/^MYSQL_ROOT_PASSWORD=.*/MYSQL_ROOT_PASSWORD=$root_password/" .env.installing
     sed -i 's|^MANGA_NOVEL_SOURCE_DIR=.*|MANGA_NOVEL_SOURCE_DIR=./.local/manga-novel-api|' .env.installing
     chown "$(stat -c '%u:%g' "$ROOT_DIR")" .env.installing
     mv .env.installing .env)
else
    echo "[1/5] Preservando a configuração existente..."
fi
if grep -Eq '^(SECRET_KEY|DB_PASSWORD|MYSQL_ROOT_PASSWORD)=troque-' .env; then
    echo "O .env existente contém senhas de exemplo. Substitua-as antes de continuar; senhas existentes não são alteradas automaticamente." >&2
    exit 1
fi

echo "[2/5] Preparando a API de mangás..."
if [[ ! -f "$API_DIR/package.json" ]]; then
    # Never replace a populated/custom checkout. Clone to a temporary directory
    # so a network failure leaves the destination ready for another attempt.
    if [[ -n "$(ls -A "$API_DIR")" ]]; then
        echo "A pasta da API contém arquivos, mas não possui package.json. Confira MANGA_NOVEL_SOURCE_DIR." >&2
        exit 1
    fi
    staging="$(mktemp -d)"
    git clone --depth 1 https://github.com/Raby012/-manga-novel-api.git "$staging/api"
    cp -a "$staging/api/." "$API_DIR/"
    chown -R "$(stat -c '%u:%g' "$ROOT_DIR")" "$API_DIR"
fi
export MANGA_NOVEL_SOURCE_DIR="$API_DIR"
compose() { docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/compose.yaml" "$@"; }
echo "[3/5] Construindo o site (a primeira instalação pode demorar)..."
compose config --quiet
compose build web manga-novel
compose up -d --wait mysql redis
echo "[4/5] Preparando o banco e iniciando o site..."
compose run --rm --no-deps web flask --app app init-db
compose run --rm --no-deps web flask --app app db upgrade
compose up -d --wait --wait-timeout 180 web updates-worker manga-novel
echo "[5/5] Ativando as atualizações automáticas..."
docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/compose.yaml" -f "$ROOT_DIR/compose.updater.yaml" up -d --build auto-updater
port="$(compose config --format json | jq -r '.services.web.ports[0].published')"
echo "Mangaka pronto! Abra http://localhost:$port e crie sua conta."
echo "As atualizações serão verificadas automaticamente enquanto o Docker estiver funcionando."
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Atenção: há alterações locais; o atualizador aguardará um checkout limpo para aplicar novos commits."
fi
