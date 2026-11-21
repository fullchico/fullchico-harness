# Pendências para a v8

Anotadas durante a v7 (2026-11-20). Nada aqui foi implementado. A v8 roda do zero, em
ambiente limpo, com o mesmo pedido. Nenhum achado específico da v7 entra nos agentes, nos
roteiros ou na spec: só mudança de processo.

O tempo da v7 não entra na comparação: a internet caiu e oscilou durante a execução (o
primeiro ticket ficou 1h27 com o implementador, com pausas de até 40 minutos sem atividade).

## Diretriz da v8 (do dono, 2026-11-21)

O que pode ser hook, guard ou script entra como trilho. Em texto fica só o que é julgamento
ou a explicação do porquê. Texto é interpretável e burlável.

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

## Varredura: regras que hoje são só texto e viram trilho

Feita em 2026-11-21 por leitura dos roteiros, agentes, skills, `AGENTS.managed.md` e `stack.md`
contra os hooks e scripts. Nada foi rodado: é o mapa do que implementar. Da mais valiosa e
barata para a menos.

| # | Regra hoje em texto | Trilho | Esforço |
|---|---|---|---|
| V1 | Não desligar checagem já gravada | `conf_check` nega proposta que remove ou esvazia `VALIDATE_*`, `MODULE_ROOTS`, `CONTRACT_PATHS` | pequeno |
| V2 | Implementador sempre em worktree isolado | `dispatch_guard` nega sem `isolation: worktree` | pequeno |
| V3 | Implementador e revisores não sobem, param nem removem ambiente, não enviam, não abrem PR | `service_guard`: esses comandos só para o dono e o orquestrador | pequeno |
| V4 | Orquestrador não junta com `git merge` à mão nem resolve conflito | `service_guard` nega `merge`, `rebase`, `cherry-pick` para o orquestrador | pequeno |
| V5 | Agente do projeto que implementa segue as mesmas regras de pedido | `dispatch_guard` reconhece agente de `.claude/agents/` que implementa | pequeno |
| V6 | Só se despacha ticket `claimed`, da fronteira, até `MAX_PARALLEL`, com o grafo válido | `dispatch_guard` lê o ticket; `ticket claim` valida o grafo e conta os em andamento | pequeno |
| V7 | Qualidade roda um comando só, não corrige nem repete | lista branca de comandos para `harness:qualidade` | pequeno |
| V8 | Spec com seções obrigatórias; entrega fora da branch padrão | `ready_for_execution` confere os títulos; `push` recusa a branch padrão | pequeno |
| V9 | Título do PR no formato de commit; corpo sem assinatura de IA | `pr` aplica as mesmas regras do `commit-msg` | pequeno |
| V10 | Começar por `setup-worktree`; implementador não deixa processo rodando | setup por hook; `ports-free` também ao fim do implementador | pequeno |
| V11 | `APPROVED` de qualidade só se a checagem passou | hoje o carimbo confia na frase do agente; gravar o resultado do `validate` por hook e exigir esse registro | médio |
| V12 | Revisor não edita nem deixa o worktree alterado | `gate_stamp` não carimba se o worktree mudou durante a revisão | médio |
| V13 | Orquestrador não escreve código da feature | guard de escrita: só `docs/`, `GLOSSARY.md`, `.harness-run/`; `integrate` recusa commit de código que não seja junção | médio |
| V14 | Modelo por papel e teto de três rodadas | `dispatch_guard` confere o modelo e conta as rodadas (definir antes o que conta: item 11) | médio |
| V15 | Regras de stack conferíveis por texto (o que o `stack.md` lista como "não se usa") | `stack_check.py` no `validate`, só no perfil `fullstack-typescript` | médio |
| V16 | Só este worktree é fonte | hook de leitura nega caminho de outro worktree de feature (hoje não há hook de leitura) | médio |
| V17 | Base provada antes da primeira onda; checagem completa a cada onda com tela; app de pé no fim | script que prova e grava um registro; o despacho e o PR exigem o registro | grande |

## Problemas achados no texto (corrigir junto)

- O fluxo de bug da skill de entrega manda fechar por um roteiro que despacha implementador e
  reabre ticket; sem spec nem ticket, o guard nega.
- O modelo de PR pede a linha final de `validate --profile push`; a checagem do fechamento é `merge`.
- O `AGENTS.md` diz que só o caçador de bugs fecha pendência; o hook aceita também o revisor de ambiente.
- Os roteiros mandam rodar `prepare` e `dev` "sozinhos" como se saíssem do sandbox; não saem.
  É a regra em que o orquestrador tropeça (item 13).
- A descrição do agente `revisor` anuncia três eixos e lista dois.
- O texto diz "ticket com mais de duas pendências não está pronto"; a máquina conta por revisão (item 1).
- O comentário do `harness.conf` diz que `VALIDATE_MERGE` roda antes do PR; roda a cada onda com tela.

## O que fica em texto, e por quê

- Gravidade, caso concreto e o que cada revisor procura: é leitura de código.
- Qualidade da spec e do fatiamento: desenho.
- "Faça só o que o ticket pede", "não adivinhe", teste primeiro: a posse limita os arquivos, não a intenção.
- Substituto igual ao adaptador e corrida com teste real: depende de entender os testes.
- Tipo do commit, código em inglês, vocabulário do glossário: julgamento do revisor.
- Modo autônomo, paradas e relato final: conduta de conversa.

## Ainda não observado na v7 (a lista fica incompleta até ela terminar)

- O ciclo completo das pendências: correção no fechamento e conferência pelo caçador de bugs.
- Os quatro portões sobre a branch inteira e o push.
- O aplicativo deixado de pé no fim, depois do envio.
- A auditoria independente: quantos defeitos escaparam de todas as camadas.
