# Executar o Mangaka em casa

## Requisitos

- Docker Engine e Docker Compose Plugin;
- Git;
- pelo menos 2 GB de memória disponível para os containers;
- uma cópia do checkout da API adicional em `../manga-novel-api`, ou outro caminho definido por `MANGA_NOVEL_SOURCE_DIR`.

## Instalação rápida

Na raiz do projeto:

```bash
./scripts/install.sh
```

O script cria `.env` com credenciais aleatórias, constrói as imagens, aplica as
migrações e inicia o site. Abra `http://localhost:5000`.

## Acesso na rede local

Edite `.env`:

```env
MANGAKA_BIND_ADDRESS=0.0.0.0
MANGAKA_PORT=5000
```

Reinicie:

```bash
docker compose up -d
hostname -I
```

No celular ou tablet conectado à mesma rede, abra
`http://IP_DO_COMPUTADOR:5000`. Se houver firewall, libere somente essa porta
na rede local.

## Atualizar

```bash
git pull
docker compose build
docker compose run --rm web flask --app app db upgrade
docker compose up -d --remove-orphans
```

## Backup e restauração

Faça backup antes de atualizar:

```bash
docker compose exec -T mysql sh -c 'exec mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' > backup.sql
```

Para restaurar em uma instalação parada:

```bash
docker compose exec -T mysql sh -c 'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < backup.sql
```

Não use `docker compose down -v` sem um backup: isso remove os volumes do banco
e do Redis.

## Publicar com segurança

Para acesso fora da rede local, coloque um proxy reverso com HTTPS na frente do
container `web` e não exponha MySQL ou Redis. Configure autenticação forte,
backup periódico e mantenha o `.env` fora do controle de versão.
