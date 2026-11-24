---
name: memory-aprender
description: Fecha o ciclo depois do merge de uma entrega. Atualiza o mapa, mede o consumo por papel, faz a retrospectiva da entrega e consolida as notas das sessões.
disable-model-invocation: true
---

# Aprender com a entrega

Rode depois de o pull request ter sido mesclado. São quatro coisas, nesta ordem. Espere os
subagentes de cada passo terminarem antes de seguir para o próximo.

## 1. Atualizar

Traga a branch padrão atualizada. Depois use a skill `/tr:memory-mapear`: ela refaz só o que a
entrega mudou no mapa, e relata termos do glossário e decisões de arquitetura a rever.

## 2. Retrospectiva

O assunto é o ambiente em que o agente trabalhou, não o agente. Leia o resumo das sessões da
entrega (`memoria-sessoes sessions`, depois `memoria-sessoes digest <id> .harness-run/dream/<id>.md`)
e procure:

- **Onde se perdeu tempo para achar algo.** Um ponteiro no mapa ou no `AGENTS.md` teria evitado?
- **Que erro uma checagem automática pegaria.** O que dá para checar por máquina vira
  proposta de checagem (lint, teste, validação), não de texto.
- **Que regra faltou,** e fez um revisor reprovar algo que o implementador não tinha como saber.
- **Que instrução não mudou nada,** e só ocupa espaço.
- **Que comando foi negado** pelo sandbox ou por um guard, e se a negação estava certa.
- **Onde a spec ou os tickets falharam,** e um implementador teve de parar por lacuna.

Escreva cada proposta num arquivo em `.harness-run/`, com o que aconteceu, a evidência e a
mudança sugerida, e guarde com `memoria-sessoes propose <assunto> <arquivo>`. O comando grava
no repositório, fora do worktree: a proposta continua lá depois que o worktree da feature for
removido. `memoria-sessoes proposals` lista as guardadas. Diga se a mudança é do projeto (o `AGENTS.md`,
uma checagem do próprio projeto) ou de um plugin.

O que é de plugin não se altera aqui. O dono leva a proposta ao repositório do plugin,
decide, publica uma versão, e todos os projetos recebem pela atualização.

## 3. Medir

Meça depois do mapa e da retrospectiva, com os subagentes deles já terminados: medir antes
deixa de fora o custo do próprio ciclo.

```bash
memoria-sessoes usage
```

A tabela mostra, para as sessões ainda não processadas, os tokens de cada papel: a sessão
principal e cada tipo de subagente, por modelo. A primeira coluna é o começo do id da sessão,
que os outros comandos do `learn` aceitam. Leve ao relato:

- o total, e a parte de cada papel;
- o que destoa: um papel barato gastando como um caro, muito token de entrada sem cache,
  um implementador que consumiu várias vezes mais que os outros.

Não tire conclusão de um número só. Uma entrega é uma amostra.

## 4. Consolidar

Use a skill `/tr:memory-dream`. Ela transforma o que as sessões ensinaram sobre o projeto em notas
ancoradas no código, e marca as sessões como processadas.

## Relatar

Diga ao dono: o que mudou no mapa, a tabela de consumo com o que destoa, as propostas
gravadas e onde estão, e as notas novas.
