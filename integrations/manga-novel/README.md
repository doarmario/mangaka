# Integração local

Fonte preservada: https://github.com/Raby012/-manga-novel-api
Commit: 2e72a110bea5f3327a856a0c7e00233291e5566b

O Dockerfile usa o contexto adicional `upstream` definido no Compose.
`server.ts` ativa o roteador original de múltiplas fontes. `asuraScraper.ts`
substitui o adaptador desatualizado e `imageProxy.ts` deriva do proxy original,
adicionando o CDN atual do Asura. Nenhuma alteração é escrita no checkout original.

`contract.test.cjs` testa os dados serializados do Astro, URLs de busca e os
estados de acesso do leitor, sem chamadas externas. Esses testes rodam no build.
