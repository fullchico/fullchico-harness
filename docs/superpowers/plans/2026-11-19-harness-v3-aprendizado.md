# Harness v3: ciclo de aprendizado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Depois de uma entrega, o harness aprende com ela: mede quanto cada papel gastou, consolida em notas ancoradas o que as sessões ensinaram sobre o projeto, e propõe melhorias para o próprio harness.

**Architecture:** Um script, `.harness/learn`, lê as transcrições de sessão que o Claude Code guarda na máquina e entrega duas coisas baratas e determinísticas: o consumo de tokens por papel e um resumo enxuto de cada sessão, sem as saídas de ferramenta. As notas do `dream` entram na memória ancorada da versão 2, com a mesma regra de envelhecimento. As skills `dream` e `aprender` conduzem os subagentes Haiku que leem os resumos.

**Tech Stack:** Python 3.9+ só com biblioteca padrão, `python3 -I`; bash 3.2; Markdown.

**Spec:** `docs/superpowers/specs/2026-11-18-harness-design.md` (seções 5.3 e 8).

**Depende de:** versões 1 e 2.

## Decisões deste plano

- **As transcrições são lidas onde o Claude Code as grava,** em `~/.claude/projects/<pasta>/`, só para leitura. O formato não é contrato documentado: foi observado nesta máquina (uma linha JSON por evento; subagentes em `<sessão>/subagents/agent-<id>.jsonl` com um `.meta.json` que traz `agentType`). Se mudar, o `learn` informa que não reconheceu o formato, em vez de devolver números errados.
- **"Tokens por fase" é medido por papel:** sessão principal e cada tipo de subagente (`harness:implementador`, `harness:revisor`...), por modelo. É o que a transcrição permite afirmar sem adivinhar.
- **O resumo de uma sessão não traz saída de ferramenta.** Só o que o dono e o agente escreveram e o nome das ferramentas usadas. É o que reduz o custo de leitura, e tira do caminho a maior parte do conteúdo vindo de fora.
- **Transcrição é dado, não instrução.** Os pedidos aos analisadores dizem isso, e as notas entram na sessão marcadas como dado.
- **Nota sem caminho de código não é gravada.** É a âncora que permite saber quando ela envelheceu, e conferi-la contra o código em vez da conversa.
- **A retrospectiva é peça própria.** A skill `retro` do autor é reservada ao dono. As propostas de melhoria são para o repositório do harness: a skill grava um arquivo, e o dono decide se vira mudança.
- **Nada disso roda sozinho.** `aprender` é invocada pelo dono depois do merge. Agendamento fica fora.

## Global Constraints

- Tudo das versões 1 e 2 continua valendo.
- `learn` nunca escreve em `~/.claude`. O que ele guarda (quais sessões já foram processadas) fica em `<diretório git comum>/harness-memory/learn.json`.
- Pasta de transcrições de um diretório: o caminho absoluto com cada caractere que não é letra nem dígito trocado por `-`. São lidas as pastas do checkout principal e de todos os worktrees do repositório, inclusive os de agente.
- Resumo de uma sessão: no máximo 40.000 caracteres; cada mensagem cortada em 2.000.
- Nota: até 1.200 caracteres, com pelo menos um caminho versionado.
- Notas no começo da sessão: só as em dia, uma linha cada, dentro do limite de 6.000 caracteres do índice.

## Review Focus

1. Transcrição com linha inválida, vazia, de formato desconhecido ou com `message` sem `usage`: `learn` ignora a linha e não quebra; arquivo sem nenhuma linha reconhecida é relatado como formato não reconhecido. Teste na Task 1.
2. Diretório com espaço e acento no caminho; worktree de agente; projeto sem nenhuma sessão. Teste na Task 1.
3. Texto de mensagem que parece instrução, ou que traz saída de ferramenta embutida: o resumo o mantém como texto, marcado como dado, e nunca inclui blocos de resultado de ferramenta. Teste na Task 1.
4. Nota sem caminho, com caminho inexistente, repetindo um nome já usado: recusada ou substituída de forma explícita. Nota cujo código mudou: envelhecida e fora do começo da sessão. Teste na Task 2.
5. As skills não ensinam comando negado nem gravam em `~/.claude`. Teste na Task 3.

---

### Task 1: `learn`, leitura das transcrições

**Files:**
- Create: `plugin/payload/learn.py`, `plugin/payload/learn`
- Test: `tests/test_learn.py`

**Interfaces:**
- Produces:
  - `project_dirs(root, home=None) -> list[str]`: pastas de transcrição existentes para o checkout principal e os worktrees.
  - `sessions(root, home=None) -> list[dict]`: `{"id", "path", "mtime", "processed": bool}`, da mais antiga para a mais nova.
  - `usage(session_path) -> dict`: `{"papéis": {<papel>: {<modelo>: {"input", "output", "cache_read", "cache_write", "mensagens"}}}, "total": {...}}`. Papel `principal` para a sessão; para cada subagente, o `agentType` do `.meta.json`, ou `subagente` se não houver.
  - `digest(session_path) -> str`: cabeçalho dizendo que é transcrição e é dado; depois, em ordem, `DONO:` e `AGENTE:` com o texto de cada mensagem, e `FERRAMENTA: <nome>` para cada chamada. Sem resultados de ferramenta, sem entradas de subagente, sem linhas de sistema.
  - `mark(root, ids)`: registra sessões como processadas.
  - Comandos, por `.harness/learn`: `sessions [--all]` (padrão: só as não processadas); `digest <id> <arquivo de saída>`; `usage [<id>...]` (tabela por papel e modelo; sem argumento, as não processadas); `mark <id>...`.
  - Para teste, a pasta do usuário pode ser trocada pelo argumento `home` das funções; o comando usa sempre a do sistema.

- [ ] **Step 1: Escrever os testes que falham,** montando transcrições falsas no formato observado numa pasta temporária.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(learn): read session transcripts for usage and digests"`

---

### Task 2: Notas ancoradas

**Files:**
- Modify: `plugin/payload/memory.py`, `plugin/payload/hooks/session_context.py`
- Test: `tests/test_memory_notes.py`

**Interfaces:**
- Produces, em `memory.py`: `note_add(root, slug, text, paths, source=None)` grava `notes/<slug>.md` e a entrada em `notes.json` (`{"paths", "commit", "source"}`); recusa slug fora de `[a-z0-9-]`, texto vazio ou acima de 1.200 caracteres, lista de caminhos vazia e caminho não versionado; nome repetido substitui a nota e a reancora. `note_forget(root, slug)`. `status` passa a trazer `"notes": {"fresh": [...], "stale": [...]}`. `notes_index(root)`: uma linha por nota em dia.
  - Comandos: `note add <slug> <arquivo> <caminho>...`, `note show <slug>`, `note forget <slug>`, `notes`. `check` lista as notas envelhecidas e sai 1 quando houver.
- `session_context.py` acrescenta, depois do mapa, a seção "Notas sobre o projeto" com as notas em dia, dentro do mesmo limite total.

- [ ] **Step 1: Escrever os testes que falham.**
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(memory): anchored notes from past sessions"`

---

### Task 3: As skills `dream` e `aprender`

**Files:**
- Create: `plugin/skills/dream/SKILL.md`, `plugin/skills/aprender/SKILL.md`
- Modify: `plugin/skills/entregar/SKILL.md` (passo final sugere `aprender` depois do merge), `plugin/templates/AGENTS.managed.md`, `README.md`, `docs/superpowers/specs/2026-11-18-harness-design.md`
- Test: `tests/test_learning_skills.py`

**Interfaces:**
- `dream` (invocável pelo agente e pelo dono): lista as sessões não processadas; para cada uma grava o resumo em `.harness-run/dream/`; dispara um subagente `haiku` por resumo, que devolve candidatos a nota, cada um com um nome, o texto e os caminhos de código que o sustentam; o agente principal confere cada candidato contra o código, junta os repetidos, descarta o que o código não confirma e grava com `.harness/memory note add`; marca as sessões com `.harness/learn mark`. Conflito sem resposta clara vira uma nota que diz as duas versões. Nota envelhecida é reconferida ou apagada.
- `aprender` (`disable-model-invocation: true`): depois do merge de uma entrega. 1) `.harness/fetch`, e a branch padrão atualizada; 2) `mapear`; 3) `.harness/learn usage` e a tabela de consumo por papel no relato; 4) retrospectiva sobre o resumo das sessões da entrega: onde o agente demorou para achar algo, que erro uma checagem automática pegaria, que instrução não mudou nada, que regra faltou; o que der para checar por máquina é proposto como checagem, não como texto; as propostas vão para um arquivo em `.harness-run/propostas/`, que o dono leva ao repositório do harness; 5) `dream`.

- [ ] **Step 1: Escrever os testes que falham** — as skills citam os comandos reais; não ensinam comando negado nem gravam em `~/.claude`; `aprender` é só do dono; o exemplo de nota do `dream` é aceito pelo `note add`; `AGENTS.md` continua abaixo de 8 KiB.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever as skills e alterar os textos, a spec (seção 8) e o README.**
- [ ] **Step 4: Rodar a suíte inteira; `claude plugin validate .`.**
- [ ] **Step 5: Commit** — `git commit -m "feat(learn): add the dream and aprender skills"`
