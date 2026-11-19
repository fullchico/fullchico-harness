# Issue tracker: arquivos locais versionados

Specs e tickets deste repositório são arquivos markdown versionados, não issues
num serviço externo.

## Convenções

- Uma mudança por diretório: `docs/specs/<slug>/`.
- A spec é `docs/specs/<slug>/spec.md`.
- Tickets são um arquivo cada, em `docs/specs/<slug>/issues/<NN>-<slug>.md`,
  numerados a partir de `01`. Nunca um arquivo único com todos.
- Cada ticket tem, perto do topo, uma linha `Status:` e uma linha
  `Blocked by: NN, NN` (vazia quando nada o bloqueia).
- Não há rótulos de triagem.

## Quando uma skill disser "publish to the issue tracker"

Crie o arquivo no caminho acima, criando o diretório se preciso.

## Quando uma skill disser "fetch the relevant ticket"

Leia o arquivo no caminho indicado.
