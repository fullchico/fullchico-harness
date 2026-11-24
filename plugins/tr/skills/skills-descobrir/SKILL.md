---
name: skills-descobrir
description: Pesquisa skills úteis para a stack e a demanda do projeto, compara as candidatas, instala a escolhida para Claude e Codex e propõe portões verificáveis quando fizer sentido.
---

# Descobrir skills para o projeto

Use este fluxo ao configurar o harness ou quando uma demanda precisar de uma capacidade que as
skills instaladas não cobrem. `/tr:grill-me` continua responsável pelas decisões de entrada e saída;
se você veio de `/tr:configurar`, leve as opções à mesma entrevista, sem abrir outra.

1. Leia a stack, a spec/ticket atual, `skills-lock.json` e `npx skills list --json`. Procure uma
   lacuna concreta. Não instale outra skill só porque apareceu na busca.
2. Rode `npx skills find "<tarefa específica>"`; tente uma segunda expressão se a primeira
   for vaga. Para cada candidata plausível, leia o `SKILL.md` e os scripts/hooks que ela traz,
   confira a origem e compare com as skills já instaladas. Escolha a que melhor cobre a tarefa
   real e funciona nos ambientes do projeto; diga por que ela venceu. Se nenhuma servir,
   registre a lacuna sem inventar uma dependência.
3. Quando a escolha fizer parte da demanda, instale **a skill específica**, no projeto, para
   os ambientes presentes: `npx --yes skills add <fonte> --skill <nome> -a claude-code -a codex -y`
   para ambos. Use somente o ambiente instalado se o projeto tiver um. Prefira fonte fixada em
   tag ou commit para reprodução. Confira `npx skills list --json` e o conteúdo instalado.
4. Apresente cada candidata selecionada como uma proposta simples: **skill e origem**, tarefa
   coberta, **portão de entrada ou revisor final**, evidência de aprovação, tickets em que se
   aplica e modelo do fiscal. Leve essa proposta a `/tr:grill-me`: o dono decide se a skill
   apenas ajuda o executor, se vira requisito antes de começar, ou se revisa a entrega.
   Uma skill instalada não vira portão automaticamente. Para um verificador com
   comando real, proponha `assina: comando` e teste o comando. Para revisão por IA, crie um
   agente fiscal **único para o portão** em `.claude/agents/<agente>.md` e
   `.codex/agents/<agente>.toml`, ambos instruídos a usar a skill instalada, examinar o estado
   atual sem editar e emitir `VEREDITO`, `COMMIT` e `RESUMO`. O fiscal é outra sessão, separada
   do executor. Proponha `assina: agente`, `agente: <agente>`, `momento: inicio|fim` e, se a
   demanda pedir, `sempre: false` para portões aplicáveis só a alguns tickets. Uma skill de
   design pode conferir o brief na entrada; uma de acessibilidade pode revisar só tickets
   de interface no fim. Configure o
   modelo com `modelos configurar portao:<nome> claude:<modelo>` ou `codex:<modelo>`.
5. Mostre o esboço JSON e os comandos `portoes --registrar` ao dono. O registro protegido é
   gravado pelo CLI no terminal dele; preserve portões existentes. Depois, confira `portao` e
   faça uma revisão real de exemplo antes de considerar o portão pronto.

O handoff ao fiscal inclui ticket, spec e resumo da conclusão como contexto. O fiscal relê o
código e a evidência por conta própria; o harness carimba apenas o snapshot que ele revisou.
