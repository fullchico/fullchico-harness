# Validadores por portão: subagente limpo, pedido escrito pelo hook

Data: 2026-11-23. Fonte: conversa com o dono e o uso real no `agenda-ai-app`, worktree `elephantfish`,
branch `fullchico/horario-primeiro-celular` (36 min, US$ 10,45, 9 subagentes, lib 2.1.0 / `tr` 0.4.0).

## Intenção

Pegar um projeto, pôr trilhos e forçar as validações com carimbo, para garantir que o processo
aconteceu. O fluxo do meio é adaptativo (as skills do projeto, como as do mattpocock, conduzem). A lib
não depende de a IA lembrar ou interpretar texto: o que pode ser hook é hook.

A regra central, do dono: **cada validação começa num subagente independente, de contexto limpo, e só
ele assina. Quem escreveu o código nunca assina.** O objetivo é contexto limpo e verdadeiro para a
análise, não outro ambiente: o validador roda na mesma pasta do projeto.

## Metas

1. Todo portão de fim é validado por um subagente próprio, disparado por um invoker (`/<plugin>:<skill>`).
2. Cada validador valida só o que o portão dele propõe. Nenhum papel extra.
3. O pedido ao validador é escrito pelo hook, não por quem escreveu o código.
4. Só a execução de dentro do subagente do portão assina. A sessão principal e os implementadores podem
   rodar `portao <nome>` para ver o resultado, mas não carimbam.
5. O validador é só leitura, garantido por hook.
6. O bloqueio aparece como quadro legível (já feito nesta branch, ver "Já feito").

## Não metas

- Ambiente separado (worktree à parte, checkout limpo) para validar.
- Um validador geral que roda vários portões, ou que acumula conferências além do portão dele
  (ex.: "o diff afrouxou os verificadores" não entra escondido em outro validador; se valer, vira portão
  registrado pelo dono).
- Hook `Stop` que impede a sessão de terminar com portão faltando. Perguntado duas vezes, sem decisão;
  fica fora desta rodada. A cobrança continua no envio.
- Orquestração (grafo de tickets, loop): continua "a vir" no plugin `orquestracao`.

## Anti-metas (falharia mesmo funcionando)

- Carimbo que a sessão que escreveu consegue produzir sozinha.
- Validador cujo pedido carrega a narrativa de quem escreveu ("está tudo certo, só confira X").
- Mais um papel/agente sem portão correspondente.

## O que o uso no elephantfish mostrou (base das decisões)

- O fluxo seguido foi o do mattpocock, improvisado: entrevista → spec → tickets em
  `docs/specs/<x>/issues/NN.md` → implementador `general-purpose` com `tdd` por ticket em worktree → merge.
- A sessão principal (que escreveu) rodou `portao` 37 vezes; várias com `| tail`/`| grep`, que não
  carimbam e não avisam. Chegou a ler o código do plugin no cache para entender.
- `tr:bugs-cacador`: 6 disparos, 1 carimbo. Dois validaram o commit do ticket no worktree (não era o topo);
  três receberam hash curto e o bloco do veredito não fechou. O pedido foi escrito à mão pelo orquestrador.
- Revisão da spec feita por `general-purpose` com "Você é revisor de spec. Não edite nada.": sem
  carimbo, independência por convenção.
- Restos do harness antigo no `settings.json` do projeto (`.harness/*` em permissões e
  `excludedCommands`, `SubagentStop` de `harness:*`, hook `ports-free`): o `--migrar` não limpou.

## Fatos da plataforma conferidos (Claude Code 2.1.322, sessão interativa real)

- `PreToolUse` no `Agent` com `permissionDecision: "allow"` + `updatedInput` troca o `prompt` que o
  subagente recebe. Conferido: o pedido `echo ORIGINAL` chegou como o texto escrito pelo hook.
- Ferramentas chamadas dentro de um subagente chegam ao hook com `agent_id` e `agent_type`; as da sessão
  principal chegam sem esses campos.
- Bloqueio por exit 2 mostra o caminho do script (`hook error: [python3 -I ".../gate.py"]: ...`). Por JSON
  `deny` some o caminho; o prefixo `Error: PreToolUse:X hook error:` é da plataforma e fica.
- `PostToolUse` com `systemMessage` aparece como `PostToolUse:Bash says: ...`; com `decision: block`
  aparece como "hook returned blocking error" seguido do motivo.

## Desenho

### Invokers e validadores

**Padrão de nome (do dono):** todo invoker é do `tr`, no formato `/tr:<portão>-<ação>`; o agente é
`tr:<portão>-<papel>`. Tudo de portão mora no plugin `tr`.

| Portão | Invoker | Subagente | Valida só |
|---|---|---|---|
| portões de comando (`qualidade`, `acessibilidade`, `seo`, `e2e`... os do registro com `assina: comando`) | `/tr:qualidade-verificar` | `tr:qualidade-verificador`, **um disparo por portão** | o comando daquele portão (`portao <nome>`) |
| `bugs` | `/tr:bugs-cacar` | `tr:bugs-cacador` | defeitos no diff |

- **`/tr:qualidade-verificar`** (skill nova no `tr`) lista os portões de comando de fim que faltam
  (`portao`) e dispara um `tr:qualidade-verificador` por portão. Cada disparo leva só o nome do portão.
  Cobre também os portões de comando do projeto (`seo`, `e2e`...): o nome é o da família, não de um portão.
- **`tr:qualidade-verificador`** (agente novo no `tr`): ferramentas `Bash, Read`. Roda `portao <nome>` sozinho
  numa chamada, uma vez, e termina com o bloco de veredito. Não corrige nada. Com falha, relata o
  trecho da saída que explica.
- Os plugins **`qualidade`** e **`bugs`** deixam de existir. O comando de qualidade já mora no registro
  (`portoes.qualidade.comando`); `qualidade-check` sai. O agente caçador vira `tr:bugs-cacador` (mesmo
  texto de hoje) e a skill vira `/tr:bugs-cacar`. Os `gate.py`/`stamp.py` deles saem: o `tr` é o único que
  barra e assina. O registro padrão passa a trazer `bugs` com `agente: tr:bugs-cacador`; o `--migrar`
  reescreve `bugs:cacador` → `tr:bugs-cacador` no registro e tira `bugs@`/`qualidade@` do `enabledPlugins`.
- Portão de agente de outro plugin (futuro): mesmo mecanismo, com o agente nomeado no registro.

### Pedido escrito pelo hook (`PreToolUse` do `Agent`)

Quando `subagent_type` é o validador de algum portão do registro (`tr:qualidade-verificador`, ou o `agente` de um
portão `assina: agente`):

- O hook resolve o portão: para `tr:qualidade-verificador`, o nome vem da primeira linha do pedido original
  (`portao: <nome>`); precisa ser um portão de comando do registro. Para agente, é o portão cujo
  `agente` é aquele `subagent_type`.
- Monta o pedido canônico e o devolve em `updatedInput.prompt`, descartando o original:
  - `tr:qualidade-verificador`: `portao: <nome>` e `commit: <hash completo do HEAD>`.
  - agente: `diff: <base>...<hash completo do HEAD>` e `commit: <hash completo do HEAD>`, com `base` =
    `registry.base(root)` (o mesmo que o portão de artefato usa).
- Barra (JSON `deny`, quadro) quando: o nome não é portão de comando do registro; a árvore está suja
  (carimbo de fim é do commit); o `subagent_type` é `fork` ou outro tipo que herda a conversa e o
  pedido tenta validar portão.
- `HEAD` e `root` são os do `cwd` da sessão que dispara. Validar commit de ticket em worktree não é
  suportado: o carimbo é do topo da branch de integração.

### Quem assina

- `sign.py`, `PostToolUse` de `Bash` com `portao <nome>`: assina só se o payload tem
  `agent_type == "tr:qualidade-verificador"`. Sem `agent_type` (sessão principal) ou com outro tipo: não assina e
  avisa por `systemMessage` ("resultado visto; o carimbo vem de `/tr:qualidade-verificar`").
- Portão de agente: como hoje (veredito `APPROVED` no `SubagentStop`/`SubagentHandback`), agora com o
  pedido já canônico.
- O validador termina com o bloco atual (`VEREDITO`, `COMMIT`, `RESUMO`), hash completo.

### A mensagem aponta o invoker

Todo quadro de bloqueio (envio sem carimbo de fim, `portao` listando o que falta) diz o invoker de cada
portão, não o comando cru (pedido do dono, com print do elephantfish):

```
⛔ trilho · envio barrado

  commit   246be583ec
  motivo   faltam portões de fim

  ✗ qualidade · lint, typecheck e testes
    → /tr:qualidade-verificar
  ✗ bugs · caça de bugs no diff
    → /tr:bugs-cacar
```

- Portão `assina: comando` → `/tr:qualidade-verificar`.
- Portão `assina: agente` → `/tr:<portão>-<ação>` quando o agente é do `tr` (`tr:bugs-cacador` →
  `/tr:bugs-cacar`). Sem invoker conhecido, o texto atual ("dispare o agente X").
- Portão `assina: artefato` (início) → o passo atual (produzir e commitar o artefato).
- A skill `/tr:qualidade-verificar` é invocável pela IA (sem `disable-model-invocation`), para o fluxo seguir
  sozinho a partir do bloqueio.

### Só leitura e forma do comando (`gate.py`)

- Com `agent_type` de um validador de portão: barra `Edit`, `Write`, `MultiEdit`, `NotebookEdit` e as
  escritas óbvias pelo terminal (as que `bash_targets` já reconhece).
- Qualquer contexto: barra `portao <nome>` combinado com pipe, `&&`, `;` ou redirecionamento, antes de
  rodar, com o quadro dizendo para rodar sozinho. `portao` sem nome (a listagem) continua livre.

### Planejamento (início)

O padrão sugerido continua o portão `processo` por artefato. Com o `mattpocock-skills` ligado, o fluxo
de referência é `/grill-with-docs` (= `grilling` + `domain-modeling`: glossário e ADRs) → `/to-spec` →
`/to-tickets` → `/implement-spec`. Essas skills são `disable-model-invocation: true`: só o dono as
chama; o portão barra a escrita até o artefato existir e diz qual comando falta. O glob do artefato
segue o que o projeto usa (`docs/specs/*/spec.md` no agenda-ai; `.scratch/<feature>/` quando o tracker
local do mattpocock estiver configurado). Nenhuma skill nova de planejamento nesta rodada.

### Migração (`install --migrar`)

Além do que já faz, remove do `settings.json` do projeto: permissões e `excludedCommands` que citam
`.harness/`, hooks que chamam qualquer coisa em `.harness/` (não só `.harness/hooks/`), e o
`SubagentStop` com matcher `harness:*`. `AGENTS.md` e `docs/agents/` não são tocados (são do projeto);
o `install` avisa que ainda descrevem o harness antigo.

Caso real (print do dono, elephantfish): sem `core.hooksPath`, a IA seguiu o `AGENTS.md` antigo, rodou
`.harness/push` (liberado pelas permissões que sobraram) e recebeu do `gate-check` antigo que faltavam
`harness:seguranca`, `harness:revisor`, `harness:revisor-bugs` e `harness:qualidade`, agentes que não
existem mais. Por isso, depois do `--migrar`, o `gate.py` também barra a execução de qualquer coisa em
`.harness/` com o quadro apontando os invokers do `tr` (o envio é `git push`, cobrado pelo trilho).

### Limpeza da lib (auditoria de 2026-11-23)

O modelo antigo sai: `plugin/`, `install` (bash), os ramos `--legado` e `update` do `bin/harness.js`, a
entrada `harness` do marketplace, os testes que só exercitam o modelo antigo, e `plugin/`/`install` do
`files` do `package.json`. Ajustes: `tests/helpers.py`, `release.yml` (versão lida do `package.json`),
`interno/colher` (importa `common` do `memoria`). Os testes de `ledger.py` passam a conferir que as cópias
por plugin são idênticas à de `plugins/_shared/`.

## Já feito nesta branch (não commitado)

- `plugins/tr/scripts/saida.py`: `quadro`, `barrar` (JSON `deny`), `recusar` (JSON `block`), `avisar`
  (`systemMessage`).
- `gate.py` e `sign.py` usam o quadro; carimbo assinado avisa `✓ trilho · <portão> carimbado (<hash>)`;
  reprovação por agente avisa `✗`.
- `registry.passos()`; `howto()` passa a juntar os passos.
- Testes: `tests/helpers.hook_verdict` traduz o JSON de decisão; dois testes novos fixam o formato.

## Respostas à leitura do construtor (decisões minhas, marcadas para o dono conferir)

1. **Registro do `qualidade` sem o plugin:** o `tr` já traz `qualidade` no registro padrão
   (`portoes.py`, `@descobrir` → scripts do `package.json`). O `self_register` deixa de ler o plugin
   `qualidade`; o `install --migrar` tira `qualidade@fullchico` do `enabledPlugins`.
2. **Árvore suja:** a mesma regra de hoje dos portões de fim (`registry.dirty`, sem o que o git ignora).
   O hook do `Agent` barra o disparo do validador com a árvore suja; o `sign.py` confere de novo antes de
   assinar, como já faz.
3. **Paralelo:** os `tr:qualidade-verificador` rodam **em sequência** por padrão (comandos do projeto podem
   disputar porta, build e relatório na mesma pasta). Paralelo fica para quando a orquestração existir.
4. **Verificador rodando outro portão:** assina. Continua sendo um subagente limpo, com pedido escrito
   pelo hook, rodando só `portao <nome>`; a garantia "quem escreveu não assina" se mantém. Não há estado
   compartilhado entre o hook do `Agent` e o do `Bash`.
5. **Portão de agente contra fork/homônimo:** `agent_type` de agente de plugin vem com prefixo
   (`tr:bugs-cacador`, conferido em `docs/verificacao-plataforma.md`); `fork` e `general-purpose` têm outro
   tipo e não assinam. Nada muda no `sign.py` além do pedido já canônico.
6. **Dependência entre plugins:** deixou de existir: `bugs` e `qualidade` passam para dentro do `tr`.
7. **Detectar `portao` combinado:** o mesmo parser do `bash_targets` (`ledger._split`, segmentos já sem
   heredoc). Barra quando um segmento começa por `portao <nome>` e o comando tem mais de um segmento ou
   redirecionamento. `git commit -m "portao qualidade | x"` não é segmento que começa por `portao`.
8. **Formato do `agent_type`:** `plugin:agente` (item 5).
9. **Sem base:** o hook barra o disparo do agente com o quadro ("sem base para o diff: defina o remoto
   ou a branch padrão"), em vez de inventar `HEAD~1`.
10. **Testes do modelo antigo:** sai o arquivo de teste que não importa nada de `plugins/` nem de
    `bin/harness.js` fora dos ramos `--legado`/`update`; os de `plugins/` ficam todos.

## Deixado para quem constrói

- Nomes internos, ordem dos commits, divisão em versões do `tr`/`bugs`.
- Texto do agente `tr:qualidade-verificador` e da skill `/tr:qualidade-verificar` (curtos, em português, no tom dos atuais).
- Como a skill `/tr:portoes` e o `README` passam a descrever o fluxo.
- Versões: subir `tr` e `bugs` (minor), `package.json` (major, por tirar `qualidade` e o modelo antigo).

## Comandos e padronização

Fora desta rodada, por pedido do dono ("depois ver a parte dos comandos e padronizá-los"). Nota: o
`plugins/tr/commands/puro.toml` está no formato do Gemini CLI e provavelmente não carrega no Claude Code.
