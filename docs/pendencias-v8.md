# Pendências para a v8

Anotadas durante a v7 (2026-11-20). Nada aqui foi implementado. A v8 roda do zero, em
ambiente limpo, com o mesmo pedido. Nenhum achado específico da v7 entra nos agentes, nos
roteiros ou na spec: só mudança de processo.

O tempo da v7 não entra na comparação: a internet caiu e oscilou durante a execução (o
primeiro ticket ficou 1h27 com o implementador, com pausas de até 40 minutos sem atividade).

## O que a v7 confirmou

- Base dividida em contrato, fundação do back e fundação do front, por orientação do roteiro.
- Contrato integrado em duas rodadas (v5: quatro e travou; v6: três).
- Critério de gravidade firme: o primeiro achado severo foi "proteção que não protege".
- Pendências do revisor de ambiente passaram a ser registradas.
- A limpeza de portas rodou ao fim dos revisores sem derrubar nada.

## Vistas na v7

1. **Teto de pendências é por revisão, não por ticket.** O contrato fechou com quatro
   pendências abertas: duas de cada rodada, cada revisão dentro do teto. Avaliar o teto por
   ticket, somando as rodadas e os dois revisores.
2. **Pendência corrigida na rodada continua aberta até o fim.** Quando a revisão reprova, o
   orquestrador manda corrigir as pendências junto ("corrija junto"), mas ninguém as fecha:
   ficam abertas no registro até o passe final. O revisor da rodada de correção deveria
   fechá-las ali, com `RESOLVIDA:`, já que confere a correção.
3. **Pendências repetidas.** Duas pendências do contrato falam do mesmo script, vistas por
   revisores diferentes. O registro só descarta texto idêntico.
4. **Queda de rede no meio da entrega.** Não há retomada automática: se a sessão morrer, um
   ticket fica preso em `claimed` e a entrega precisa ser retomada à mão. Avaliar um comando
   de retomada que o dono rode com uma palavra.

5. **O orquestrador desligou uma checagem para integrar.** Na v7 o contrato não integrava
   porque o `VALIDATE_ARCH` apontava para um arquivo que só o ticket 03 cria. O orquestrador
   comentou a linha no `harness.conf` pelo `.harness/conf-apply`, fez o commit ("pause
   VALIDATE_ARCH until ...") e integrou. O `conf-apply` aceita sem perguntar, e nada obriga a
   religar. Trilho: proposta que remove ou esvazia uma checagem já gravada (`VALIDATE_*`,
   `MODULE_ROOTS`, `CONTRACT_PATHS`) é recusada, ou pede o dono; e o push é recusado se uma
   checagem que a spec declarou não estiver no `harness.conf`.

6. **A entrega encheu o disco.** A v7 parou em 8 de 18 tickets com o disco cheio. Os worktrees
   de agente já integrados não são removidos durante a entrega: o Claude Code os mantém
   travados enquanto a sessão vive, o `agents-clean` pula worktree travado, e o sandbox não
   deixa os agentes apagarem. Cada um carrega dependências e build. Trilho: ao integrar um
   ticket, apagar ao menos o que é regenerável (dependências, build) do worktree dele, mesmo
   travado; e a entrega conferir o espaço livre antes de cada onda, parando com aviso claro.
7. **`.harness/down` deixa processos órfãos.** Ele encerra o processo principal do aplicativo,
   mas os filhos (o servidor do front e o da API) continuam segurando as portas.
8. **`agents-clean` apagou trabalho em andamento.** Rodado à mão depois da parada, removeu
   também os worktrees dos três tickets que estavam no meio da correção, sem commit. Deve
   poupar worktree com alteração não commitada, ou avisar antes.

## Vindas das listas anteriores, ainda não feitas

9. Entrevista de verdade, em sessão interativa, com o dono respondendo.
10. Linha de base sem harness: o mesmo pedido, só com as skills e um prompt bom.
11. Reprovação de contrato subindo de modelo, contada por máquina.
12. Versão fixada dos plugins de terceiros; aviso quando uma skill fixada mudar na origem.
13. Teste por propriedade exigido por máquina nas regras com borda.
14. Decisão sobre a skill `shadcn`, que executa `npx shadcn@latest` ao carregar.
15. A suíte da lib travou uma vez sem causa encontrada; os testes deixam resíduo em
    `~/.claude/harness/`.
16. Os passos novos do roteiro (ambiente provado depois da base, checagem completa a cada onda
    com tela, aplicativo de pé no fim) são instrução, não trilho.
