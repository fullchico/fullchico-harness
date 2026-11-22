# memoria

Memória do projeto ancorada em git. Cada resumo do mapa do código e cada nota guarda o commit em que
foi escrito e os caminhos que descreve; saber se envelheceu é uma pergunta ao git, sem IA. No começo
de toda sessão, um hook injeta o mapa e as notas em dia, marcados como dado e não como instrução.

## Instalar só ele

```
npx @fullchico/harness add memoria
```

ou, à mão: `claude plugin marketplace add FullChico/fullchico-harness` e
`claude plugin install memoria@fullchico --scope project`.

## Comandos (a pasta `bin/` entra no PATH da sessão)

- `memoria check | units | record | show | slice | index | forget | anchor | anchors | note add|show|forget | notes`
- `memoria-sessoes sessions | digest | usage | mark | propose | proposals`

## Skills e agente

`/memoria:mapear` refaz o mapa do que envelheceu; `/memoria:dream` consolida o que as sessões ensinaram
em notas; `/memoria:aprender` fecha o ciclo depois do merge. Quem propõe notas é o agente
`memoria:extrator`; `memoria note add` só aceita nota nova cujo nome ele propôs.

## Onde ficam os dados

Mapa, âncoras e notas ficam em `<diretório git comum>/harness-memory/`, o mesmo lugar do plugin antigo
`harness`: quem já tinha memória continua com ela. Os candidatos do extrator ficam em
`~/.claude/trilho/<id>/candidates/`, gravados por hook, fora do alcance do agente.
