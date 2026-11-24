# memoria

Memória do projeto ancorada no estado do código. Cada resumo e nota guarda o commit e os caminhos
que descreve. O instalador inicia Git quando necessário. No começo
de toda sessão, um hook injeta o mapa e as notas em dia, marcados como dado e não como instrução.

## Instalar com o tr

```
npx @fullchico/harness add tr memoria
```

ou, à mão: `claude plugin marketplace add FullChico/fullchico-harness` e
`claude plugin install tr@fullchico --scope project` e
`claude plugin install memoria@fullchico --scope project`. As skills ficam no `tr`; os dados e hooks ficam no `memoria`.

## Comandos (a pasta `bin/` entra no PATH da sessão)

- `memoria check | units | record | show | slice | index | forget | anchor | anchors | note add|show|forget | notes`
- `memoria-sessoes sessions | digest | usage | mark | propose | proposals`

## Skills e agente

`/tr:memory-mapear` refaz o mapa do que envelheceu; `/tr:memory-dream` consolida o que as sessões ensinaram
em notas; `/tr:memory-aprender` fecha o ciclo depois da entrega. Quem propõe notas é o agente
`memoria:extrator`; `memoria note add` só aceita nota nova cujo nome ele propôs.

## Onde ficam os dados

Mapa, âncoras e notas ficam em `<diretório git comum>/harness-memory/`, o mesmo lugar do plugin antigo
`harness`. Os candidatos do extrator ficam em
`~/.claude/trilho/<id>/candidates/`, gravados por hook, fora do alcance do agente.
