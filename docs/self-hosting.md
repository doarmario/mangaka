# Executar o Mangaka em casa

## Requisitos

- Docker Engine e Docker Compose Plugin no Linux, ou Docker Desktop no Windows
  configurado para containers Linux;
- Git;
- pelo menos 2 GB de memória disponível para os containers;
- internet na instalação e nas atualizações.

## Instalação rápida

Após clonar o projeto, na pasta `mangaka`, execute este único comando (também no
PowerShell do Windows):

```bash
docker compose -f compose.install.yaml run --build --rm installer
```

O instalador cria `.env` com credenciais aleatórias, baixa automaticamente a API
adicional em `.local/manga-novel-api`, constrói as imagens, aplica as migrações,
inicia o site e ativa as atualizações automáticas. Não precisa programar, editar
configurações ou instalar Python/Node. Abra `http://localhost:5000` e crie sua conta.
No Linux, `bash scripts/install.sh` é um atalho para o mesmo comando.

Se houver um erro de rede, execute o comando novamente. Credenciais existentes,
volumes e checkouts da API não são substituídos. Se já houver um `.env`, sua
configuração será preservada e `MANGA_NOVEL_SOURCE_DIR` será respeitado. Um `.env`
com senhas de exemplo é recusado; em uma instalação nova, deixe o instalador gerar
esse arquivo. Não apague o `.env` de uma instalação que já possui dados.

O instalador e o atualizador usam o socket Docker para gerenciar os containers.
Use somente uma cópia confiável do projeto. O site não recebe esse acesso.
O Docker precisa continuar funcionando; configure o Docker Desktop para iniciar
com sua sessão se desejar. Se o acesso ao Docker for negado no Linux, configure
as permissões de acesso ao Docker antes de executar o instalador.

Para verificar o estado ou acompanhar o atualizador:

```bash
docker compose -f compose.yaml -f compose.updater.yaml ps
docker compose -f compose.yaml -f compose.updater.yaml logs --tail=100 auto-updater
```

Detalhes e limitações estão em [Atualizações automáticas](auto-update.md).

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
docker compose -f compose.yaml -f compose.updater.yaml up -d
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
