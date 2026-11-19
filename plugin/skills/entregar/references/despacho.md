# Despachar os implementadores

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
   - `isolation` como `worktree`, para cada um trabalhar na própria cópia;
   - o modelo: `sonnet`;
   - o pedido, só com ponteiros:

```pedido harness:implementador
spec: docs/specs/exemplo/spec.md
ticket: docs/specs/exemplo/issues/01-nome.md
leitura: GLOSSARY.md
```

4. Quando cada um voltar, junte a branch dele na da feature com `git merge --no-ff`.
   Conflito pequeno você resolve; conflito que muda o sentido do que foi feito volta para
   o implementador, numa rodada de correção.
5. Confira que o ticket ficou `Status: done`. Rode `.harness/validate --profile push`.
6. Peça a fronteira de novo. Repita até ela vir vazia e todo ticket estar concluído.

Os worktrees de agente usam o ambiente da feature. Nenhum implementador sobe ambiente.

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
`opus`. A entrega inteira tem limite de 3 rodadas de correção: na quarta, pare e relate
ao dono.
