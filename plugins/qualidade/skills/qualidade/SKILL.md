---
name: qualidade
description: Roda a checagem de qualidade do projeto (lint, testes) e carimba o commit. Use antes de enviar, depois de cada commit que importa, ou quando o envio foi barrado pelo plugin qualidade.
---

# Qualidade

O envio (`git push`, `gh pr create`) é barrado enquanto o commit do topo não tem o carimbo `qualidade`.

## Configurar (uma vez, no projeto)

O comando da checagem é do projeto, em `.claude/trilho.json`:

```json
{"qualidade": {"comando": "pnpm lint && pnpm test"}}
```

Sem essa chave, `qualidade-check` explica como configurar e não carimba.

## Rodar

1. Faça o commit de tudo: a árvore precisa estar limpa, senão o carimbo mentiria sobre o commit.
2. Rode `qualidade-check`, sozinho na chamada (sem `&&`, sem argumentos).
3. A última linha diz `qualidade: passou` ou `qualidade: FALHOU (<comando>)`. Passou: o hook carimba o
   commit. Falhou: corrija, faça o commit e rode de novo.

O carimbo é do commit: commit novo pede nova checagem. Ele fica fora do repositório
(`~/.claude/trilho/<id>/stamps/qualidade/<sha>.json`) e só o hook grava.
