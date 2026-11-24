---
name: tr-codex
description: Use para planejar uma mudança, verificar portões, consultar a memória e validar a entrega no Codex.
---

# Portões no Codex

O registro é `.claude/trilho.json`, compartilhado com Claude Code. Consulte o estado com
`python3 -I .codex/harness/tr/scripts/portao.py`.

Antes de editar código, siga o portão de início. Para o padrão `processo`, escreva a spec no caminho
que o registro pede e rode `python3 -I .codex/harness/tr/scripts/portao.py processo`
sozinho. O hook assina o carimbo após o comando passar.

Quando a implementação estiver pronta, confira os portões de fim. Para cada portão de comando, use um
subagente `tr-qualidade-verificador` com mensagem na primeira linha `portao: <nome>`. O hook substitui
a mensagem por nome e snapshot e assina após a execução bem sucedida do comando. Para `bugs`, use um
subagente `tr-bugs-cacador`; o hook substitui a mensagem pelo snapshot e lê o veredito final.
Espere cada validador terminar antes do próximo. O próprio agente que implementou não assina os
portões de fim. Rode `python3 -I .codex/harness/tr/scripts/portao.py entrega` antes de responder.
Só declare `ENTREGA: concluída` quando passar. O instalador inicia Git; PR e push são opcionais.

O Codex precisa carregar os hooks de `.codex/hooks.json` e o projeto deve estar confiável. Sem hooks
ativos, a execução do comando não carimba e os portões não têm força de bloqueio.

Para memória, use as skills `$tr-memory-mapear`, `$tr-memory-dream` e `$tr-memory-aprender`.
O motor fica em `.codex/harness/memoria/`: consulte o índice com
`.codex/harness/memoria/bin/memoria index` e uma parte do código com
`.codex/harness/memoria/bin/memoria slice <caminho>`. Confira as notas contra o código.
