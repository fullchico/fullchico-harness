---
name: qualidade-verificar
description: Valida os portões de comando de fim do projeto (qualidade, e2e, seo...), cada um num subagente limpo que carimba o commit. Use depois do commit e antes de enviar, ou quando o envio foi barrado apontando /tr:qualidade-verificar.
---

# Verificar os portões de comando

Quem escreveu o código não carimba: cada portão de comando é rodado por um `tr:qualidade-verificador`,
um subagente de contexto limpo, e o hook assina o carimbo a partir da execução dele.

1. **Árvore limpa.** `git status --porcelain` sem saída. Alteração sem commit: faça o commit antes (o
   disparo é barrado com a árvore suja).
2. **O que falta.** Rode `portao` sozinho e pegue os portões de fim `[falta]` que assinam por comando.
3. **Um verificador por portão, um de cada vez.** Dispare o agente `tr:qualidade-verificador` com a
   primeira linha `portao: <nome>`. O hook reescreve o pedido (nome e commit) e escolhe o modelo; o que
   mais você escrever é descartado. Espere terminar antes do próximo: comandos do projeto disputam
   porta, build e relatório na mesma pasta.
4. **Falhou:** corrija (você, ou o implementador), faça o commit e rode este passo a passo de novo. O
   carimbo é do commit: commit novo pede os portões de novo.
5. Ao fim, `portao` mostra o estado. Os portões de agente (ex.: `bugs`) têm o invoker deles
   (`/tr:bugs-cacar`).

Rodar `portao <nome>` na sessão principal mostra o resultado, mas não carimba.
