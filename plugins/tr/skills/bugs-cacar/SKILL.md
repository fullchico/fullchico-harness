---
name: bugs-cacar
description: Caça bugs no que a branch mudou, num subagente limpo que carimba o commit. Use depois do commit e antes de enviar, ou quando o envio foi barrado apontando /tr:bugs-cacar.
---

# Caçar bugs

O portão `bugs` é assinado pelo veredito do agente `tr:bugs-cacador`. Você não assina nada e não
escreve o pedido dele: o hook do trilho escreve (base, topo e commit), para o caçador começar sem o
contexto de quem escreveu o código.

1. **Árvore limpa.** `git status --porcelain` sem saída; senão, faça o commit (o disparo é barrado com
   a árvore suja).
2. **Dispare o agente `tr:bugs-cacador`.** Qualquer pedido curto serve; o hook troca pelo canônico.
3. **O veredito** vem em três linhas (`VEREDITO`, `COMMIT`, `RESUMO`).
   - `APPROVED`: o hook carimba o commit. Confira as observações e decida o que vale corrigir depois.
   - `REJECTED`: corrija o que ele apontou (com o teste que pegaria o defeito), faça o commit e cace de
     novo. Commit novo pede caça nova.

O caçador valida só defeitos no diff; os portões de comando são do `/tr:qualidade-verificar`.
