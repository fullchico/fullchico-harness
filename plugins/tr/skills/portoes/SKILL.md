---
name: portoes
description: Como trabalhar num projeto com portões (.claude/trilho.json). Use ao começar uma mudança, quando uma escrita de código ou um envio for barrado pelo trilho, ou para saber o que falta.
---

# Trabalhar com portões

Um portão é uma etapa obrigatória do fluxo do projeto. Os de **início** vêm antes de escrever código;
os de **fim** vêm antes de enviar (`git push`, `gh pr create`). O carimbo (a prova) é gravado por um
hook, fora do repositório: você cumpre a etapa, não assina nada, e não altera o registro
(`.claude/trilho.json`), que é do dono.

## Passo a passo

1. **Veja o que falta.** Rode `portao` sozinho. Ele lista cada portão com `ok` ou `falta` e diz o
   que fazer em cada um.
2. **Comece pelos de início.** Antes de escrever em código do app, cumpra a etapa (por exemplo, a
   spec da mudança, saída da entrevista). Escrever sem ela é barrado, e a mensagem diz qual etapa falta.
   Docs, `.claude/` e arquivos `.md` nunca são barrados.
3. **Portão de início:** `portao <nome>`, sozinho numa chamada (sem `&&`, sem pipe; o hook barra a
   forma combinada). Termina com `portao <nome>: passou` ou `FALHOU (<motivo>)`; passou, o hook assina.
   Em portão de artefato, o arquivo precisa estar em commit. Mudou o artefato: o carimbo é novo.
4. **Portões de fim:** quem escreveu o código não carimba. Com tudo commitado, rode
   `/tr:qualidade-verificar` (um subagente limpo por portão de comando) e `/tr:bugs-cacar` (o caçador de
   bugs). O hook escreve o pedido de cada validador e assina a partir dele. O carimbo é do commit do
   topo: commit novo pede de novo. A linha `Portões:` da spec escolhe os opcionais da demanda.
5. **Envie** só com todos os `ok` (`[fora]` é portão que esta demanda não pede).

Uma demanda nova começa por `/tr:processo-planejar`.

Barrado e sem entender? Rode `portao` e siga o "fazer" do portão que falta.
