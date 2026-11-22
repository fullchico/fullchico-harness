# bugs

O caçador de bugs, para qualquer projeto. Um agente (`bugs:cacador`) lê o que o diff mudou atrás de
defeito; se aprovar, um hook assina o carimbo `bugs` do commit do topo. Sem o carimbo, `git push` e
`gh pr create` são barrados.

## Instalar só ele

```
npx @fullchico/harness add bugs
```

ou, à mão: `claude plugin marketplace add FullChico/fullchico-harness` e
`claude plugin install bugs@fullchico --scope project`.

## Como se usa

A skill `bugs:cacar` descreve o fluxo: commit, caçar o diff contra a base, corrigir se reprovar.
O carimbo fica fora do repositório, em `~/.claude/trilho/<id>/stamps/bugs/<sha>.json`, e é do
commit: commit novo pede caça nova. Cada decisão (assinou, não assinou, barrou) vai para
`~/.claude/trilho/<id>/log.jsonl`.

## O que ele barra

`git push` (em qualquer ponto de um encadeamento) e `gh pr create`, quando o `HEAD` não tem carimbo.
Sem exceção por tipo de arquivo.
