# Mangaka Project

## Instalar e começar a ler

Com o Docker funcionando e este repositório clonado, abra um terminal na pasta
`mangaka` e execute apenas:

```bash
docker compose -f compose.install.yaml run --build --rm installer
```

Funciona no Linux e no PowerShell do Windows com Docker Desktop no modo de
containers Linux. O instalador gera as senhas, baixa a API adicional, prepara o
banco e inicia o site com atualização automática. Não é necessário criar `.env`
nem clonar outra API manualmente. A primeira instalação pode levar alguns minutos.
Ao terminar, abra **http://localhost:5000** e crie sua conta.

Mantenha o Docker funcionando para ler e receber atualizações. Para mais detalhes,
consulte o [guia de instalação](docs/self-hosting.md).

**Aviso Legal:** Este projeto é um trabalho educacional e de estudo, criado com o propósito de demonstrar habilidades técnicas e de desenvolvimento web.

O Mangaka Project **não hospeda, distribui ou promove conteúdo protegido por direitos autorais** (como mangás completos, scans ou materiais piratas).

Este repositório contém apenas o código-fonte de um site que consome dados de uma API pública para fins de aprendizado. O uso do código é **responsabilidade do usuário** e deve ser feito de acordo com as leis de direitos autorais e as permissões das APIs utilizadas.

Qualquer uso deste código para fins ilegais ou para distribuição de conteúdo protegido é de **responsabilidade exclusiva do usuário que o fizer**.

---

## Sobre o Projeto

O Mangaka Project é uma iniciativa para desenvolvimento de um site de mangás baseado em APIs públicas, focado em aprendizado, prototipagem e demonstração técnica.

Este projeto **não disponibiliza nenhum conteúdo protegido diretamente** e é destinado ao uso **pessoal, educativo e de portfólio**.

---

## Aviso de Responsabilidade

Este projeto foi criado para fins educacionais e técnicos. O uso do código para **distribuir conteúdo protegido por direitos autorais** sem a devida permissão **não é permitido**. A responsabilidade por quaisquer ações legais decorrentes de **violação de direitos autorais** é exclusivamente do usuário que utilizar o código de maneira imprópria.

Por favor, **respeite os direitos autorais dos criadores de conteúdo** e **não hospede, distribua ou acesse mangás ou outros materiais protegidos sem a devida autorização**.

---

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

## Contato

Para dúvidas ou sugestões, abra uma issue ou entre em contato.

## Configuração manual com Docker (opcional)

O projeto inclui MySQL, Redis e o servidor web em `compose.yaml`. Se o `.env`
ainda não existir, copie `.env.example` para `.env` e substitua as três
chaves/senhas por valores aleatórios. O `.env` não é versionado nem copiado
para a imagem Docker.

```bash
docker compose up -d --build
docker compose ps
```

Se o Docker exigir permissão administrativa na sua máquina, use `sudo` antes
desses comandos. Abra **http://localhost:5000** quando o serviço `web` estiver
saudável. Você pode criar sua conta pela página de cadastro.

O serviço `init-db` aguarda o MySQL e o Redis e cria as tabelas ausentes antes de
iniciar o site. Ele termina com código 0; isso é normal. Esse comando não apaga
dados nem substitui migrações para alterações futuras no esquema.

```bash
# Acompanhar inicialização ou erros
docker compose logs --tail=100 web init-db mysql redis
# Parar preservando banco, cache e sessões
docker compose down
# Retomar
docker compose up -d
```

Os dados ficam em volumes persistentes. Não use `down -v` se quiser preservá-los.
MySQL e Redis ficam acessíveis apenas na rede interna do Compose; o site é
publicado apenas no endereço local. Para mudar a porta, ajuste `MANGAKA_PORT`
no `.env`. As senhas do MySQL no `.env` são aplicadas na primeira inicialização
do volume; alterá-las depois exige também atualizar as credenciais no banco.

Para acessar pelo celular ou tablet na mesma rede, descubra o IP do computador
(`hostname -I` no Linux), ajuste `MANGAKA_BIND_ADDRESS=0.0.0.0` no `.env` e
reinicie o site. Abra `http://IP_DO_COMPUTADOR:5000` no outro dispositivo.
Consulte [docs/self-hosting.md](docs/self-hosting.md) para instalação em uma
máquina nova, atualização, backup e publicação atrás de HTTPS.

Para atualizar automaticamente a instalação a partir de novos commits, consulte
[Atualizações automáticas](docs/auto-update.md). O serviço opcional roda no Docker,
inclusive no Docker Desktop do Windows, sem agendamento no sistema operacional.

## Testes da integração MangaDex

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

A suíte usa a biblioteca MangaDex real com respostas HTTP simuladas e bloqueia
requisições externas inesperadas. Banco SQLite em memória e cache em memória são
usados **somente nos testes**; a configuração normal continua usando MySQL e Redis.
O workflow do GitHub Actions executa os testes em Python 3.13.

O fork `doarmario/mangadex` está fixado por commit em `requirements.txt` (o nome da
distribuição no `pyproject.toml` do fork é `md`; o módulo importado é `mangadex`).
Ao atualizá-lo, rode os testes de contrato antes de trocar o commit. A listagem do
fork retorna apenas objetos e descarta `total`: o adaptador usa o transporte e o
parser da biblioteca separadamente para preservar a paginação da resposta.

### Cache e requisições

- As chaves `mangadex_v3_` incluem página, idioma, tamanho de página e filtros.
  Entradas antigas expiram normalmente, sem necessidade de limpar o Redis.
- Listas e capítulos: 15 minutos; metadados e capas: 1 hora; autores e tags: 24 horas.
- URLs temporárias das páginas: 10 minutos, separadas dos metadados do capítulo.
- As listagens alimentam o cache de metadados, evitando consultar novamente cada
  mangá ao abrir seus detalhes ou buscar sua capa.
- Dados compartilhados são dicionários/listas; favoritos e marcações de leitura
  são consultados por usuário e não entram no cache compartilhado.
- Após HTTP 429, uma pausa compartilhada respeita `Retry-After` numérico (60 segundos
  na ausência de valor válido). Consultas já em cache continuam disponíveis; novas
  consultas recebem indisponibilidade temporária, sem tentativas automáticas.

Cache reduz requisições, mas não garante sozinho o limite em acessos simultâneos:
misses concorrentes ainda podem gerar chamadas repetidas. Os testes não validam
um servidor Redis real nem a disponibilidade atual da API; cobrem contratos da
biblioteca, paginação, navegação, falhas HTTP e reaproveitamento do cache.

## Idiomas

O catálogo, a busca e as atualizações incluem português brasileiro (`pt-br`),
português de Portugal (`pt`) e inglês (`en`). Títulos e descrições priorizam
português, depois inglês; quando não há tradução, o título original continua
sendo exibido. Isso não traduz automaticamente as páginas dos mangás.

Na página do mangá, cada capítulo indica seu idioma e o seletor permite filtrar
as traduções. “Começar a ler” prioriza português e usa inglês quando não há
capítulos em português. Ao selecionar um idioma, o botão acompanha essa seleção.
No leitor, anterior/próximo mantêm o idioma do capítulo aberto.

Os capítulos são consultados e armazenados no Redis separadamente por idioma,
porque o endpoint de agregação do MangaDex não identifica o idioma de cada item.
Números iguais em traduções diferentes continuam disponíveis, sem misturar
as marcações de leitura.

## Fontes adicionais: Manga Novel API

O catálogo agora permite escolher **MangaDex** ou **AsuraScans**. Ao aplicar uma fonte, o catálogo carrega seus títulos automaticamente; a escolha
da fonte acompanha a busca e a paginação. Detalhes e leitor mostram a procedência.
IDs locais próprios permitem usar favoritos e histórico sem confundir obras ou
capítulos de provedores diferentes. Não há fusão automática de obras por título.

A integração usa uma cópia local de
[Raby012/-manga-novel-api](https://github.com/Raby012/-manga-novel-api), commit
`2e72a110bea5f3327a856a0c7e00233291e5566b`. Para instalar em outra máquina:

```bash
git clone https://github.com/Raby012/-manga-novel-api.git ../manga-novel-api
git -C ../manga-novel-api checkout 2e72a110bea5f3327a856a0c7e00233291e5566b
docker compose up -d --build
```

O Compose lê o checkout em `../manga-novel-api`, configurável por
`MANGA_NOVEL_SOURCE_DIR` no `.env`, e inicia a API apenas na rede interna. O servidor
web usa `MANGA_NOVEL_API_URL=http://manga-novel:3001`. A inicialização do banco cria
apenas a nova tabela `source_reference`, preservando os dados existentes.

Nesta máquina, o código original está em `~/Work/manga-novel-api` e um backup Git
completo, verificado, está em `~/Work/manga-novel-api-backup.bundle`. O bundle pode
ser clonado sem acesso ao GitHub, por exemplo com
`git clone ~/Work/manga-novel-api-backup.bundle ~/Work/manga-novel-api-restaurada`.

As adaptações ficam em `integrations/manga-novel/`, sem modificar o checkout:

- O ponto de entrada monta as rotas de múltiplos provedores já presentes na API;
  o servidor original ignorava a escolha da fonte em várias operações.
- O adaptador Asura usa o domínio atual `asurascans.com` e os dados públicos das
  páginas; o endereço antigo redirecionava buscas para a página inicial.
- Capítulos marcados como premium, bloqueados ou ainda em acesso antecipado não
  são disponibilizados pelo adaptador.
- Os testes de contrato do adaptador Node rodam durante a construção da imagem.

O Redis guarda resultados por fonte, URL, página e idioma por 15 minutos e URLs
de páginas por 10 minutos. Falhas abrem uma pausa de 30 segundos para evitar
repetir consultas a um provedor indisponível. ComicK e WeebCentral não fazem
mais parte das fontes exibidas no catálogo.

O catálogo do MangaDex também permite filtrar a busca e a listagem por idioma
(português do Brasil, português de Portugal ou inglês) e status da obra. Esses
filtros permanecem ativos durante a paginação.

Usuários autenticados também têm as páginas **Minha biblioteca** e **Novidades**.
A área de novidades consulta os capítulos dos favoritos, usa o cache existente e
mostra apenas capítulos que ainda não foram marcados como lidos.
O serviço `updates-worker` verifica esses favoritos a cada 30 minutos e cria
notificações individuais; o intervalo pode ser ajustado com
`UPDATES_INTERVAL_SECONDS`.

Consumet **não está integrado**: seus repositórios oficiais estavam indisponíveis
quando consultados. É necessária uma instância ou documentação acessível para
validar essa integração. Novels também não fazem parte desta integração de mangás.

## Tags e gêneros

Nas páginas de mangás do MangaDex e do Asura, clique em uma tag (por exemplo,
**Isekai**, **Action** ou **Fantasy**) para abrir o catálogo dessa fonte filtrado
pelo gênero. A tag permanece na paginação e nas buscas por título. Use
**Remover filtro** para voltar ao catálogo da mesma fonte; ao aplicar outra fonte,
o filtro é reiniciado, pois os identificadores de gênero são específicos de cada
provedor.
