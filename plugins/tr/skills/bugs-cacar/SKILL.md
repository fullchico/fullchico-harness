---
name: bugs-cacar
description: Caça bugs no trabalho concluído, num subagente independente que carimba o estado atual. Use antes da entrega.
---

# Caçar bugs

O portão `bugs` é assinado pelo veredito do agente `tr:bugs-cacador`. Você não assina nada e não
escreve o pedido dele: o hook do trilho escreve o snapshot, para o caçador começar sem o
contexto de quem escreveu o código. Sem Git, ele inspeciona os arquivos atuais.

1. **Estado pronto.** O implementador terminou o código a validar; não é preciso abrir PR.
2. **Dispare o agente `tr:bugs-cacador`.** Qualquer pedido curto serve; o hook troca pelo canônico.
3. **O veredito** vem em três linhas (`VEREDITO`, `COMMIT`, `RESUMO`).
   - `APPROVED`: o hook carimba o estado atual.
   - `REJECTED`: o implementador corrige, e outro exame valida o novo estado.

O caçador valida só defeitos no diff; os portões de comando são do `/tr:qualidade-verificar`.
