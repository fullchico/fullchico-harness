---
name: cacar
description: Caça bugs no que a branch mudou, antes de enviar. Use antes de `git push` ou `gh pr create`, depois de cada commit que importa, ou quando o envio foi barrado pelo plugin bugs.
---

# Caçar bugs

O envio (`git push`, `gh pr create`) é barrado enquanto o commit do topo não tem o carimbo `bugs`.
O carimbo é assinado por um hook quando o agente `bugs:cacador` aprova o commit. Você não assina nada.

## Passo a passo

1. **A árvore tem de estar limpa.** `git status --porcelain` sem saída. Alteração sem commit não é
   caçada: faça o commit antes.
2. **A base.** `git merge-base HEAD origin/<branch padrão>` (a padrão: `git symbolic-ref --short refs/remotes/origin/HEAD`
   sem o `origin/`). Sem remoto, use `main` ou `master` local, o que existir.
3. **O topo.** `git rev-parse HEAD`, o hash completo.
4. **Dispare o agente `bugs:cacador`** com exatamente duas linhas no pedido:

   ```
   diff: <base>...<topo>
   commit: <topo>
   ```

5. **O veredito** vem em três linhas (`VEREDITO`, `COMMIT`, `RESUMO`).
   - `APPROVED`: o hook carimba o commit. Pode enviar. Confira as observações e decida o que vale corrigir depois.
   - `REJECTED`: corrija o que ele apontou (com o teste que pegaria o defeito), faça o commit e cace de novo.
     O carimbo é do commit: commit novo pede caça nova.

Se o envio continuar barrado depois de `APPROVED`, o commit do topo mudou depois da caça, ou o hook
não aceitou o bloco: cace de novo sobre o `HEAD` atual.
