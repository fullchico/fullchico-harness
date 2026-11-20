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

## Vindas das listas anteriores, ainda não feitas

5. Entrevista de verdade, em sessão interativa, com o dono respondendo.
6. Linha de base sem harness: o mesmo pedido, só com as skills e um prompt bom.
7. Reprovação de contrato subindo de modelo, contada por máquina.
8. Versão fixada dos plugins de terceiros; aviso quando uma skill fixada mudar na origem.
9. Teste por propriedade exigido por máquina nas regras com borda.
10. Decisão sobre a skill `shadcn`, que executa `npx shadcn@latest` ao carregar.
11. A suíte da lib travou uma vez sem causa encontrada; os testes deixam resíduo em
    `~/.claude/harness/`.
12. Os passos novos do roteiro (ambiente provado depois da base, checagem completa a cada onda
    com tela, aplicativo de pé no fim) são instrução, não trilho.
