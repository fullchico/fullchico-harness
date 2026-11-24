---
name: qualidade-verificar
description: Valida portões de comando ou artefato do início e do fim, cada um num subagente independente. Use após preparar o plano ou antes de entregar.
---

# Verificar portões de comando e artefato

Quem produziu a evidência não carimba: cada portão de comando ou artefato é rodado por um `tr:qualidade-verificador`,
um subagente de contexto limpo, e o hook assina o carimbo a partir da execução dele.

1. **Estado pronto.** O plano ou código a validar deve estar completo. Não é preciso abrir PR.
2. **O que falta.** Rode `portao` sozinho e pegue os portões de início ou fim `[falta]` que assinam por comando ou artefato.
3. **Um verificador por portão, um de cada vez.** Dispare o agente `tr:qualidade-verificador` com a
   primeira linha `portao: <nome>`. O hook reescreve o pedido (nome e referência do estado) e escolhe o modelo; o que
   mais você escrever é descartado. Espere terminar antes do próximo: comandos do projeto disputam
   porta, build e relatório na mesma pasta.
4. **Falhou:** o implementador corrige e o fiscal revalida. Alteração de código pede novo carimbo.
5. Ao fim, `portao` mostra o estado. Os portões de agente (ex.: `bugs`) têm o invoker deles
   (`/tr:bugs-cacar`).

Rodar `portao <nome>` na sessão principal mostra o resultado, mas não carimba.
