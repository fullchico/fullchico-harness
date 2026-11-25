# memory

Memória do projeto ancorada no estado do código. Cada resumo e nota guarda o commit e os caminhos
que descreve. O instalador inicia Git quando necessário. No começo
de toda sessão, um hook injeta o mapa e as notas em dia, marcados como dado e não como instrução.

## Instalar com o tr

```
npx @fullchico/harness add tr memory
```

ou, à mão: `claude plugin marketplace add FullChico/fullchico-harness` e
`claude plugin install tr@fullchico --scope project` e
`claude plugin install memory@fullchico --scope project`. As skills ficam no `tr`; os dados e hooks ficam no `memory`.

## Comandos (a pasta `bin/` entra no PATH da sessão)

- `memory check | units | record | show | slice | index | forget | anchor | anchors | note add|show|forget | notes | graph rebuild | graph search <termos ou caminhos>`
- `memory-sessions sessions | digest | usage | mark | propose | proposals`

## Skills e agente

`/tr:memory-map` refaz o mapa do que envelheceu; `/tr:memory-dream` consolida o que as sessões ensinaram
em notas; `/tr:memory-learn` fecha o ciclo depois da entrega. Quem propõe notas é o agente
`memory:extractor`; `memory note add` só aceita nota nova cujo nome ele propôs.

A skill `graphify` acompanha o plugin no Claude e é copiada para `.agents/skills/graphify`
no Codex pelo instalador. O motor AST é a CLI externa `graphify` (pacote oficial
`graphifyy`). Para habilitá-lo localmente, instale com `uv tool install --with anyio graphifyy`;
o índice simples do harness continua disponível quando a CLI não estiver instalada.

## Onde ficam os dados

Mapa, âncoras e notas ficam em `<diretório git comum>/harness-memory/`, o mesmo lugar do plugin antigo
`harness`. Os candidatos do extrator ficam em
`~/.claude/tr/<id>/candidates/`, gravados por hook, fora do alcance do agente.

`memory graph rebuild` gera um índice descartável em `graphify.json`, e `memory graph search`
faz busca lexical nos resumos, notas e âncoras, seguindo referências para arquivos versionados.
O índice é local ao clone/worktrees e não entra no Git; é atualizado ao pesquisar e pode ser
reconstruído a qualquer momento. Não requer serviço externo nem dependência de nuvem.
