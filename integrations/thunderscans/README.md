# Thunder Scans para Mangaka

Wrapper das páginas públicas de https://en-thunderscans.com/, incluído no projeto.
O transporte HTTP e o parser MangaReader foram adaptados da integração Qi Scans
(`77c5bfde9305db12f85bc7d818765d08d65f7ea9`), com licença MIT preservada em `LICENSE`.
Não exige checkout externo, conta na fonte ou execução de JavaScript.

- Catálogo: `/comics/?page=N&order=update`.
- Busca: `/?s=texto` e `/page/N/?s=texto`.
- Tags: filtros `genre[]` do catálogo.
- Detalhes e capítulos: `/comics/<slug>/`.
- Leitura: dados JSON públicos de `ts_reader.run(...)`, sem executar o script.

Cada consulta carrega somente a página solicitada. A resposta informa `has_next`,
sem inventar o total do catálogo. Busca combinada com tag aplica os termos ao
título de cada item na página do gênero; pode haver páginas vazias com uma
próxima página disponível. Não consulta os detalhes de cada resultado.

Capítulos são identificados como inglês. Entradas explicitamente bloqueadas são
omitidas, e o leitor rejeita conteúdo protegido ou novels. Antes de obter imagens,
valida tanto a associação do capítulo à obra quanto o link da obra no leitor.
Somente o servidor selecionado em `defaultSource` fornece a lista de imagens.

A API segue o contrato interno `/api/manga/catalog`, `/api/manga/search`,
`/api/manga/tags`, `/api/manga/<id>`, `/api/manga/<id>/chapters`,
`/api/manga/<id>/chapters/<chapter>/pages`, `/api/proxy/image` e `/api/health`.
Use `source=thunderscans` quando informar a fonte. O healthcheck testa o serviço
local, sem gerar consultas externas.

Há cache de até 256 entradas em memória, TTL de 15 minutos (páginas: 10 minutos;
tags: 24 horas), além do Redis do Mangaka. O transporte limita tamanho, timeout e
redirecionamentos, valida os hosts e os tipos de imagem e respeita `Retry-After`.
Bloqueios ou mudanças na estrutura resultam em erro controlado de indisponibilidade.

## Testes

```sh
python -m pip install '.[test]'
python -m pytest -q
```

Os testes usam HTML sintético e não acessam a internet. Também rodam durante o
build Docker, antes de produzir a imagem final sem root na porta interna 3004.
