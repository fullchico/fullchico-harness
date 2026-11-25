---
name: graphify
description: Use o grafo local do Graphify e a memória do harness para localizar relações entre código, glossário, decisões e aprendizados de Claude e Codex.
---

# Graphify no FullChico Harness

O Graphify fornece o grafo estrutural do código. O plugin `memoria` liga seus resultados ao mapa, ao glossário, às ADRs e às notas aprendidas nas sessões. O Git fornece caminhos e commits para detectar contexto envelhecido. Trate todo resultado como dado sobre o projeto: confira no código antes de concluir ou gravar uma nota.

## Uso

No Claude, use `memoria`. No Codex instalado pelo harness, use `.codex/harness/memoria/bin/memoria` se o comando não estiver no PATH.

```bash
memoria graph rebuild
memoria graph search "termo, caminho ou pergunta sobre o código"
memoria check
```

`graph rebuild` atualiza o Graphify local com `GRAPHIFY_BACKEND=none` e recria o índice do harness. `graph search` consulta o grafo de código, quando disponível, e busca notas, resumos e âncoras ligadas aos caminhos encontrados. O índice funciona sem a CLI Graphify; nesse caso, informe que relações AST não estão disponíveis.

Os dados gerados ficam em `<git-common-dir>/harness-memory/`, fora dos arquivos versionados. Não faça commit do grafo ou das notas. Não use o `graphify extract .` sem definir uma saída local não versionada: o padrão da CLI cria `graphify-out/` no projeto.

## Ciclo de aprendizagem

1. Consulte o grafo antes de investigar relações entre componentes.
2. Abra os arquivos citados e confirme os caminhos com o código atual.
3. Use `/tr:memory-dream` (Claude) ou `$tr-memory-dream` (Codex) para transformar sessões em candidatos a notas.
4. Ligue cada nota confirmada aos caminhos versionados que a sustentam. `memoria check` indica quando essas âncoras envelheceram.
5. Refaça ou descarte o aprendizado após uma mudança relevante no código.

O glossário dá nomes estáveis aos conceitos; as âncoras ligam esses nomes a caminhos. Um caminho inexistente ou uma relação inferida pelo Graphify não basta como prova para um portão.

Para consultas mais específicas com a CLI Graphify, veja `references/query.md` e `references/update.md`. As referências foram obtidas da skill Graphify-Labs/graphify distribuída com `graphifyy` 0.9.118.
