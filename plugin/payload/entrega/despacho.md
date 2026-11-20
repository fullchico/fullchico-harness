# Despachar os implementadores

## Antes da primeira rodada

**O `harness.conf`** já foi gravado antes de fatiar (`.harness/entrega/tickets.md`).

**O ambiente.** Se os testes da entrega precisam de banco ou de outro serviço, suba com
`.harness/up` e depois `.harness/prepare`, cada um sozinho, sem `&&` nem `;`: só a forma exata
sai do sandbox. Em projeto novo o compose chega com o ticket de contrato: integre-o primeiro, e
só então suba o ambiente e despache os demais. Ticket que depende do ambiente não é concluído
com teste contra um substituto em memória: sem ambiente de verdade ele fica `claimed`. O
ambiente fica de pé até o envio. Integrado um ticket que muda o schema do banco, rode
`.harness/prepare` de novo.

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
   - `run_in_background` como `false`: você espera os implementadores no mesmo turno. Em
     segundo plano o aviso de término iria para a sessão do dono, não para você;
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
   mesma mensagem, com `run_in_background` como `false`:

```pedido harness:revisor-bugs
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
diff: BASE...HASH_DO_COMMIT
commit: HASH_DO_COMMIT
```

   O ticket de contrato vai com o modelo `opus`: o que passar errado ali é seguido por todos
   os outros tickets. Os demais vão no modelo do agente.

   `HASH_DO_COMMIT` é a ponta da branch do implementador (`git rev-parse <branch>`), e `BASE` é
   o commit de onde ela saiu (`git merge-base HEAD <branch>`). Reprovou: é rodada de correção
   para aquele ticket, com a resposta como achado, e cada caso apontado entra como teste junto
   com a correção. Os que passaram seguem.
5. Junte cada branch aprovada na da feature com
   `.harness/integrate <arquivo do ticket> <branch>`, um ticket por vez. Ele recusa a branch
   que não passou pela caça a bugs naquele commit. O comando
   confere que a branch só mexeu no que o ticket possui, junta, roda a checagem e desfaz a
   junção se ela falhar; no fim apaga os worktrees de agente já integrados. Não junte com
   `git merge` à mão.
   Recusa por posse, conflito ou checagem é uma rodada de correção para aquele ticket: o
   comando diz o motivo. Não resolva conflito à mão: ele mostra que o fatiamento está errado.
6. Ticket integrado está `Status: done` e com a checagem passando: o comando garante os dois.
7. Peça a fronteira de novo. Repita até ela vir vazia e todo ticket estar concluído.

Os worktrees de agente usam o ambiente da feature. Nenhum implementador sobe ambiente. Cada
um prepara a própria cópia com `.harness/setup-worktree`, que traz o `.env` da feature e
instala as dependências.

Se um implementador cair sem entregar, o ticket dele fica preso em `claimed` e some da
fronteira. Reabra-o com `.harness/ticket reopen` e despache de novo.

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

3. Junte o resultado e volte ao fechamento.

**A posse não muda calada.** Se um ticket precisar de um caminho que não possuía, corrija o
`Owns:` antes de integrar e registre na spec, em "Decisões tomadas sem o dono", o que mudou e
por quê. Você não faz commit de código: o que não é documento entra por um ticket.

**O que você corrige sem despachar ninguém,** porque não é de nenhum ticket: a spec, o
glossário, os tickets e o `harness.conf` (por `.harness/conf-apply`). Tipo de commit errado
apontado pelo revisor não se conserta com commit novo: devolva o relato, é decisão do dono.

Conte as rodadas. A rodada de correção de um ticket vai em `sonnet`; reprovado duas vezes,
em `opus`. A entrega inteira tem limite de 3 rodadas de correção: na quarta, pare e devolva o
relato do que travou.
