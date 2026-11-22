# qualidade

A checagem de qualidade do projeto (lint, testes) como carimbo. O comando é do projeto, em
`.claude/trilho.json`:

```json
{"qualidade": {"comando": "pnpm lint && pnpm test"}}
```

## Instalar só ele

```
npx @fullchico/harness add qualidade
```

ou, à mão: `claude plugin marketplace add FullChico/fullchico-harness` e
`claude plugin install qualidade@fullchico --scope project`.

## Como funciona

`qualidade-check` (no PATH da sessão) roda o comando na raiz do projeto e termina com
`qualidade: passou` ou `qualidade: FALHOU (<comando>)`. Ele não grava nada: quem carimba é um hook,
só quando o comando foi exatamente `qualidade-check`, terminou bem e a árvore está limpa. O carimbo
é do commit e fica em `~/.claude/trilho/<id>/stamps/qualidade/<sha>.json`.

## O que ele barra

`git push` e `gh pr create` quando o `HEAD` não tem o carimbo `qualidade`.
