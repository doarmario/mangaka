#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

command -v docker >/dev/null || { echo "Docker não encontrado." >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose não encontrado." >&2; exit 1; }

if [[ ! -f .env ]]; then
  cp .env.example .env
  if command -v openssl >/dev/null; then
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
    sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=$(openssl rand -hex 24)/" .env
    sed -i "s/^MYSQL_ROOT_PASSWORD=.*/MYSQL_ROOT_PASSWORD=$(openssl rand -hex 24)/" .env
  else
    echo "Instale openssl para gerar credenciais automaticamente." >&2
    exit 1
  fi
  echo ".env criado com credenciais aleatórias. Guarde o arquivo com segurança."
fi

docker compose up -d --build --remove-orphans
docker compose run --rm web flask --app app db upgrade
docker compose up -d --remove-orphans
docker compose ps
