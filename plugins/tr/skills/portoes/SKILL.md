---
name: portoes
description: Como trabalhar num projeto com portões (.claude/trilho.json). Use ao começar uma mudança, na validação da entrega ou para saber o que falta.
---

# Trabalhar com portões

Um portão é uma etapa obrigatória do fluxo do projeto. Os de **início** vêm antes de escrever código;
os de **fim** são verificados quando o modelo conclui a implementação. O carimbo (a prova) é gravado por um
hook, fora dos arquivos do projeto: você cumpre a etapa, não assina nada, e não altera o registro
(`.claude/trilho.json`), que é do dono.

## Passo a passo

1. **Veja o que falta.** Rode `portao` sozinho. Ele lista cada portão com `ok` ou `falta` e diz o
   que fazer em cada um.
2. **Comece pelos de início.** Antes de escrever em código do app, cumpra a etapa (por exemplo, a
   spec da mudança, saída da entrevista). Escrever sem ela é barrado, e a mensagem diz qual etapa falta.
   Docs, `.claude/` e arquivos `.md` nunca são barrados.
3. **Portão de início:** `portao <nome>`, sozinho numa chamada (sem `&&`, sem pipe; o hook barra a
   forma combinada). Termina com `portao <nome>: passou` ou `FALHOU (<motivo>)`; passou, o hook assina.
   Em portão de artefato, o arquivo precisa existir. Mudou o artefato: o carimbo é novo.
4. **Portões de fim:** quem escreveu o código não carimba. Quando a implementação estiver pronta, rode
   `/tr:qualidade-verificar` (um subagente limpo por portão de comando) e `/tr:bugs-cacar` (o caçador de
   bugs). O hook escreve o pedido de cada validador e assina a partir dele. O carimbo é do estado
   atual: código alterado pede nova validação. A linha `Portões:` da spec escolhe os opcionais.
5. **Entregue** após `fullchico-harness entregar` passar (`[fora]` é portão que esta demanda não pede).

Uma demanda nova começa por `/tr:processo-planejar`.

Barrado e sem entender? Rode `portao` e siga o "fazer" do portão que falta.
