---
name: aprender
description: Fecha o ciclo depois do merge de uma entrega. Atualiza o mapa, mede o consumo por papel, faz a retrospectiva da entrega e consolida as notas das sessões.
disable-model-invocation: true
---

# Aprender com a entrega

Rode depois de o pull request ter sido mesclado. São quatro coisas, nesta ordem.

## 1. Atualizar

Rode `.harness/fetch` e traga a branch padrão do remoto para onde você está, com
`git merge origin/<branch padrão>`. Depois use a skill `mapear`: ela refaz só o que a
entrega mudou no mapa, e relata termos do glossário e decisões de arquitetura a rever.

## 2. Medir

```bash
.harness/learn usage
```

A tabela mostra, para as sessões ainda não processadas, os tokens de cada papel: a sessão
principal e cada tipo de subagente, por modelo. Leve ao relato:

- o total, e a parte de cada papel;
- o que destoa: um papel barato gastando como um caro, muito token de entrada sem cache,
  um implementador que consumiu várias vezes mais que os outros.

Não tire conclusão de um número só. Uma entrega é uma amostra.

## 3. Retrospectiva

O assunto é o ambiente em que o agente trabalhou, não o agente. Leia o resumo das sessões da
entrega (`.harness/learn sessions`, depois `.harness/learn digest <id> .harness-run/dream/<id>.md`)
e procure:

- **Onde se perdeu tempo para achar algo.** Um ponteiro no mapa ou no `AGENTS.md` teria evitado?
- **Que erro uma checagem automática pegaria.** O que dá para checar por máquina vira
  proposta de checagem (lint, teste, validação), não de texto.
- **Que regra faltou,** e fez um revisor reprovar algo que o implementador não tinha como saber.
- **Que instrução não mudou nada,** e só ocupa espaço.
- **Que comando foi negado** pelo sandbox ou por um guard, e se a negação estava certa.
- **Onde a spec ou os tickets falharam,** e um implementador teve de parar por lacuna.

Grave as propostas em `.harness-run/propostas/<data>-<assunto>.md`, cada uma com o que
aconteceu, a evidência, e a mudança sugerida. Diga se a mudança é do projeto (o `harness.conf`,
a parte do projeto no `AGENTS.md`, uma checagem do próprio projeto) ou do harness.

O que é do harness não se altera aqui. O dono leva a proposta ao repositório do harness,
decide, publica uma versão, e todos os projetos recebem pela atualização.

## 4. Consolidar

Use a skill `dream`. Ela transforma o que as sessões ensinaram sobre o projeto em notas
ancoradas no código, e marca as sessões como processadas.

## Relatar

Diga ao dono: o que mudou no mapa, a tabela de consumo com o que destoa, as propostas
gravadas e onde estão, e as notas novas.
