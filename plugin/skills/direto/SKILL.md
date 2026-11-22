---
name: direto
description: Libera a edição direta de código nesta sessão, sem passar pelo ciclo de entrega. Só o dono invoca, para ajuste pequeno.
disable-model-invocation: true
---

# Edição direta

O dono liberou, nesta sessão, a edição direta do código do aplicativo. A liberação nasce da
mensagem dele e vale só para esta sessão.

Pedido: $ARGUMENTS

- Faça só o que ele pediu, no menor diff. O que você notar fora disso vai para o relato, não
  para o código.
- Teste o que mudou e rode `.harness/validate` antes de dizer que terminou.
- Commit no formato do projeto. Commit `feat` continua pedindo spec no push: se o pedido é uma
  feature, diga isso ao dono e sugira `/harness:entregar`.
- Se a escrita for negada mesmo assim, a liberação não foi registrada: diga isso ao dono. Ela só
  nasce de uma mensagem dele que comece por `/harness:direto`.
