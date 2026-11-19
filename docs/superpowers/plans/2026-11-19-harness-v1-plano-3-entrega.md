# Harness v1, plano 3: entrega — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dentro do worktree de uma feature, o dono roda `/harness:entregar` e o harness conduz da entrevista ao pull request: spec, revisão da spec, tickets em grafo, implementação em paralelo, checagem, revisão e envio.

**Architecture:** A orquestração é uma skill do plugin, `entregar`, invocada pelo dono e seguida pela sessão principal, que é o elefante. Ela é texto de instrução apoiado em quatro referências (spec, tickets, despacho, fechamento) e em peças determinísticas: um validador do grafo de tickets, o guard do pedido de formato fixo estendido aos implementadores, e um hook que entrega as regras de execução a cada subagente. Os implementadores rodam em worktrees de agente dentro da feature, e o elefante integra o trabalho na branch da feature.

**Tech Stack:** Markdown (skill e agentes), Python 3.9+ só com biblioteca padrão, testes com `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-18-harness-design.md` (seções 5, 6.4 e 9).

**Depende de:** planos 1 e 2, já implementados.

## Decisões deste plano

- **O elefante é a sessão principal seguindo a skill `entregar`.** Não há agente `orquestrador` separado nem chave `agent` nas configurações: a spec previa os dois, mas a skill já é a orquestração, e definir o agente da sessão por plugin não foi confirmado na plataforma.
- **Implementadores trabalham em worktrees de agente** (`isolation: worktree` da ferramenta de subagente), dentro da feature. O ambiente é o da feature (plano 2). O elefante junta cada entrega na branch da feature, na ordem do grafo. É o que evita dois subagentes editando a mesma árvore ao mesmo tempo.
- **O harness entrega um `implementador` genérico.** Projeto com agentes próprios de stack (`backend`, `frontend`) os usa no lugar; a skill escolhe pelo que existir em `.claude/agents/`.
- **O pedido de formato fixo vale também para o `implementador` do harness.** Agentes do projeto não são vigiados pelo guard, mas a skill manda usar o mesmo formato.
- **Espelho do Codex fica fora deste plano.** A barreira do harness é o sandbox do Claude Code; gerar a configuração do Codex sem a barreira equivalente passaria uma segurança que não existe. Fica para um plano próprio, que começa por conferir o sandbox do Codex.
- **Sem teste automático da orquestração em si.** Ela é conduzida por um modelo. Os testes cobrem as peças determinísticas e a coerência entre o que a skill manda escrever e o que os guards aceitam. A validação de ponta a ponta é do dono, numa aplicação de teste.

## Global Constraints

- Tudo dos planos 1 e 2 continua valendo: Python só com biblioteca padrão e chamado com `python3 -I`; hooks `PreToolUse` negam em erro; nada de caminho pessoal em `plugin/`; texto dos agentes e da skill em português.
- A skill e as referências são escritas pelo harness. Não se copia texto das skills de terceiros.
- Skills de terceiros que a `entregar` invoca, só as que o agente pode invocar: `grilling`, `domain-modeling`, `tdd`, `diagnosing-bugs`, `pr`.
- Formato de um ticket: arquivo `docs/specs/<slug>/issues/<NN>-<nome>.md`, `NN` com dois dígitos a partir de `01`. Nas primeiras dez linhas, uma linha `Status: <open|claimed|done>` e uma linha `Blocked by:` seguida de números separados por vírgula, ou vazia.
- Comandos que a skill usa para o remoto e o ambiente: `.harness/fetch`, `.harness/push`, `.harness/pr`, `.harness/up`, `.harness/prepare`, `.harness/dev`, `.harness/validate`. Nunca `git push`, `git fetch` ou `gh` diretos.
- Limite de rodadas de correção por entrega: 3. Escalada de modelo: ticket reprovado 2 vezes passa a Opus.
- `MAX_PARALLEL` no `harness.conf`, padrão 3.

## Review Focus

1. Grafo com ciclo, com referência a ticket inexistente, com número repetido ou com `Status` fora do conjunto: o validador recusa e diz qual ticket. Teste na Task 1.
2. Ticket sem a linha `Blocked by:` ou sem `Status:`: recusado, não tratado como "sem bloqueio". Teste na Task 1.
3. Pedido ao `implementador` com narrativa, ou apontando ticket de outra spec: negado. Teste na Task 2.
4. Os exemplos de pedido que a skill ensina passam pelo guard exatamente como estão escritos. Teste na Task 4.
5. A skill não manda usar nenhum comando que o sandbox ou os guards negam. Teste na Task 4.

---

### Task 1: Validador do grafo de tickets

**Files:**
- Create: `plugin/payload/tickets_check.py`
- Modify: `plugin/payload/validate`
- Test: `tests/test_tickets_check.py`

**Interfaces:**
- Produces:
  - `load(issues_dir: str) -> dict[int, dict]`: por número, `{"path", "status", "blocked_by": list[int]}`. Levanta `ValueError` com mensagem que cita o arquivo.
  - `problems(tickets: dict) -> list[str]`: referência inexistente, auto-referência, ciclo (citando os números do ciclo).
  - `frontier(tickets: dict) -> list[int]`: tickets `open` cujos bloqueadores estão todos `done`, em ordem numérica.
  - Como script: `tickets_check.py <pasta docs/specs/<slug>>`: sai 0 e imprime `ok: N tickets`; ou sai 1 com os problemas em stderr. Com `--frontier`, imprime um caminho de ticket por linha. Pasta sem `issues/`: sai 0 e imprime `ok: 0 tickets`.
  - `validate` passa a rodar o validador para cada `docs/specs/*/` que tenha `issues/`, depois do manifesto.

- [ ] **Step 1: Escrever os testes que falham**

```python
def spec(repo, tickets):   # {"01-a": ("open", ""), "02-b": ("open", "01")} -> docs/specs/x/issues/*.md
class TestTicketsCheck(unittest.TestCase):
    def test_valid_graph_and_frontier(self):       # 01 done, 02 open bloqueado por 01, 03 open por 02, 04 open livre: frontier == [02, 04]
    def test_claimed_and_done_are_not_in_the_frontier(self):
    def test_missing_reference_self_reference_and_cycle(self):   # cada um: 1 problema citando os números
    def test_duplicate_number_bad_name_or_bad_status(self):      # 01-a e 01-b; "1-a.md"; Status: started -> ValueError citando o arquivo
    def test_missing_status_or_blocked_by_line(self):            # ValueError, não "sem bloqueio"
    def test_blocked_by_parsing(self):             # "01, 03", "1,3", vazio, "nenhum" -> ValueError para "nenhum"
    def test_header_lines_only_count_in_the_first_ten(self):     # "Status: done" na linha 40 não vale
    def test_cli(self):                            # ok: 3 tickets; rc 1 com ciclo; --frontier lista caminhos; pasta sem issues/ -> ok: 0 tickets
    def test_validate_rejects_a_broken_graph(self):              # projeto sincronizado com grafo em ciclo: .harness/validate --profile push sai != 0
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `tickets_check.py` e a chamada no `validate`.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(delivery): validate the ticket graph"`

---

### Task 2: Pedido de formato fixo para o implementador

**Files:**
- Modify: `plugin/payload/hooks/dispatch_guard.py`
- Test: `tests/test_dispatch_guard.py`

**Interfaces:**
- Produces: `harness:implementador` entra em `REQUIRED` com `("spec", "ticket")`. Nova chave aceita, só para ele: `achado: <caminho>`, um arquivo existente dentro do projeto. Para ele, `ticket` precisa estar dentro de `<pasta da spec>/issues/`. As chaves `diff` e `commit` continuam aceitas só para os revisores. O registro da base (`record_request`) não muda.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_implementer_gets_spec_and_ticket_only(self):
    ok = "spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-a.md\nleitura: GLOSSARY.md"
    self.assertEqual(self.hook("harness:implementador", ok), 0)
    self.assertEqual(self.hook("harness:implementador", ok + "\nachado: docs/specs/x/issues/01-a.md"), 0)
    for bad in ("spec: docs/specs/x/spec.md",                                   # sem ticket
                ok + "\nFaça com cuidado, o módulo é frágil.",                    # narrativa
                "spec: docs/specs/x/spec.md\nticket: docs/specs/y/issues/01-a.md",  # ticket de outra spec
                "spec: docs/specs/x/spec.md\nticket: GLOSSARY.md",                 # ticket fora de issues/
                ok + "\nachado: /etc/hosts", ok + f"\ncommit: {self.sha}"):
        self.assertEqual(self.hook("harness:implementador", bad), 2, bad)
def test_reviewers_do_not_accept_achado(self): ...
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Alterar `dispatch_guard.py`.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(delivery): pointer-only requests for the implementer"`

---

### Task 3: Regras de execução entregues a cada subagente

**Files:**
- Create: `plugin/payload/hooks/subagent_context.py`, `plugin/payload/subagent-rules.md`
- Modify: `plugin/templates/settings.json`
- Test: `tests/test_subagent_context.py`

**Interfaces:**
- Produces: hook `SubagentStart`. Para `agent_type` que não seja `harness:seguranca`, `harness:revisor` nem `harness:revisor-spec`, imprime `{"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": <texto>}}` com o conteúdo de `subagent-rules.md`. Para os três revisores, e para entrada inválida, não imprime nada e sai 0: revisor recebe só o pedido. Nunca bloqueia.
- `subagent-rules.md`, abaixo de 3.000 caracteres: você é um subagente, sem a conversa; trabalhe só com o que o pedido aponta; lacuna na spec se relata, não se adivinha; teste primeiro, nos pontos de costura da spec (`tdd`); commits de contexto, sem assinatura de IA; não sobe ambiente nem envia ao remoto, isso é do orquestrador; as portas estão no `.env`; termine dizendo o que foi feito, o que ficou de fora e como validar.

- [ ] **Step 1: Escrever os testes que falham**

```python
test_implementers_and_project_agents_get_the_rules     # harness:implementador, backend, general-purpose: JSON com hookEventName SubagentStart e o texto
test_reviewers_get_nothing                             # os três revisores: stdout vazio, rc 0
test_bad_input_is_silent                               # stdin vazio ou inválido: stdout vazio, rc 0
test_rules_fit_and_name_the_boundaries                 # < 3000 caracteres; cita .env, tdd, e que não envia ao remoto
test_settings_register_the_hook                        # settings gerado tem SubagentStart chamando subagent_context.py com python3 -I
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar o hook, escrever as regras e registrar no template.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(delivery): hand execution rules to every subagent"`

---

### Task 4: Agentes e a skill `entregar`

**Files:**
- Create: `plugin/agents/implementador.md`, `plugin/agents/revisor-spec.md`, `plugin/skills/entregar/SKILL.md`, `plugin/skills/entregar/references/spec.md`, `references/tickets.md`, `references/despacho.md`, `references/fechamento.md`
- Modify: `plugin/templates/AGENTS.managed.md`, `plugin/templates/harness.conf`, `plugin/map.json`
- Test: `tests/test_entregar.py`

**Interfaces:**
- Consumes: `tickets_check.py` (Task 1), o formato do pedido (Task 2), os scripts dos planos 1 e 2.

Conteúdo, em português:

- **`implementador`** (`model: sonnet`): recebe `spec:`, `ticket:`, e opcionalmente `leitura:` e `achado:`. Lê os dois documentos; implementa só o ticket, com `tdd` nos pontos de costura da spec; valida sem ambiente quando der; marca o ticket `Status: done` no mesmo conjunto de commits; não envia nem sobe ambiente. Termina com o que fez, o que ficou de fora e como validar.
- **`revisor-spec`** (`model: inherit`, só leitura): recebe `spec:` e `leitura:`. Lê a spec como alguém que vai implementá-la sem poder perguntar. Relata premissa não declarada, requisito ambíguo, decisão que falta, teste sem ponto de costura definido, e risco de implementação, cada um citando o trecho. Não reescreve a spec e não dá veredito: quem resolve é o dono.
- **`SKILL.md`** (`disable-model-invocation: true`): o roteiro em passos numerados, com as duas paradas marcadas. Em cada passo, o que fazer, qual referência ler, e qual comando roda. Antes de tudo: conferir que a sessão está num worktree de feature e não na branch padrão, e rodar `.harness/fetch`.
- **`references/spec.md`**: as seções da spec e o que cada uma precisa responder; os pontos de costura dos testes como parte obrigatória; o que não entra (caminho de arquivo, trecho de código); onde gravar.
- **`references/tickets.md`**: fatia vertical, cada ticket entregável e testável sozinho; o cabeçalho (`Status:`, `Blocked by:`); o corpo (o que entregar, como validar, arquivos prováveis); rodar `tickets_check.py` antes de seguir.
- **`references/despacho.md`**: ler a fronteira com `--frontier`; marcar `claimed`; disparar até `MAX_PARALLEL` implementadores, cada um com `isolation: worktree` e com o pedido de formato fixo; ao voltar cada um, juntar a branch dele na da feature e conferir; repetir até a fronteira esvaziar; rodada de correção com `achado:`; limite de 3 rodadas; subir a Opus depois de 2 reprovações do mesmo ticket.
- **`references/fechamento.md`**: `.harness/validate --profile merge`; ambiente só se a validação exigir (`up`, `prepare`, `dev --background`); disparar `seguranca` e `revisor` em paralelo com `diff:` e `commit:`; em reprovação, voltar ao despacho com o achado; aprovado, `.harness/push`; corpo do PR com a skill `pr` gravado em arquivo; `.harness/pr create`.

- [ ] **Step 1: Escrever os testes que falham**

```python
test_agents_frontmatter                        # implementador: model sonnet; revisor-spec: model inherit e sem Edit/Write nas ferramentas
test_skill_is_user_invoked_and_has_the_two_stops   # disable-model-invocation; cita a aprovação da spec e o limite de rodadas como paradas
test_every_reference_exists_and_is_linked      # os quatro arquivos existem e o SKILL.md aponta para cada um
test_request_examples_pass_the_guard           # extrai dos textos os blocos de pedido (cerca ```pedido) e passa cada um pelo dispatch_guard, num repositório com os caminhos do exemplo: todos aceitos
test_skill_never_teaches_a_denied_command      # nenhum texto da skill ou dos agentes contém "git push", "git fetch", "git pull", "gh pr", "--no-verify", "docker compose up"
test_skill_uses_only_agent_invocable_skills    # skills de terceiros citadas ⊆ {grilling, domain-modeling, tdd, diagnosing-bugs, pr}; não cita to-spec, to-tickets, implement-spec, grill-with-docs
test_ticket_example_passes_tickets_check       # o exemplo de ticket de references/tickets.md, gravado em arquivos, passa no validador
test_agents_md_still_fits                      # AGENTS.md gerado continua abaixo de 8 KiB e cita /harness:entregar
test_conf_template_documents_max_parallel
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever os agentes, a skill e as referências; atualizar os templates e o mapa.**
- [ ] **Step 4: Rodar e ver passar; `claude plugin validate .`; rodar a suíte inteira.**
- [ ] **Step 5: Commit** — `git commit -m "feat(delivery): add the entregar skill and its agents"`

---

### Task 5: Alinhar a spec e o guia de uso

**Files:**
- Modify: `docs/superpowers/specs/2026-11-18-harness-design.md` (seções 4.2, 5 e 13)
- Create: `README.md`

- [ ] **Step 1: Atualizar a spec** com o que este plano decidiu: sem agente `orquestrador`, worktrees de agente para os implementadores, `implementador` genérico, Codex adiado.
- [ ] **Step 2: Escrever o `README.md`**: o que é; instalar num projeto (`claude plugin marketplace add`, `/harness:setup`); o que muda no dia a dia (sandbox, os comandos `.harness/*`, as perguntas que o dono recebe); o roteiro de uma primeira entrega com `/harness:entregar`; o que ainda não foi verificado em sessão interativa, como lista para a primeira validação do dono.
- [ ] **Step 3: Rodar a suíte inteira.**
- [ ] **Step 4: Commit** — `git commit -m "docs: align the spec with the delivery plan and add a usage guide"`
