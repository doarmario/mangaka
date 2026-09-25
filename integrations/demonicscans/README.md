# Demonic Scans para Mangaka

Wrapper local das páginas públicas de https://demonicscans.org/, escrito para
este projeto. O transporte HTTP e o contrato foram adaptados da integração
Qi Scans (`77c5bfde9305db12f85bc7d818765d08d65f7ea9`), com sua licença MIT
preservada em `LICENSE`. Não depende de API pública ou checkout externo.

- Catálogo: `/advanced.php?list=N`; gêneros: `genre[]=ID`.
- Busca: `/search.php?manga=texto`, paginada localmente em grupos de 20.
- Metadados e capítulos: `/manga/<slug original>`.
- Leitor: `/chaptered.php?manga=ID&chapter=N`, somente imagens do capítulo.
- Idioma dos capítulos: inglês.

O catálogo mantém as páginas nativas, sem estimar um total. Busca com gênero
intersecta os resultados da busca com cada página do gênero, sem consultar os
detalhes de cada título. Uma página pode não ter correspondências e ainda ter
uma próxima página. Identificadores hexadecimais preservam a codificação original
dos slugs. Capítulos são validados contra a lista da obra antes de abrir o leitor.

A API interna segue `/api/manga/catalog`, `/api/manga/search`, `/api/manga/tags`,
`/api/manga/<id>`, `/api/manga/<id>/chapters`,
`/api/manga/<id>/chapters/<chapter>/pages`, `/api/proxy/image` e `/api/health`.
O parâmetro `source`, quando informado, deve ser `demonicscans`.

Cache em memória de até 256 entradas, TTL de 15 minutos (páginas: 10 minutos;
gêneros: 24 horas), além do cache Redis da aplicação. HTTP com timeout,
limites de tamanho e redirecionamentos, lista explícita de hosts, pausa ao receber
429 e validação do tipo de imagem. Não executa JavaScript nem contorna login,
pagamento ou desafios da fonte. Mudanças no HTML podem exigir ajustes no parser.

## Testes

```sh
python -m pip install '.[test]'
python -m pytest -q
```

Fixtures sintéticas, sem acesso à internet nos testes. O build Docker executa os
testes antes de gerar a imagem final, que roda sem root na porta interna 3003.
