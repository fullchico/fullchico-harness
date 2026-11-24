---
name: grill-me
description: Entrevista o dono para decidir a configuração do harness, os trilhos e os portões com base no diagnóstico dos ambientes e nas evidências do projeto.
---

# Entrevistar para configurar o projeto

Esta skill inclui o fluxo `grilling` de Matt Pocock (versão 1.3.1, licença MIT;
veja `../../THIRD_PARTY_NOTICES.md`) adaptado para a configuração do FullChico Harness.
Use-a dentro de `/tr:configurar`, depois de ler os diagnósticos e o projeto.

Mapeie as decisões como uma árvore: cada escolha abre as decisões que dependem dela.
Pergunte em rodadas. Em cada rodada, apresente somente as perguntas cujas premissas já
estão resolvidas. Numere as perguntas, dê uma recomendação concreta para cada uma e
espere as respostas do dono antes de avançar. Recalcule a próxima rodada com base nas
respostas. Formule cada pergunta de modo que “sim” aceite sua recomendação.

Descobrir fatos é trabalho seu: confira arquivos, comandos e diagnósticos antes de
perguntar. Pergunte ao dono apenas por decisões, por exemplo o nível de rigor no envio,
quais verificações são obrigatórias e quais são opcionais por tipo de entrega.

Para cada portão proposto, mostre a evidência, o momento (`inicio` ou `fim`), o modo de
assinatura (`comando`, `artefato` ou `agente`) e o comando, caminho ou agente exato.
Se não houver evidência para um comando, não invente: deixe a decisão aberta.

Termine quando não houver decisão pendente. Resuma o acordo e peça ao dono que confirme
que o entendimento está correto antes de preparar o esboço do registro.
