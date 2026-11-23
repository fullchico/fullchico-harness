# Verificação da 3.0 numa sessão real (2026-11-23)

Claude Code 2.1.322, sessão interativa (pty), modelo da sessão sonnet, `tr` 1.0.0 carregado por
`--plugin-dir` desta árvore. Projeto de rascunho Python com registro `qualidade` (comando) e `bugs`
(agente `tr:bugs-cacador`), remoto local.

## Rodada 1: envio, verificação e caça

| Passo | Resultado |
|---|---|
| `git push` antes dos portões | barrado com o quadro "envio barrado" |
| `/tr:qualidade-verificar` com `__pycache__/` não versionado | disparo do verificador barrado: "a árvore tem alteração sem commit" |
| verificador depois de limpar | pedido canônico no livro (`portao: qualidade`), carimbo `qualidade` |
| `/tr:bugs-cacar` | pedido canônico `diff: <base>...<topo>`, `APPROVED` com duas observações, carimbo `bugs` |
| `git push` de novo | passou |

Achado: para a árvore parecer limpa, a sessão escreveu `__pycache__/` em `.git/info/exclude`. Corrigido
no mesmo dia: o `gate.py` barra escrita em `.git/` ("estado do git protegido"), com o teste do caso.

## Rodada 2: modelo por papel

Ticket `docs/specs/media/issues/01-dobro.md` com `Complexidade: simples`; a sessão (sonnet) disparou um
`general-purpose` com o caminho do ticket e depois `/tr:qualidade-verificar`. Pelas transcrições:

| Subagente | Modelo das respostas |
|---|---|
| `general-purpose` (ticket simples) | `claude-haiku-5-5` (o hook trocou) |
| `tr:qualidade-verificador` | `claude-haiku-5-5` (o `model` da definição; o hook tira o da chamada) |
