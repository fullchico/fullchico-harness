# Pendências para a v7

Anotadas durante a v6 (2026-11-20). Nada aqui foi implementado. A v6 roda até o fim sem
intervenção na lib; a v7 roda do zero, em ambiente limpo, com o mesmo pedido.

O tempo da v6 não entra na comparação: a internet estava fraca durante a execução.

## Vistas na v6

1. **Pendência do revisor de ambiente não é registrada.** O hook só registra as linhas
   `PENDENCIA:` do caçador de bugs; as do `harness:revisor-ambiente` se perdem, e a regra
   "pendência aberta barra o push" não vale para elas. Na v6 o orquestrador leu a pendência no
   texto e a incluiu na correção por conta própria. Corrigir no `gate_stamp.py`, com teste.
2. **Pendência de revisão reprovada vira "corrija também".** Quando o veredito é `REJECTED`,
   as pendências não são registradas (por desenho) e o orquestrador as junta ao achado. Cada
   rodada de correção cresce com itens que não reprovaram. Decidir: registrar também nesse
   caso, e o implementador da rodada cuidar só do severo.
3. **O que só aparece ao subir o ambiente.** O contrato da v6 passou pelas duas leituras e só
   então o `.harness/prepare` falhou dentro do sandbox (ferramenta abrindo socket negado). Os
   revisores do contrato rodam antes de o ambiente existir. Avaliar: subir o ambiente e rodar
   `.harness/prepare` como parte da conferência do contrato, antes de integrar.
4. **Ticket de contrato continua sendo o gargalo.** Três rodadas na v6, quatro na v5. O
   fatiamento da v6 já separou um `front-base` sozinho; avaliar dividir de vez em contrato
   (tipos, portas, convenções) e fundação (ambiente, ferramentas, estrutura de testes).
5. **Suíte da lib travou uma vez** e foi cortada pelo limite de tempo; na execução seguinte
   terminou normalmente. Causa não encontrada.
6. **Testes da lib deixam estado em `~/.claude/harness/`** (pastas de pendências de repositórios
   temporários). Limpar ao fim de cada teste.

7. **Critério de gravidade frouxo.** Na v6 o caçador registrou como pendência (simples)
   corrida entre dois pedidos, perda de alteração entre dois administradores e suíte de porta
   que não roda contra o substituto. Na v5 o mesmo tipo de achado reprovava. Trocamos "tudo
   reprova" por "quase nada reprova", e a correção fica para o fim. Fixar por regra, sem
   exemplo de projeto: corrida, perda de dado e substituto divergente são sempre severos.
8. **Teto de pendências por ticket.** Acima de um número pequeno, o ticket volta para correção
   em vez de seguir: pendência é exceção, não o caminho normal.

9. **Revisor deixa processo de pé e trava a entrega.** Na v6 o revisor de ambiente copiou o
   projeto para uma pasta temporária, subiu a API para testar e não a derrubou. O servidor
   ficou na porta da API da feature por mais de uma hora; o ticket de ponta a ponta não
   conseguiu subir a aplicação, e o sandbox não deixa a sessão encerrar processo de outro
   agente. A entrega parou em 13 de 14 e devolveu ao dono. Trilhos a avaliar: revisor não sobe
   servidor nas portas da feature; ao terminar um subagente, o hook encerra o que ele deixou
   escutando nessas portas; e um comando do harness, fora do sandbox, que libera as portas da
   feature, para o orquestrador não depender do dono.

## Vindas da lista da v6, ainda não feitas

9. A entrega termina com o app de pé e o link na última mensagem (na v6 o relato só diz como
   abrir).
10. Entrevista de verdade, em sessão interativa, com o dono respondendo.
11. Linha de base sem harness: o mesmo pedido, só com as skills e um prompt bom.
12. Reprovação de contrato subindo de modelo, contada por máquina.
13. Versão fixada dos plugins de terceiros; aviso quando uma skill fixada mudar na origem.
14. Teste por propriedade exigido por máquina nas regras com borda.
15. Decisão sobre a skill `shadcn`, que executa `npx shadcn@latest` ao carregar.

## Regras para a v7, do dono

- Teste limpo: nenhum achado específico de uma versão anterior entra nos agentes, nos
  roteiros ou na spec da versão seguinte. Só mudança de processo.
- Cada versão parte do zero, em pasta isolada, sem enxergar as anteriores.
