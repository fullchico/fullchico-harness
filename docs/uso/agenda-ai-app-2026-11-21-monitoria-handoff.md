# Handoff da monitoria: entrega `agendamento-barbearia` no `agenda-ai-app`

Escrito em 2026-11-21 às 20:50 pela sessão de monitoria (Claude Desktop, aberta em
`~/www/fullchico-harness`). A monitoria passa para a sessão deste worktree. A sessão de
origem parou o agendamento dela; nada mais roda de lá.

Horários em hora local (UTC−3). As transcrições gravam em UTC.

## Onde a entrega está (20:47)

- **Os 14 tickets foram integrados** (o 14 às 20:36). A entrega está no fechamento.
- O orquestrador reabriu tickets para corrigir pendências: 05, 06, 12 e 08 já voltaram
  integrados; **09 e 10 estão `claimed`**, em correção.
- **Pendências abertas: 6** (P1, P2, P7, P9, P10, P11), de 11 no pico.
- Ainda não aconteceu: checagem de merge do fechamento, os portões sobre a branch inteira,
  push e pull request. A branch não tem remoto (esperado).
- Portas 35520 (front) e 35521 (API) livres, sem órfão. Postgres e Playwright de pé.
- Tela da sessão da entrega sem pedido de permissão aberto.
- Disco: 36 GB livres. 38 worktrees de agente em `~/www/agenda-ai-app/.claude/worktrees/`.
- A lib no projeto é a v0.1.8.

## Como continuar a monitoria

Só leitura, salvo o sim do dono a cada intervenção.

- Worktree da feature: `~/orca/workspaces/agenda-ai-app/houndshark`, branch
  `FullChico/chore-harness-setup`.
- Tickets: `grep -m1 '^Status:' docs/specs/agendamento-barbearia/issues/*`.
- Achados: `docs/specs/agendamento-barbearia/achados/`. Pendências: `.harness/pendings`.
- Transcrições: `~/.claude/projects/-Users-diogobarbosa-orca-workspaces-agenda-ai-app-houndshark/`,
  sessão principal `4a0b4298-51f3-4319-bc76-1cd8be26368d.jsonl`, agentes em `subagents/`.
  Orquestrador atual: `agent-a624dd9ed61cc9824`.
- **Tela da sessão da entrega** (é onde aparece pedido de permissão; não está em arquivo nenhum):
  `/Applications/Orca.app/Contents/Resources/bin/orca terminal read --terminal term_e06d2d0e-4182-4c5e-9909-156f74ed3134 --screen --json`.
  O comando `orca` não está no PATH; o handle muda se o Orca reiniciar (`terminal list
  --worktree path:<houndshark>`).
- Portas da feature: chaves `*_PORT` do `.env` (35520 a 35523). Órfão = alguém escutando na
  35520 ou 35521 sem `.harness-run/dev.pid`.
- Travamento: nenhum `.jsonl` muda há mais de 15 minutos com trabalho pendente. Olhar também
  a tela, porque agente parado em pedido de permissão parece agente morto na transcrição.

O dono autorizou intervenção direta e pediu que cada uma seja anotada em
`docs/melhoria-sandbox-ambiente.md`, seção "Intervenções do dono durante a entrega". Uma
tentativa de agendar rodadas com intervenção automática foi negada pelo classificador de
segurança da sessão de origem; ficou como rodada de leitura que avisa e espera o sim.

## O que entregar no fim (pedido original do dono)

Tempo total, tempo por ticket, rodadas de revisão por ticket, achados severos por ticket,
pendências que ficaram abertas e a lista de pontos de processo. Falta ainda perguntar ao
dono o que irritou e o que surpreendeu (seção "O que o dono achou" do relatório de uso).

## Tempos e rodadas até 20:47

Primeiro commit do harness no projeto: 14:15. Primeiro claim: 14:23. Último ticket
integrado: 20:36 (6h13 depois do primeiro claim; 3h02 depois da retomada das 17:34).

| Ticket | 1º claim | Merges | Reprovações de revisor | Outros retornos |
|---|---|---|---|---|
| 01 contrato e ferramentas | 14:23 | 17:48, 18:06, 18:49 | 3 | 3 ajustes de ambiente (tsx, Turbopack, fechamento com banco parado) |
| 02 base da API | 17:50 | 18:04 | 1 | nenhum |
| 03 base do front | 18:05 | 18:28 | 0 | 1 despacho descartado, 3 ajustes (posse, posse, porta ocupada), 1 volta por teto de pendências |
| 04 auth | 19:18 | 19:24 | 1 | nenhum |
| 05 catalog | 19:18 | 20:11, 20:45 | 1 | 44 min parado em pedido de permissão; reaberto no fechamento |
| 06 scheduling | 19:18 | 20:13, 20:40 | 0 | 40 min retido esperando o 05; reaberto no fechamento |
| 07 booking | 20:13 | 20:20 | 1 | nenhum |
| 08 appointment | 20:13 | 20:17, 20:46 | 0 | reaberto no fechamento |
| 09 login | 20:13 | 20:19 | 1 | reaberto no fechamento, em correção |
| 10 agenda ver | 20:20 | 20:24 | 0 | reaberto no fechamento, em correção |
| 11 agenda marcar | 20:24 | 20:31 | 1 | 1 ajuste de posse |
| 12 manage-services | 20:20 | 20:23, 20:41 | 0 | reaberto no fechamento |
| 13 manage-barbers | 20:21 | 20:25 | 0 | nenhum |
| 14 ponta a ponta | 20:31 | 20:36 | 0 | nenhum |

Achados severos lidos: 01 tem 5 (3 na rodada 1, 1 na 2, 1 na 3); 02 tem 2; 04 tem 1.
**Não lidos**: `05-rodada-1`, `07-rodada-1`, `09-rodada-1`, `11-rodada-1`, `11-ajuste-posse`,
`06-fechamento`, `pendencias.md`. A contagem de severos desses tickets está por fazer.

O histórico do 01 antes das 17:34 (claim 14:23, reopen 14:24, claim 15:25) não foi investigado.

Paradas que não são trabalho:

| Intervalo | Duração | Causa |
|---|---|---|
| 16:32 a 17:34 | ~1 h | queda de rede (`ENOTFOUND`) matou o orquestrador |
| 18:49 a 19:16 | 27 min | porta do front presa por servidor órfão de um revisor |
| 19:18 a 20:02 | 44 min | pedido de permissão aberto na tela da sessão principal |

## Decisões tomadas sem o dono (a confirmar com ele)

- Regra `missing`/`extra` do teste de contrato (17:46).
- Limites de requisição valem só em rota marcada (17:59).
- `tsx` trocado por `node --import tsx` no seed (18:05).
- **`dev` do front virou `next build && next start`, sem hot reload (18:44)**, depois de
  Turbopack e webpack falharem no sandbox. O dono reagiu a essa ("Pq tá usando webpack!?").
- Componentes shadcn escritos à mão, porque `ui.shadcn.com` é bloqueado (18:13).
- Nova tentativa em deadlock do Postgres, até 3 vezes (19:32).
- Ordenação de nomes do catálogo com `collate "C"` (20:10).
- Implementadores em `haiku`; o ticket 14 em `opus`.

## Pontos de processo

Coisas da ferramenta de entrega, não do aplicativo. Sem proposta de correção, só registro.
As propostas sobre sandbox e ambiente estão em `docs/melhoria-sandbox-ambiente.md`.

**Rede e orquestrador**
1. 16:32, ticket 01: queda de rede matou o agente "Retomar execução da spec"; uma hora parada.
13. 18:12, ticket 03: o orquestrador encerrou sozinho com implementador em segundo plano; o
    relato foi parar na sessão principal, que redespachou. Causa não identificada.
14. 18:13: o orquestrador novo repetiu na partida os tropeços do anterior.
34. 18:52: diante de bloqueio que ele mesmo descreveu como fora do alcance, esperou em laço
    em vez de pedir o dono.
38. 19:17: viu o segundo órfão, não conseguiu matar e despachou a onda sem registrar.
42. 19:18 a 20:02, ticket 05: esperou um implementador parado, sem tempo limite por despacho.
43. 19:32, ticket 06: ticket aprovado ficou retido por outro, independente.
39. 19:18: primeira onda com três tickets em vez dos nove do plano.
35, 36, 49. A sessão principal relatou estado errado (18:52), não repassou o bloqueio da
    porta ao dono e ficou com a tela dizendo "2 de 14" até o fim.
Positivo: orquestrador como subagente deixa a sessão principal livre para responder o dono.
Custo: ela enxerga só git e arquivos, e o orquestrador é ponto único de queda.

**Guards**
5, 14, 58. `dispatch_guard`, formato do pedido ao revisor: negado 4 vezes às 17:34, 1 às
    18:13, 1 às 20:39.
5, 14. `service_guard`, juntar branch à mão: 17:34, 17:39, duas às 18:13.
5. Despacho com ticket fora de `claimed` (17:39).
5, 32. Script do harness encadeado com outro comando (17:49, 18:28); `sleep` encadeado (18:49).
21. 18:30, ticket 01: o achado mandava conferir com `.harness/dev` e o guard negou ao
    implementador e aos dois revisores, em 40 segundos.
— 18:27, ticket 03: revisor tentou alterar o worktree da feature.

**Fatiamento e posse**
3. 17:46, ticket 01: severo que era efeito do 01 sobre os tickets 02, 04, 05 e 06.
10. 18:04, ticket 02: `app.module.test.ts` sem dono.
12, 15. 18:06 a 18:20, ticket 03: quatro correções de posse (marcadores de fatia,
    `pages/.gitkeep` com caminho errado, `playwright.config.ts`, `next-env.d.ts`), cada uma
    com reopen e implementador novo.
16. 18:19, ticket 03: a configuração de ponta a ponta do 01 esperava uma rota do ticket 06.
54. 20:27, ticket 11: arquivos de ligação com a agenda fora de `Owns:`.
8, 22. Ticket 01 reaberto duas vezes depois de integrado, mexendo em arquivo de outros
    tickets (`apps/api/package.json`, `apps/web/package.json`).

**Revisão e pendências**
2. Ticket 01: três tentativas; 2 dos 3 severos da rodada 1 eram de ambiente.
9. O ajuste "não conta como rodada" passou pelos dois revisores (resolvido, é só o nome).
18. Arquivos `NN-rodada-N.md` que não são reprovação de revisor inflam a contagem.
20. 18:25, ticket 03: três pendências simples (uma acima do teto) custaram uma rodada inteira.
26. 18:30 a 18:42, ticket 01: correção entregue sem conferir; só o revisor de ambiente, que
    subiu o `next dev` direto, viu que não funcionava.
51. P3 e P5: a mesma pendência registrada por dois revisores.
56. 20:40: veredito de revisor não gravado pelo hook com revisores em paralelo; o
    orquestrador passou a despachar um de cada vez.
57. 20:38: pendência corrigida reabrindo o ticket inteiro; seis tickets reabertos no fechamento.
4. Pelo menos oito decisões registradas na spec sem o dono (lista acima).

**Ambiente e sandbox** (detalhe e contagens em `docs/melhoria-sandbox-ambiente.md`)
22. Três falhas do mesmo tipo no 01: `steiger` EMFILE (17:39), `tsx` EPERM (18:05), Turbopack
    FSEvents (18:28). A lib já sabia do Turbopack desde 19/11.
25, 30. Bundler de dev trocado duas vezes por causa do sandbox, sem o dono.
17, 27, 29. Processo órfão em porta: API esquecida (18:20), `next dev` do revisor (18:35).
33. Órfão fora do alcance do `kill` (sandbox) e do `ports-free` (regra da pasta da feature).
37. 19:17: `.harness/down` deixou o `next start` filho vivo (item 7 da v8).
31. 18:46: ticket não fechou porque o banco estava parado; um despacho só para trocar o status.
28. Fase paralela parada de 18:28 a 19:18 por causa do `dev` do front.
45. Pedido de permissão do modo automático para um `grep` de leitura prendeu a onda 44 min,
    invisível nas transcrições.
50. Dez fatias de tela integradas sem o app subir nenhuma vez depois das 19:17. Não foi
    conferido se os testes de ponta a ponta do 14 rodaram contra o app de pé.

**Tropeços repetidos dos agentes**
19, 23, 47, 52, 55, 60. `sed -i` do BSD: seis vezes (18:14, 18:30, 20:09, 20:23, 20:30, 20:40).
24, 41, 53, 59. Pacote `contracts` sem build no worktree novo: mais de dez agentes.
48. 20:07, ticket 05: `amend` misturou a troca de status no commit de código.
61. 20:40, ticket 10: Prettier aplicado com o estilo errado.

**Worktrees**
6, 11. Worktree de tentativa encerrada não é removido: 38 no disco às 20:47. O do despacho
    descartado do 03 foi removido; os concluídos não. `agent-a133ecee` está travado sem
    agente desde as 18:12.

**Sobre a própria monitoria**
46. Ler só transcrições e git não bastou: o pedido de permissão só aparecia na tela. O
    diagnóstico "implementador do 05 morreu" (19:41) estava errado.
7. As rodadas de 10 minutos caíram várias vezes logo depois de um pedido de status do dono.

## Intervenções feitas (três)

Estão na tabela de `docs/melhoria-sandbox-ambiente.md`: `kill 63953` às 19:16, `kill 74205`
às 20:01 e "Yes" no pedido de permissão às 20:02.

## Arquivos desta monitoria na lib, sem commit

- `docs/melhoria-sandbox-ambiente.md`: diagnóstico do sandbox, contagem de negações,
  propostas (a 6, app em contêiner, é a direção do dono), intervenções.
- este arquivo.

O dono foi perguntado duas vezes se queria o commit do documento de melhoria e não respondeu.
