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
3. **Verifique o portão.** `portao <nome>`, sozinho numa chamada (sem `&&`, sem pipe): roda a
   verificação e termina com `portao <nome>: passou` ou `portao <nome>: FALHOU (<motivo>)`. Se passou,
   o hook assina. Em portão de artefato, o arquivo precisa estar em commit. Mudou o artefato: o carimbo é novo.
4. **Termine pelos de fim.** O carimbo de fim é do commit do topo: commit novo pede de novo.
   Portão de comando exige a árvore limpa (tudo commitado). Portão de agente só o agente nomeado
   assina: dispare-o sobre o commit do topo; o veredito APPROVED dele vira o carimbo.
5. **Envie** só com todos os `ok`.

Barrado e sem entender? Rode `portao` e siga o "fazer" do portão que falta.
