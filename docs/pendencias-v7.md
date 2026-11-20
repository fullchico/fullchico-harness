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

## Vindas da lista da v6, ainda não feitas

7. A entrega termina com o app de pé e o link na última mensagem (na v6 o relato só diz como
   abrir).
8. Entrevista de verdade, em sessão interativa, com o dono respondendo.
9. Linha de base sem harness: o mesmo pedido, só com as skills e um prompt bom.
10. Reprovação de contrato subindo de modelo, contada por máquina.
11. Versão fixada dos plugins de terceiros; aviso quando uma skill fixada mudar na origem.
12. Teste por propriedade exigido por máquina nas regras com borda.
13. Decisão sobre a skill `shadcn`, que executa `npx shadcn@latest` ao carregar.

## Regras para a v7, do dono

- Teste limpo: nenhum achado específico de uma versão anterior entra nos agentes, nos
  roteiros ou na spec da versão seguinte. Só mudança de processo.
- Cada versão parte do zero, em pasta isolada, sem enxergar as anteriores.
