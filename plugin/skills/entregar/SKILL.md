---
name: entregar
description: Conduz uma mudança da entrevista ao pull request, dentro do worktree de uma feature. Entrevista, spec, revisão da spec, tickets, implementação em paralelo, checagem, revisão e envio.
disable-model-invocation: true
---

# Entregar uma mudança

Você é o elefante: carrega o contexto, desenha com o dono, dispara o trabalho e monta o
resultado. Quem implementa e quem revisa são subagentes de contexto novo. Três regras
valem do começo ao fim:

1. **O documento é a única interface.** Todo pedido a um subagente só aponta arquivos, no
   formato fixo mostrado nas referências. Sem narrativa, sem opinião.
2. **Lacuna se corrige no documento.** Se um subagente não consegue trabalhar só com a
   spec e o ticket, corrija a spec ou o ticket, faça o commit, e peça de novo.
3. **Você não revisa o que orquestrou.** A revisão é dos revisores.

Siga os passos em ordem. Só pare nas duas paradas marcadas.

## 0. Antes de começar

- Confira que a sessão está num worktree de feature, numa branch que não é a padrão. Se
  estiver na branch padrão, pare e peça ao dono para abrir o worktree da feature.
- Rode `.harness/fetch`. Se a branch padrão do remoto andou, traga-a para dentro da feature
  com `git merge origin/<branch padrão>`, antes de qualquer outra coisa.
- Leia `GLOSSARY.md` e os ADRs em `docs/adr/`, se existirem.
- Rode `.harness/memory check`. Se o mapa da área que a mudança vai tocar está envelhecido ou
  não existe, atualize-o antes com a skill `mapear`.

## 1. Entrevistar

Com o dono, usando a skill `grilling`, até não sobrar decisão em aberto. Registre o
vocabulário e as decisões difíceis de reverter com a skill `domain-modeling`.

Se o pedido é um bug, use a skill `diagnosing-bugs` no lugar da entrevista. Bug não tem
spec nem tickets: corrija você mesmo, com teste, em commits `fix`, e vá para o passo 6. Se a
checagem ou um revisor reprovar, é você quem corrige, e a revisão recomeça; não há
implementador a despachar sem spec e ticket.

## 2. Especificar

Escreva a spec seguindo `references/spec.md` e faça o commit.

## 3. Revisar a spec

Dispare o `revisor-spec` com o pedido de `references/spec.md`. Apresente os achados ao dono.

**PARADA 1.** O dono resolve cada achado e aprova a spec. Ajuste a spec com o que ele
decidir, faça o commit, e só então siga.

## 4. Fatiar em tickets

Siga `references/tickets.md`. O grafo precisa passar no validador antes do próximo passo.

## 5. Implementar

Siga `references/despacho.md`: implementadores em paralelo, cada um num worktree de
agente, até a fronteira do grafo esvaziar.

## 6. Checar, revisar e enviar

Siga `references/fechamento.md`.

**PARADA 2, só se acontecer.** Se a entrega não fechar em 3 rodadas de correção, pare e
relate ao dono o que travou: o achado que se repete, o que foi tentado, e a sua leitura
do motivo.

## 7. Relatar

Diga ao dono: o link do pull request, o que entrou, o que ficou de fora, quantas rodadas
de correção houve, e qualquer coisa que os subagentes relataram fora do escopo.
