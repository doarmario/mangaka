# Atualizações automáticas (Linux com systemd)

Em uma instalação já funcionando, execute como o usuário que tem acesso ao Docker:

```bash
bash scripts/enable-auto-update.sh
```

O agendamento verifica a branch remota acompanhada pela branch atual a cada cinco
minutos. A primeira execução também implanta o commit atual. Não há webhook nem
porta adicional. O computador precisa estar ligado e conectado à internet.
Para executar mesmo sem uma sessão aberta, habilite uma vez:

```bash
sudo loginctl enable-linger "$USER"
```

Use uma instalação sem modificações locais. Commits locais ainda não enviados,
históricos divergentes e arquivos não commitados bloqueiam a atualização.
Configurações pessoais devem ficar no `.env`, que é preservado junto com os
volumes. Em repositórios privados, o usuário do serviço precisa ter acesso Git
sem prompts interativos. Mudanças só locais não são publicadas por este sistema.

O processo baixa commits, avança apenas por fast-forward e constrói as imagens
antes de parar o site e o worker. Em seguida, salva um dump MySQL, aplica as
migrações e sobe os serviços com verificação de saúde do Compose. Há uma breve
indisponibilidade durante o backup, migração e reinício. O código externo da API
Asura não recebe `git pull` automático; permanece na versão instalada.

O commit só é marcado como implantado após o sucesso; falhas são tentadas novamente
no próximo ciclo. Falhas após a parada podem deixar o site parado. Consulte os
logs e corrija a causa antes de reiniciar. Não há rollback automático, pois uma
migração pode alterar dados de forma incompatível com o código antigo.

Backups ficam em `.git/mangaka-update/backups/`, com acesso restrito ao usuário.
Não são apagados automaticamente: acompanhe o espaço em disco e copie backups
para outro local. Excluir a instalação também exclui esses backups.

```bash
# Estado e logs
systemctl --user list-timers mangaka-update.timer
journalctl --user -u mangaka-update.service -n 100
# Executar agora
systemctl --user start mangaka-update.service
# Desativar próximas atualizações (não interrompe uma em andamento)
systemctl --user disable --now mangaka-update.timer
```
