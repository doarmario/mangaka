# Atualizações automáticas pelo Docker

A [instalação em um comando](self-hosting.md#instalação-rápida) já ativa o
atualizador. Os passos abaixo servem para instalações existentes.

Em uma instalação já funcionando, execute na pasta do projeto, pelo terminal
Linux ou PowerShell do Windows:

```bash
docker compose -f compose.yaml -f compose.updater.yaml up -d --build auto-updater
```

No Windows, use Docker Desktop no modo de containers Linux. O agendamento roda
dentro do container `auto-updater`, sem cron, systemd ou Agendador de Tarefas.
O Docker precisa estar em execução; no Windows, configure o Docker Desktop para
iniciar com sua sessão se desejar. A instalação precisa ser um clone Git (não ZIP).

O agendamento verifica a branch remota acompanhada pela branch atual a cada cinco
minutos. A primeira execução também implanta o commit atual. Não há webhook nem
porta adicional. O computador precisa estar ligado e conectado à internet.
O intervalo é definido por `AUTO_UPDATE_INTERVAL_SECONDS` no `.env` (padrão 300,
mínimo 60). Após mudar esse valor, execute novamente o comando de ativação.

O atualizador monta o checkout com escrita, o código da API adicional em modo
somente leitura e o socket Docker. Esse socket concede controle do Docker:
ative apenas em um checkout e uma branch confiáveis. O site e o worker não
recebem esse acesso. Não é usado Docker-in-Docker nem `privileged`.

O caminho `MANGA_NOVEL_SOURCE_DIR` do `.env` é interpretado no computador e montado
como `/upstream` no atualizador. Isso permite usar caminhos do Windows sem enviá-los
ao Compose executado dentro do container. Use a configuração padrão de volumes
nomeados dos serviços; bind mounts personalizados nesses serviços precisam estar
disponíveis no mesmo caminho para o Docker host e para o atualizador.
Se sua instalação usa um nome de projeto diferente, defina `COMPOSE_PROJECT_NAME`
no `.env` antes da ativação para reutilizar os mesmos containers e volumes.
Para Docker rootless ou Docker Desktop no Linux, configure `DOCKER_SOCKET_PATH`
no `.env` com o caminho do socket da instalação.

Se você ativou anteriormente o agendamento systemd, desative-o antes de migrar:

```bash
systemctl --user disable --now mangaka-update.timer
```

Use uma instalação sem modificações locais. Commits locais ainda não enviados,
históricos divergentes e arquivos não commitados bloqueiam a atualização.
Configurações pessoais devem ficar no `.env`, que é preservado junto com os
volumes. Por padrão, o container acessa repositórios públicos via HTTPS. Credenciais
Git e agentes SSH do computador não são herdados; repositórios privados exigem
configuração de autenticação dentro do container. Mudanças só locais não são
publicadas por este sistema. O instalador e o atualizador detectam o UID/GID do
dono do checkout e executam com essa identidade, incluindo as operações Git.
O grupo do socket é adicionado para permitir o acesso ao Docker. Na inicialização,
arquivos pertencentes ao root deixados por versões antigas são devolvidos ao dono
do projeto; links simbólicos não são seguidos e outros usuários são preservados.
Os scripts usam finais de linha
LF definidos em `.gitattributes` para também funcionarem em clones no Windows.

O processo baixa commits, avança apenas por fast-forward e constrói as imagens
antes de parar o site e o worker. Em seguida, salva um dump MySQL, aplica as
migrações e sobe os serviços com verificação de saúde do Compose. Há uma breve
indisponibilidade durante o backup, migração e reinício. O código externo da API
Asura não recebe `git pull` automático; permanece na versão instalada.
O atualizador não recria a si próprio. Alterações em sua imagem ou configuração
exigem executar novamente o comando de ativação; o script do ciclo é lido do
checkout a cada execução.

O commit só é marcado como implantado após o sucesso; falhas são tentadas novamente
no próximo ciclo. Falhas após a parada podem deixar o site parado. Consulte os
logs e corrija a causa antes de reiniciar. Não há rollback automático, pois uma
migração pode alterar dados de forma incompatível com o código antigo.

Backups ficam em `.git/mangaka-update/backups/`, com acesso restrito ao usuário.
Não são apagados automaticamente: acompanhe o espaço em disco e copie backups
para outro local. Excluir a instalação também exclui esses backups.

```bash
# Estado e logs
docker compose -f compose.yaml -f compose.updater.yaml ps auto-updater
docker compose -f compose.yaml -f compose.updater.yaml logs --tail=100 auto-updater
# Executar agora (o lock impede dois ciclos simultâneos)
docker compose -f compose.yaml -f compose.updater.yaml exec auto-updater bash /opt/mangaka-entrypoint.sh update-once
# Desativar (aguarde o fim de uma atualização em andamento antes de parar)
docker compose -f compose.yaml -f compose.updater.yaml stop auto-updater
```

Evite `--remove-orphans` ao operar apenas `compose.yaml`, pois o atualizador fica
no arquivo adicional. Inclua ambos os arquivos para administrar a instalação toda.
O script `scripts/enable-auto-update.sh` continua disponível como alternativa
opcional para instalações Linux sem o container de atualização.

### Corrigir arquivos Git criados como root por versões antigas

Após obter esta versão, reconstrua o atualizador:

```bash
docker compose -f compose.yaml -f compose.updater.yaml up -d --build auto-updater
```

O novo entrypoint repara os arquivos do checkout pertencentes ao root e muda para
o UID/GID do dono da pasta antes de iniciar o loop. Isso preserva o modo privado
dos backups e do `.env`, sem usar `chmod 777`. O teste de permissões é executado
durante a construção da imagem, com troca real de UID/GID e operações Git.

Se o índice já estiver bloqueado e impedir o próprio `git pull`, pare o atualizador
antigo e recupere o acesso ao Git uma vez, na pasta do projeto, antes de baixar a
correção (Linux):

```bash
docker compose -f compose.yaml -f compose.updater.yaml stop auto-updater
sudo chown -R "$(id -u):$(id -g)" .git
git pull --ff-only
docker compose -f compose.yaml -f compose.updater.yaml up -d --build auto-updater
```

Referências: [Docker Desktop no Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
e [imagem oficial do Docker CLI](https://hub.docker.com/_/docker).
