# Despachar os implementadores

## Antes da primeira rodada

**O `harness.conf`.** Sem `PROJECT` nele não há portas, nem ambiente, nem worktree de
implementador. Se estiver vazio (projeto novo), proponha você: escreva o conteúdo em
`.harness-run/harness.conf`, no formato do arquivo atual, com o que a spec decidiu, e rode
exatamente `.harness/conf-apply`. O comando confere a proposta, grava o arquivo e as portas no
`.env`, sem perguntar ao dono. Faça o commit do `harness.conf`: é pelo diff que os revisores o
conferem. Nunca peça ao dono para colar o arquivo.

**O ambiente.** Se os testes da entrega precisam de banco ou de outro serviço, suba antes:
`.harness/up`, depois `.harness/prepare`. Ticket que depende do ambiente não é concluído com
teste contra um substituto em memória: sem ambiente de verdade ele fica `claimed`.

Rode `.harness/conf-apply` e `.harness/up` sozinhos, um por chamada, sem `&&` nem `;`. Só a
forma exata sai do sandbox; encadeados, eles rodam dentro dele e falham.

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
2. Em cada um, troque `Status: open` por `Status: claimed`. Faça um commit só:
   `chore(tickets): claim <NN>, <NN>`.
3. Dispare todos na mesma mensagem, para rodarem ao mesmo tempo. Para cada ticket, a
   ferramenta de subagente com:
   - o agente: um agente do projeto em `.claude/agents/` cuja descrição cobre a área do
     ticket, se houver; senão `harness:implementador`;
   - `isolation` como `worktree`, para cada um trabalhar na própria cópia, mesmo quando a
     rodada tem um ticket só;
   - o modelo: `sonnet`;
   - o pedido, só com ponteiros:

```pedido harness:implementador
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
leitura: GLOSSARY.md
```

   A linha `leitura` é opcional e só lista arquivos que existem. A spec e o ticket precisam
   estar em commit: o implementador trabalha numa cópia que só tem o que foi commitado.

4. Quando cada um voltar, ele diz em que branch ficaram os commits. Junte essa branch na da
   feature com `git merge --no-ff`, e depois rode `.harness/agents-clean`, que apaga os
   worktrees de agente já integrados e as branches deles.
   Conflito pequeno você resolve; conflito que muda o sentido do que foi feito volta para
   o implementador, numa rodada de correção.
5. Confira que o ticket ficou `Status: done`. Rode `.harness/validate --profile push`.
6. Peça a fronteira de novo. Repita até ela vir vazia e todo ticket estar concluído.

Os worktrees de agente usam o ambiente da feature. Nenhum implementador sobe ambiente. Cada
um prepara a própria cópia com `.harness/setup-worktree`, que traz o `.env` da feature e
instala as dependências.

Se um implementador cair sem entregar, o ticket dele fica preso em `claimed` e some da
fronteira. Devolva-o a `Status: open`, faça o commit, e despache de novo.

## Quando o implementador diz que falta algo

É uma lacuna da spec ou do ticket. Corrija o documento, faça o commit, devolva o ticket a
`Status: open` e despache de novo. Não responda a lacuna no pedido.

## Rodada de correção

Quando a checagem ou um revisor reprova:

1. Grave o achado, como veio, em `docs/specs/<slug>/achados/<NN>-rodada-<n>.md` e faça o
   commit. O arquivo precisa estar versionado para o implementador enxergá-lo no worktree dele.
2. Despache o ticket afetado de novo, com o achado apontado:

```pedido harness:implementador
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
achado: docs/specs/exemplo/achados/01-rodada-1.md
```

3. Junte o resultado e volte ao fechamento.

Conte as rodadas. Um ticket reprovado duas vezes passa a ser despachado com o modelo
`opus`. A entrega inteira tem limite de 3 rodadas de correção: na quarta, pare e devolva o
relato do que travou.
