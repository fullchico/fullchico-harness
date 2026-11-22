# Despachar os implementadores

## Antes de tudo: a retomada

```bash
.harness/resume docs/specs/<slug>
```

Comece sempre por ele, e rode de novo quando não souber em que pé um ticket está. Ele cruza o
ticket na feature, as branches dos worktrees de agente e os portões, e diz a próxima ação de
cada ticket em andamento. Siga-a, em vez de recomeçar:

- `integrar`: a branch foi aprovada. Rode o `.harness/integrate` que ele mostra.
- `revisar`: há commit pronto que ninguém revisou. Despache o revisor com o `diff` e o `commit` que ele dá.
- `esperar`: há implementador ou revisor trabalhando. Espere o aviso de término.
- `corrigir`: o revisor reprovou. É rodada de correção.
- `despachar`: não há commit do ticket em lugar nenhum. Despache o implementador.
- `parado`: o despacho passou do tempo limite (`DISPATCH_TIMEOUT_MIN` no `harness.conf`, 30
  minutos se não estiver lá) sem commit novo nem resposta. Veja "Despacho parado", abaixo.

O harness recusa despachar implementador para ticket que já tem commit pronto e não integrado.
Se o trabalho não presta, reabra o ticket com `.harness/ticket reopen` e pegue-o de novo.

## Antes da primeira rodada

**O `harness.conf`** já foi gravado antes de fatiar (`.harness/entrega/tickets.md`).

**O ambiente.** Se os testes da entrega precisam de banco ou de outro serviço, suba com
`.harness/up` e depois `.harness/prepare`. O `up` vai sozinho, sem `&&` nem `;`: só a forma exata
sai do sandbox. Em projeto novo o compose chega com o ticket de contrato: integre-o primeiro, e
só então suba o ambiente e despache os demais. Ticket que depende do ambiente não é concluído
com teste contra um substituto em memória: sem ambiente de verdade ele fica `claimed`. O
ambiente fica de pé até o envio. Integrado um ticket que muda o schema do banco, rode
`.harness/prepare` de novo.

**A base prova que roda.** Logo depois de integrar o ticket de contrato (e o de fundação, se
foram separados), e antes de despachar qualquer outro, confira o que os revisores não têm
como ver, porque rodam antes de o ambiente existir. `up`, `down` e `logs` vão sozinhos na
chamada; `prepare` e `dev` rodam dentro do sandbox e não têm essa exigência:

1. `.harness/up`: os serviços sobem. Se o aplicativo é um serviço do compose (o
   `harness.conf` não tem `DEV_CMD`), ele sobe aqui também.
2. `.harness/prepare`: as migrations e o seed rodam.
3. O aplicativo responde: confira o front e a API nos endereços do `.env`
   (`curl -s -o /dev/null -w "%{http_code}"`). Com o app no compose, o log sai por
   `.harness/logs <serviço>`. Com `DEV_CMD`, suba antes com `.harness/dev --background`
   (log em `.harness-run/dev.log`) e, conferido, `.harness/down` e `.harness/up` de novo,
   porque os implementadores precisam dos serviços.
4. Mude um arquivo do front e confira que a página servida muda: a recarga a quente funciona.

Falhou qualquer um: reabra o ticket dono com o erro como achado. É ajuste de ambiente, e
não conta como reprovação de revisor no teto de rodadas. Só despache a primeira onda com os
quatro passos passando. Se o que falha é uma ferramenta de desenvolvimento dentro do sandbox, o
conserto é levar o app para o compose (`docs/agents/stack.md`), não trocar a ferramenta do projeto.

**A tela é exercitada desde a primeira.** Depois de integrar uma onda que tem ticket de tela,
rode `.harness/validate --profile merge` uma vez: ele compila o aplicativo e roda os testes de
navegador que já existem. Falhou: rodada de correção para o ticket dono do teste que falhou.

**Testes em paralelo.** Os implementadores de uma rodada dividem o ambiente da feature. Se os
testes usam banco, a spec precisa dizer como cada um isola o seu (um banco de teste por ticket,
por exemplo). Isso se escreve na spec, antes de despachar: o pedido só leva ponteiros.

**O plano.** Monte a tabela das ondas que o grafo dá: quais tickets rodam juntos em cada uma.
Ela vai no seu relato final, com o que de fato rodou em paralelo.

## A fronteira

```bash
python3 -I .harness/tickets_check.py docs/specs/<slug> --frontier
```

A resposta são os tickets abertos cujos bloqueadores já estão concluídos. São esses que
podem ser feitos agora, em paralelo.

## Uma rodada

1. Pegue da fronteira até `MAX_PARALLEL` tickets. O valor está no `harness.conf`; se não
   estiver, use 3.
2. Marque-os como em andamento, com o comando, que também faz o commit:
   `.harness/ticket claim docs/specs/<slug> <NN> <NN>`.
3. Dispare todos na mesma mensagem, para rodarem ao mesmo tempo. Para cada ticket, a
   ferramenta de subagente com:
   - o agente: um agente do projeto em `.claude/agents/` cuja descrição cobre a área do
     ticket, se houver; senão `harness:implementador`;
   - `isolation` como `worktree`, para cada um trabalhar na própria cópia, mesmo quando a
     rodada tem um ticket só;
   - o modelo: `haiku`. O ticket de contrato vai em `sonnet`: é ele que define o que todos
     os outros seguem;
   - `run_in_background` como `false`, se a sua ferramenta de subagente tiver esse parâmetro.
     Se ela responder que o agente foi lançado em segundo plano, o trabalho **não terminou**:
     você não sabe nada do resultado até o aviso de término dele chegar. Espere o aviso de cada
     agente antes do passo que depende dele (revisar, integrar), não dispare de novo o mesmo
     pedido, e não encerre a sua resposta final com agente em andamento;
   - o pedido, só com ponteiros:

```pedido harness:implementador
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
leitura: GLOSSARY.md
```

   A linha `leitura` é opcional e só lista arquivos que existem. A spec e o ticket precisam
   estar em commit: o implementador trabalha numa cópia que só tem o que foi commitado.

4. Quando todos voltarem, cada um diz em que branch ficaram os commits. Antes de integrar,
   cada ticket passa pela caça a bugs: dispare um `harness:revisor-bugs` por ticket, todos na
   mesma mensagem, em primeiro plano (`run_in_background` como `false`, se o parâmetro existir):

```pedido harness:revisor-bugs
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
diff: BASE...HASH_DO_COMMIT
commit: HASH_DO_COMMIT
```

   **O ticket de contrato tem duas leituras, juntas:** na mesma mensagem do
   `harness:revisor-bugs`, com o modelo `opus`, dispare o `harness:revisor-ambiente`, com as
   mesmas quatro linhas. Um procura defeito de comportamento; o outro, o que só funciona na
   pasta de quem escreveu. O `.harness/integrate` exige os dois nesse commit. Os demais
   tickets passam só pelo `harness:revisor-bugs`, no modelo do agente.

   **Achado simples não reprova.** O revisor responde `APPROVED` com linhas `PENDENCIA:`, o
   hook as registra e o ticket segue. O teto é de duas pendências abertas por ticket, somando
   as rodadas e os revisores: passou disso, a aprovação não é gravada, mesmo que ele tenha
   escrito `APPROVED`. É rodada de correção, com as pendências como achado. Você não corrige pendência agora nem a discute: elas
   são tratadas no fechamento, e o push é recusado enquanto houver uma aberta
   (`.harness/pendings` lista).

   `HASH_DO_COMMIT` é a ponta da branch do implementador (`git rev-parse <branch>`), e `BASE` é
   o commit de onde ela saiu (`git merge-base HEAD <branch>`). Reprovou: é rodada de correção
   para aquele ticket, com a resposta como achado, e cada caso apontado entra como teste junto
   com a correção. Os que passaram seguem.
5. Junte cada branch aprovada na da feature com
   `.harness/integrate <arquivo do ticket> <branch>`, um ticket por vez, assim que ela aprova:
   ticket aprovado não espera os outros da onda que não o bloqueiam. Ele recusa a branch
   que não passou pela caça a bugs naquele commit. O comando
   confere que a branch só mexeu no que o ticket possui, junta, roda a checagem e desfaz a
   junção se ela falhar; no fim apaga os worktrees de agente já integrados. Não junte com
   `git merge` à mão.
   Recusa por posse, conflito ou checagem é uma rodada de correção para aquele ticket: o
   comando diz o motivo. Não resolva conflito à mão: ele mostra que o fatiamento está errado.
6. Ticket integrado está `Status: done` e com a checagem passando: o comando garante os dois.
7. A sua onda termina aqui, com os tickets dela integrados e a checagem da onda feita. Não pegue
   outro lote: encerre com `ENTREGA: CONTINUA` se ainda há ticket aberto ou o fechamento a fazer.
   O próximo orquestrador pede a fronteira de novo.

Os worktrees de agente usam o ambiente da feature. Nenhum implementador sobe ambiente. Cada
um prepara a própria cópia com `.harness/setup-worktree`, que traz o `.env` da feature e
instala as dependências.

**Porta ocupada.** Se a aplicação ou um teste não sobe porque uma porta da feature está em
uso, rode `.harness/ports-free`, sozinho: ele encerra o processo esquecido por outro agente
e não toca no que roda da pasta da feature nem nos contêineres. O mesmo comando roda sozinho
quando um revisor termina.

**Agente mudo não é agente morto.** Se um agente despachado fica sem responder, rode
`.harness/doctor` antes de concluir que ele caiu (e leia `.harness-run/aguardando-dono.txt`, se
existir). Pedido de permissão visto e sem resposta é bloqueio do dono: relate qual pedido está
na tela dele e pare. Não espere em laço nem despache de novo.

Se um implementador cair sem entregar, o ticket dele fica preso em `claimed` e some da
fronteira. O `.harness/resume` diz se ele deixou commit: se deixou, revise e integre; se não,
é `despachar`.

**Despacho parado.** Você não espera em laço. Quando o `.harness/resume` diz `parado`:

1. Confira o motivo: `.harness/logs` (sozinho na chamada), se há pedido de permissão esperando
   resposta no worktree do agente, e `.harness/doctor`, se o projeto tiver esse comando.
2. Se dá para destravar (porta ocupada: `.harness/ports-free`; lacuna no ticket: corrija o
   documento), destrave, reabra o ticket com `.harness/ticket reopen`, pegue-o e despache de novo.
3. Se não dá, pare: devolva o relato começando por `PARADA`, com o ticket, o que conferiu e o
   que só o dono resolve. Os tickets que não dependem dele seguem antes de você parar.

## Quando o implementador diz que falta algo

É uma lacuna da spec ou do ticket. Corrija o documento, faça o commit, reabra o ticket com
`.harness/ticket reopen` e despache de novo. Não responda a lacuna no pedido.

Se o que falta é algo comum (um tipo, um utilitário, uma dependência), ele pertence ao ticket
de contrato: acrescente o item a esse ticket, reabra-o com
`.harness/ticket reopen docs/specs/<slug> <NN> "<o que falta>"`, despache-o, integre, e só
então reabra o ticket que relatou a falta.

## Rodada de correção

Quando a checagem ou um revisor reprova:

1. Grave o achado, como veio, em `docs/specs/<slug>/achados/<NN>-rodada-<n>.md` e faça o
   commit. O arquivo precisa estar versionado para o implementador enxergá-lo no worktree dele.
2. Reabra o ticket afetado, com `.harness/ticket reopen docs/specs/<slug> <NN> "<motivo>"`,
   e despache-o de novo, com o achado apontado. O implementador começa de uma cópia nova da feature: se a rodada veio de
   uma recusa do `.harness/integrate`, o trabalho anterior não está nela, então diga no achado
   o nome da branch recusada, para ele trazer o que serve com `git merge <branch>`; no conflito
   do arquivo do ticket, vale `Status: open`. Integrado
   o ticket refeito, jogue fora a branch recusada: `.harness/agents-clean --discard <branch>`.

```pedido harness:implementador
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
achado: docs/specs/exemplo/achados/01-rodada-1.md
```

3. Quando ele voltar, o revisor que reprovou recebe o mesmo arquivo de achado, para conferir
   a correção e não reler o ticket inteiro:

```pedido harness:revisor-bugs
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
diff: BASE...HASH_DO_COMMIT
commit: HASH_DO_COMMIT
achado: docs/specs/exemplo/achados/01-rodada-1.md
```

   No ticket de contrato, o commit novo pede as duas leituras de novo: quem reprovou vai com
   `achado:`; quem tinha aprovado vai com `achado:` também, para conferir só o que a correção tocou.

4. Junte o resultado e volte ao fechamento.

**A posse não muda calada.** Se um ticket precisar de um caminho que não possuía, corrija o
`Owns:` antes de integrar e registre na spec, em "Decisões tomadas sem o dono", o que mudou e
por quê. Você não faz commit de código: o que não é documento entra por um ticket.

**O que você corrige sem despachar ninguém,** porque não é de nenhum ticket: a spec, o
glossário, os tickets e o `harness.conf` (por `.harness/conf-apply`). Tipo de commit errado
apontado pelo revisor não se conserta com commit novo: devolva o relato, é decisão do dono.

Conte as rodadas **por ticket**. A rodada de correção de um ticket vai em `sonnet`; reprovado
duas vezes, em `opus`. Cada ticket tem limite de 3 rodadas de correção: na quarta do mesmo
ticket, pare e devolva o relato do que travou. Só reprovação conta rodada, e só achado severo
reprova; os outros tickets continuam andando enquanto um está em correção.
