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
- A checagem completa a cada onda com tela pegou defeito que o revisor e os testes do ticket
  não pegaram, em pelo menos cinco tickets de tela.
- O ambiente provado logo depois da base pegou defeito nas duas fundações.
- Nenhum ticket passou de três rodadas; o contrato não foi mais o gargalo.

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

9. **Implementador fechou o ticket afirmando que o teste passava, sem tê-lo rodado.** Quem
   desmentiu foi a checagem completa depois da onda. O fechamento do ticket deve trazer a prova
   (a saída do teste), não a afirmação; e o `integrate` deveria rodar os testes de navegador do
   próprio ticket, não só a checagem de push.
10. **Fechar o ticket só depois de o teste passar no ambiente da feature.** O orquestrador
    passou a fazer isso sozinho no meio da v7, depois do caso acima. Vira regra do roteiro.
11. **O que conta como rodada no teto de três.** Um ticket teve duas reprovações da checagem
    completa e uma do revisor. O roteiro diz "só reprovação conta", sem dizer se a da checagem
    entra. Definir, e contar por máquina.
12. **Total de pendências.** Dez abertas com 16 de 18 tickets integrados: bem menos que as 17
    da v6, mas o teto por revisão não segura o total (ver item 1).
13. **O orquestrador tropeça sempre na mesma regra:** encadeia um comando do harness com outro,
    é barrado pelo guard e refaz. Acontece em toda versão. O roteiro pode dizer isso logo no
    começo, ou o guard pode responder com o comando já separado.
14. **Aviso de pasta não confiável a cada execução.** O Claude Code ignora as permissões
    `allow` do projeto em pasta nunca aberta em modo interativo. Não atrapalha o teste (roda com
    permissões liberadas), mas atrapalharia uma sessão normal do dono.

## Vindas das listas anteriores, ainda não feitas

15. Entrevista de verdade, em sessão interativa, com o dono respondendo.
16. Linha de base sem harness: o mesmo pedido, só com as skills e um prompt bom.
17. Reprovação de contrato subindo de modelo, contada por máquina.
18. Versão fixada dos plugins de terceiros; aviso quando uma skill fixada mudar na origem.
19. Teste por propriedade exigido por máquina nas regras com borda.
20. Decisão sobre a skill `shadcn`, que executa `npx shadcn@latest` ao carregar.
21. A suíte da lib travou uma vez sem causa encontrada; os testes deixam resíduo em
    `~/.claude/harness/`.
22. Os passos novos do roteiro (ambiente provado depois da base, checagem completa a cada onda
    com tela, aplicativo de pé no fim) são instrução, não trilho.

## Ainda não observado na v7 (a lista fica incompleta até ela terminar)

- O ciclo completo das pendências: correção no fechamento e conferência pelo caçador de bugs.
- Os quatro portões sobre a branch inteira e o push.
- O aplicativo deixado de pé no fim, depois do envio.
- A auditoria independente: quantos defeitos escaparam de todas as camadas.
