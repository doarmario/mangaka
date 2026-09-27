# Identidade e leitura independentes das fontes

O usuário acompanha uma **obra local**. MangaDex, Asura, Qi Scans, Demonic Scans
 e Thunder Scans fornecem metadados e páginas; não são a autoridade da identidade.
Nenhuma imagem passa a ser armazenada permanentemente por esta implementação.

## Estruturas e compatibilidade

- `work`: UUID local, título canônico, descrição e metadados opcionais
  (autor/artista, tipo, ano, país, edição). Não depende de IDs externos.
- `work_alias`: títulos alternativos, normalização e origem. O mesmo alias pode
  pertencer a obras distintas. Hash SHA-256 indexado evita que a collation do
  MySQL confunda acentos/caracteres que o normalizador preserva.
- `work_external_id`: sinais opcionais de identidade (MangaDex, AniList,
  MyAnimeList, MangaUpdates); únicos por provider + ID. Não consulta esses
  serviços nem depende de sua disponibilidade.
- `source_work`: mapeia o UUID de compatibilidade/ID remoto de um provider para
  `work`. Mantém título na fonte, URL opcional, disponibilidade e timestamps.
- `logical_chapter`: pertence à obra, tem chave textual, número decimal opcional,
  volume, título e rótulo. Único por obra + hash da chave.
- `source_chapter`: mapeia o capítulo de provider para o capítulo lógico e guarda
  idioma, número original, disponibilidade e timestamps. IDs remotos extensos
  ficam em TEXT; a unicidade usa obra de fonte + hash do ID remoto.
- `reading_progress`: único por usuário + obra; capítulo lógico, página (base 1),
  quantidade, fração entre 0 e 1, timestamps, status e último provider/ID local
  do capítulo como auxiliares. Capítulo pode ser nulo em “Quero ler”.
- `favorite` continua sendo a tabela de favoritos, agora com `work_id`.
  `readed` continua sendo o histórico por usuário/capítulo de origem e passa a
  guardar também obra, capítulo lógico, página, fração e conclusão. Consultas de
  lidos usam o capítulo lógico; leituras parciais não são marcadas como concluídas.
- `update_notification` ganha referências canônicas, preservando os campos
  antigos para notificações já emitidas.

`manga`, `chapter`, `source_reference`, seus IDs e todas as rotas antigas são
preservados. Escritas de leitura/favorito mantêm as relações antigas, necessárias
para compatibilidade e auditoria. Linhas antigas de favoritos duplicadas entre
fontes são preservadas, mas aparecem uma vez por obra na biblioteca. Remover um
favorito remove as associações daquele usuário à mesma obra.

Não existe um log de cada movimento de página: `readed` mantém o último estado
por usuário/capítulo de fonte, incluindo primeira/última leitura, como no modelo
anterior. O histórico de uma fonte não é apagado ao usar outra.

## Normalização e matching

`app/libs/identity.py` centraliza NFKC, casefold, trim, compactação de espaços e
substituição de pontuação por espaços. Preserva acentos, letras não latinas,
números e símbolos significativos como `+`. Não remove “2”, “Remake”, “Ragnarok”
ou “Side Story”.

`app/libs/canonical.py` resolve IDs externos conhecidos e mapeamentos já
persistidos antes de procurar títulos/aliases exatos. IDs externos conflitantes
não movem silenciosamente um mapeamento existente. Autor, artista, tipo, país,
ano ou edição explicitamente divergentes vetam matching por título.

Um único candidato exato e compatível recebe confiança 1.0. Mais de um candidato
ou dois IDs distintos do mesmo provider com o mesmo título permanecem separados,
salvo evidência explícita de ID externo. A descoberta em lote verifica a ambiguidade
antes de resolver cada item. Aliases novos podem consolidar obras previamente
separadas; os históricos são remapeados, o progresso mais recente é mantido e o
ID canônico antigo continua funcionando como redirecionamento local.

Fuzzy usa `SequenceMatcher`, somente como sugestão: score >= 0.85 e limitado a
0.94. Nunca autoriza associação automática, mesmo com score alto. Sugestões de
uma obra nova ficam em `metadata_json.match_candidates`; a busca é limitada a
100 títulos com o primeiro token em comum e retorna até cinco candidatos.
Não há interface de revisão manual de candidatos nesta etapa.

Homônimos com metadados ausentes não podem ser distinguidos com certeza.
Traduções sem aliases ou IDs em comum podem continuar separadas. A descoberta
consulta uma página por provider e mantém os caches existentes; não varre a web.

## Capítulos e páginas

`parse_chapter`, `chapter_order` e `chapter_identity` são funções compartilhadas.
`12`, `12.1`, `12.5`, `12.5.1`, `0`, `Prologue`, `Extra`, `Side Story 3` e
`Epilogue` são aceitos. Decimal é usado sem conversão para float. Números que não
cabem exatamente em NUMERIC(24,8) continuam preservados na chave textual.

Ordem crescente: desconhecidos, prólogo, números/decimais/subdivisões, especiais
com ordenação natural, epílogo. A listagem exibe a ordem inversa. Volume faz parte
da identidade quando fornecido. Fontes com volume ausente e volume explícito não
são equiparadas automaticamente, pois a numeração pode reiniciar a cada volume.

Um `Extra` genérico sem título distinto mantém uma chave específica do registro
original; não é prova de equivalência com outro extra. Números repetidos no mesmo
idioma de uma mesma fonte também não autorizam equivalência automática. Idiomas
diferentes podem apontar para o mesmo capítulo lógico; suas páginas continuam
separadas e o resolver prefere o idioma usado anteriormente.

O leitor autenticado envia progresso por POST com CSRF e debounce; página e
percentual ficam no banco. Preferências de exibição e fallback anônimo continuam
no armazenamento local. O progresso antigo que existia **somente no navegador**
não está disponível à migração do banco.

## Continuar lendo e disponibilidade

`resolve_source_for_chapter` busca o progresso por usuário/obra e tenta:

1. Última fonte disponível com o capítulo;
2. providers configurados em `SOURCE_PRIORITY` (lista na configuração Flask),
   usando a ordem de fontes habilitadas como padrão;
3. demais fontes habilitadas que possuam o mesmo capítulo lógico;
4. fontes antes indisponíveis, para permitir recuperação.

Não existe preferência de provider por usuário no modelo anterior. A prioridade
é centralizada no backend; o frontend abre `/work/<id>/continue`.

Uma fonte removida da configuração não é consultada. Falhas/ausências marcam
mapeamentos indisponíveis e nunca apagam progresso. Sincronização completa marca
capítulos desaparecidos como indisponíveis; uma atualização parcial não faz isso.
Reencontrar o item restaura sua disponibilidade.

Na mesma fonte, a página é retomada diretamente. Em outra, aplica-se
`floor(fração * total_de_páginas)`, limitada a [1, total]. Assim 32/42 vira 43/57.
É uma aproximação: o capítulo é a unidade confiável. Sem equivalente, a resposta
503 informa que o progresso foi preservado; não escolhe arbitrariamente um capítulo
vizinho. Páginas são buscadas pelo adaptador/cache existente, sem download permanente.

## Rotas e interface

- `/work/<id>`: página canônica, fontes, estado, progresso e status da biblioteca.
- `/work/<id>/continue`: resolve provider e redireciona ao leitor existente.
- `POST /cap/<id>/progress`: `{page, page_count}`, autenticado e protegido por CSRF.
- `POST /work/<id>/status`: `reading`, `plan_to_read`, `completed`, `paused`, `dropped`.
- `/api/works/<id>`: ID canônico, título, aliases, fontes e progresso apenas do
  usuário autenticado. `Cache-Control: private, no-store`.

As rotas `/manga/<id>`, `/cap/<id>`, favoritos e `/readed` mantêm seus contratos.
Respostas internas de adaptadores ganham campos aditivos; os scrapers existentes
não precisam adotar um protocolo novo. Os cards multifonte e a biblioteca passam
a usar as URLs canônicas. Detalhes específicos de provider continuam acessíveis.

## Migração, concorrência e operação

A revisão `20260928_canonical_reading`, após `20260924_unique_notifications`, adiciona
as tabelas/colunas e popula obras, favoritos, histórico, progresso e notificações.
Ela aceita bancos antigos e bancos em que `init-db` já criou as tabelas novas.
Não faz consultas HTTP e não remove registros antigos. Faça backup antes de uma
atualização, como descrito em [self-hosting.md](self-hosting.md).

O instalador e o auto-updater já executam `flask --app app db upgrade` antes de
iniciar o novo código. Em atualização manual, use o mesmo comando. Não basta
`create_all` para adicionar colunas a tabelas existentes.

Capítulos MangaDex antigos só tinham UUID, sem número no banco. A migração cria
uma identidade provisória específica, preserva o histórico e a enriquece quando
seus metadados forem consultados. Se a fonte sumir antes desse enriquecimento,
não é possível deduzir o capítulo correto; a aplicação mantém os dados e informa
a falta de equivalente. Metadados presentes em `source_reference` são reaproveitados.

O downgrade é **não destrutivo**: recua o marcador Alembic e conserva as estruturas
aditivas. A aplicação anterior pode ignorá-las; uma nova aplicação da migração é
idempotente. Não significa converter progresso novo em um formato antigo com a
mesma precisão. O helper `backfill` é parte do contrato da migração; mudanças nele
precisam manter os testes de upgrade/reaplicação sobre banco legado.

`catalog_lock` serializa decisões curtas de identidade e progresso no banco.
Um upsert atômico evita deadlock na criação inicial. HTTP ocorre fora desse lock.
MySQL usa READ COMMITTED para observar a identidade gravada pelo concorrente após
esperar; constraints protegem IDs externos, source works, source chapters,
aliases por obra e progresso por usuário/obra. O lock global favorece integridade
para instalações locais; não é uma arquitetura de ingestão massiva distribuída.

Testes usam SQLite e um MySQL 8.4 descartável (`canonical_test`), incluindo quatro
sincronizações simultâneas, migração de dados antigos, reaplicação, aliases,
falsos positivos e fallback de leitura entre providers. Para rodar o teste MySQL,
defina `MANGAKA_TEST_MYSQL_URL` para um banco **descartável** chamado `canonical_test`;
esses testes criam e removem tabelas somente nesse banco.

## Novas integrações

Continuam entregando `id`, `title`, `aliases` opcionais, `autor`/`author`, `artist`,
`ano`/`year`, `type`, `country`, `edition`, `external_ids` opcionais e `source_url`.
Capítulos usam `cap_id`, `cap` textual, `volume`, `title`, `language` e URL opcional.
O adaptador `Library` resolve identidade após receber os dados; não replique matching
nem normalização nos scrapers. Não invente metadados ausentes para forçar associações.
