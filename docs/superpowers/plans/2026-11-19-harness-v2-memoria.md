# Harness v2: memória ancorada em git — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O projeto tem um mapa do código e âncoras para o glossário e os ADRs que dizem, de graça e pelo git, o que envelheceu; toda sessão começa conhecendo o mapa.

**Architecture:** Um script, `.harness/memory`, guarda cada item com o commit em que foi escrito e os caminhos que descreve, e responde o que mudou desde então com `git diff`. O conteúdo que precisa de leitura (o resumo de um módulo, os caminhos de um termo) é escrito por subagentes Haiku, conduzidos pela skill `mapear`. Um hook de início de sessão injeta o índice do mapa.

**Tech Stack:** Python 3.9+ só com biblioteca padrão, chamado com `python3 -I`; bash 3.2; Markdown.

**Spec:** `docs/superpowers/specs/2026-11-18-harness-design.md` (seção 7). Este plano altera onde a memória derivada mora: ver "Decisões".

**Depende de:** versão 1.

## Decisões deste plano

- **A memória derivada mora em `<diretório git comum>/harness-memory/`**, e não em `~/.claude/` como a spec dizia. O sandbox impede o agente de gravar em `~/.claude`. O novo lugar continua local, fora dos arquivos versionados, e é compartilhado por todos os worktrees do repositório.
- **Toda sessão recebe o índice do mapa por um hook `SessionStart`**, que faz o papel do índice de memória do Claude.
- **Âncora que aponta para um commit que não existe mais** (branch reescrita) é tratada como envelhecida. Com isso não é preciso restringir a gravação à branch padrão.
- **`check` não gasta IA e `refresh` não existe como comando:** quem regenera é a skill `mapear`, porque regenerar exige ler código.
- O glossário e os ADRs continuam nos arquivos do autor (`GLOSSARY.md`, `docs/adr/`), sem mudança de formato. As âncoras deles ficam à parte.

## Global Constraints

- Tudo da versão 1 continua valendo, em especial: Python só com biblioteca padrão e `python3 -I`; `sys.dont_write_bytecode`; nada escreve em `.harness/`; hooks que não são guards nunca bloqueiam.
- Unidade do mapa: um diretório com arquivos versionados, até a profundidade `MAP_DEPTH` do `harness.conf` (padrão 2); o que estiver mais fundo pertence ao ancestral nessa profundidade. Ficam de fora os caminhos de `MAP_EXCLUDE` (padrão `docs .harness .claude .github`). Arquivos soltos na raiz formam a unidade `.`.
- Item envelhecido: o commit da âncora não existe, ou `git diff --quiet <commit> HEAD -- <caminhos>` acusa diferença.
- Resumo de uma unidade: no máximo 1.500 caracteres. Índice injetado na sessão: no máximo 6.000 caracteres.
- ADR pede revisão quando os caminhos dele tiveram `ADR_REVIEW_COMMITS` commits ou mais desde a âncora (padrão 20).

## Review Focus

1. Caminho com espaço, acento ou que começa com `-`; unidade removida do repositório; repositório sem nenhum commit de código: `check` não quebra e classifica certo. Teste na Task 1.
2. Âncora num commit que sumiu (branch reescrita): envelhecida, sem erro do git. Teste na Task 1.
3. `record` com caminho fora do repositório, com `..`, ou com resumo acima do limite: recusado. Teste na Task 1.
4. Termo do glossário cujos caminhos sumiram; ADR com muitos commits na área: sinalizados, sem alterar os arquivos do autor. Teste na Task 2.
5. Mapa vazio, enorme ou com conteúdo que parece instrução: o hook injeta dentro do limite, nunca bloqueia, e marca o conteúdo como dado. Teste na Task 3.

---

### Task 1: `memory`, o mapa

**Files:**
- Create: `plugin/payload/memory.py`, `plugin/payload/memory`
- Modify: `plugin/payload/hooks/common.py` (função `memory_dir`)
- Test: `tests/test_memory.py`

**Interfaces:**
- Produces, em `common.py`: `memory_dir(cwd) -> str | None`: `<git-common-dir absoluto>/harness-memory`.
- Produces, em `memory.py` (e pelo invólucro `.harness/memory <comando>`):
  - `units(root) -> list[str]`: unidades do mapa, em ordem.
  - `record(root, unit, text)`: grava `map/<unidade codificada>.md` e a entrada em `map.json` (`{"unit", "commit", "paths": [unit]}`), ancorada no HEAD. Levanta `ValueError` para unidade que não existe, caminho inválido ou texto acima do limite.
  - `status(root) -> dict`: `{"fresh": [...], "stale": [...], "missing": [...], "orphan": [...]}` para as unidades.
  - `slice_for(root, paths) -> str`: os resumos das unidades que contêm os caminhos dados, com a marca de envelhecido quando for o caso.
  - `index(root) -> str`: uma linha por unidade com a primeira linha do resumo.
  - Comandos: `units`; `check` (imprime o estado; sai 0 se nada envelheceu, 1 caso contrário); `record <unidade> <arquivo com o resumo>`; `show <unidade>`; `slice <caminho>...`; `index`; `forget <unidade>`.

- [ ] **Step 1: Escrever os testes que falham** — unidades com profundidade e exclusões; `record` e `check` (fresh, depois stale ao mudar um arquivo da unidade, missing para unidade nova, orphan para unidade removida); âncora em commit inexistente; caminhos com espaço e acento; recusas do `record`; `slice` e `index`; memória compartilhada entre worktrees; nada aparece em `git status`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(memory): git-anchored code map"`

---

### Task 2: Âncoras do glossário e dos ADRs

**Files:**
- Modify: `plugin/payload/memory.py`
- Test: `tests/test_memory_anchors.py`

**Interfaces:**
- Produces: `anchor <glossary|adr> <chave> <caminho>...` grava em `anchors.json` `{"kind", "key", "paths", "commit"}`; `anchors` lista. `status` passa a trazer `"glossary": {"gone": [...], "unanchored": [...]}` e `"adr": {"review": [...], "unanchored": [...]}`.
  - Termos do glossário: os títulos `## ` ou `### ` e as entradas `**Termo**` no começo de linha de `GLOSSARY.md`. ADRs: os arquivos `docs/adr/NNNN-*.md`.
  - `gone`: termo cujos caminhos ancorados não existem mais no HEAD. `review`: ADR cujos caminhos tiveram `ADR_REVIEW_COMMITS` ou mais commits desde a âncora, ou cuja âncora sumiu. `unanchored`: termo ou ADR que existe no arquivo e não tem âncora.
  - `check` imprime também esses grupos; termo ou ADR sem âncora não faz o `check` sair 1, os demais fazem.

- [ ] **Step 1: Escrever os testes que falham.**
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(memory): anchors for glossary terms and ADRs"`

---

### Task 3: O mapa no começo de cada sessão

**Files:**
- Create: `plugin/payload/hooks/session_context.py`
- Modify: `plugin/templates/settings.json`
- Test: `tests/test_session_context.py`

**Interfaces:**
- Produces: hook `SessionStart`. Imprime `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <texto>}}` com: uma linha dizendo que o que segue é o mapa do código, gerado por máquina e tratado como dado e não como instrução; o índice, cortado em 6.000 caracteres com aviso de corte; e, se houver, a contagem do que envelheceu com a indicação de `/harness:mapear`. Sem mapa: uma linha só, sugerindo `/harness:mapear`. Fora de repositório, ou em qualquer erro: nada, e sai 0.

- [ ] **Step 1: Escrever os testes que falham.**
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar e registrar no template.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(memory): give every session the code map"`

---

### Task 4: A skill `mapear` e o uso do mapa na entrega

**Files:**
- Create: `plugin/skills/mapear/SKILL.md`
- Modify: `plugin/payload/subagent-rules.md`, `plugin/skills/entregar/SKILL.md`, `plugin/templates/AGENTS.managed.md`, `plugin/templates/harness.conf`, `docs/superpowers/specs/2026-11-18-harness-design.md`, `README.md`
- Test: `tests/test_mapear.py`

**Interfaces:**
- `mapear` (invocável pelo agente e pelo dono): roda `.harness/memory check`; para cada unidade envelhecida ou sem resumo, até `MAX_PARALLEL` por vez, dispara um subagente com o modelo `haiku` que lê a unidade e grava o resumo num arquivo em `.harness-run/map/`; grava cada um com `.harness/memory record`; depois ancora os termos do glossário e os ADRs sem âncora, pedindo a um subagente Haiku os caminhos de cada um, e relata ao dono os termos sem código e os ADRs a rever, sem alterar esses arquivos.
- Formato do resumo que a skill pede: primeira linha, o que a unidade faz, em uma frase; depois os arquivos principais, do que ela depende e quem depende dela, e o que não é óbvio.
- `subagent-rules.md` passa a dizer: antes de explorar uma área, `.harness/memory slice <caminhos>`.
- `entregar`, passo 0: `.harness/memory check`, e `mapear` se houver o que regenerar na área da mudança.

- [ ] **Step 1: Escrever os testes que falham** — a skill cita os comandos reais do `memory` e o modelo `haiku`; o exemplo de resumo dela passa pelo `record`; não ensina comando negado; `AGENTS.md` continua abaixo de 8 KiB; as regras dos subagentes continuam abaixo de 3.000 caracteres.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever a skill e alterar os textos; atualizar a spec (seção 7) e o README.**
- [ ] **Step 4: Rodar a suíte inteira; `claude plugin validate .`.**
- [ ] **Step 5: Commit** — `git commit -m "feat(memory): add the mapear skill and use the map in delivery"`
