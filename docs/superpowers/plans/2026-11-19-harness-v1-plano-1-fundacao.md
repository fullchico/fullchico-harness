# Harness v1, plano 1: fundação (plugin, sync e portões) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um projeto consegue adotar o harness com um comando e passa a ter os dois portões de push, a trava de spec, o bloqueio de autoaprovação e a proteção dos arquivos gerenciados.

**Architecture:** Este repositório é um marketplace do Claude Code com um plugin (`plugin/`). O plugin carrega agentes, skills, templates e um `payload/` que o `bin/sync` copia para `.harness/` do projeto, gravando um manifesto de hashes. Os guardrails são hooks em Python dentro de `.harness/hooks/` e hooks de git em `.harness/git-hooks/`; o estado das aprovações fica no diretório git comum a todos os worktrees.

**Tech Stack:** Python 3.9+ só com biblioteca padrão (hooks, `sync`, testes com `unittest`); bash compatível com 3.2 (scripts e hooks de git); git.

**Spec:** `docs/superpowers/specs/2026-11-18-harness-design.md` (seções 4, 6, 10 e 12).

**Planos seguintes da v1, fora deste:** plano 2, ambiente por worktree (`worktree-env`, `up`, `dev`, `down`, `destroy`, regras de serviço do `service-guard`, Orca e Conductor); plano 3, entrega (`orquestrador`, `revisor-spec`, skill `entregar`, validação do grafo, espelho do Codex).

## Global Constraints

- Nome do plugin: `harness`. Nome do marketplace: `fullchico`. Repositório: `FullChico/fullchico-harness`. Licença MIT.
- Repositório público: nada de caminho pessoal, segredo ou nome de projeto do dono em `plugin/`.
- Python: só biblioteca padrão, compatível com 3.9. Bash: compatível com 3.2 (macOS). Sem `jq` neste plano.
- Todo caminho é tratado com espaços (o diretório de dados do dono contém "Application Support").
- Hook `PreToolUse`: qualquer exceção ou entrada inválida vira negação (exit 2 com o motivo em stderr), nunca liberação. Hook `SubagentStop` (`gate_stamp`): sempre exit 0 e nunca bloqueia; na dúvida, não carimba.
- Hooks de agente usam o `cwd` do JSON de entrada, não `$CLAUDE_PROJECT_DIR`, para achar o worktree.
- Estado dos portões: `$(git rev-parse --path-format=absolute --git-common-dir)/harness/`.
- Nomes de portão: `seguranca` e `revisao`. Agentes: `seguranca` e `revisor`; em hooks o `agent_type` chega como `harness:seguranca` e `harness:revisor`.
- Commits deste repositório: `tipo(escopo): descrição` em inglês, até 80 caracteres, corpo livre; sem co-autoria nem assinatura de IA.
- Rodar todos os testes: `python3 -m unittest discover -s tests -v`.

## Review Focus

1. Push de branch nova, sem `origin/HEAD` configurado e com sha remoto zerado: o `pre-push` deve achar a base (cai para `main`) e aplicar as regras, sem erro de git. Teste na Task 8.
2. Entrada de hook vazia ou JSON inválido: guards negam; `gate_stamp` sai 0 sem carimbar. Testes nas Tasks 3, 4, 5 e 6.
3. Projeto em caminho com espaços: `sync`, `approve`, `pre-push` e `update` funcionam. Testes nas Tasks 7, 8 e 9, que criam o repositório temporário num diretório com espaço no nome.
4. Aprovação carimbada num worktree vale para push feito de outro worktree do mesmo repositório. Teste na Task 3.
5. Mensagem de revisor com veredito ambíguo (os dois valores, veredito citado no meio de uma frase, minúsculas, `COMMIT` de outro hash): não carimba. Testes na Task 3.

---

## Estrutura de arquivos

```
.claude-plugin/marketplace.json
LICENSE
plugin/.claude-plugin/plugin.json
plugin/map.json
plugin/agents/seguranca.md
plugin/agents/revisor.md
plugin/skills/setup/SKILL.md
plugin/bin/sync                         Python, executável
plugin/payload/hooks/common.py          leitura de payload, estado, conf, negação
plugin/payload/hooks/gate_stamp.py      SubagentStop
plugin/payload/hooks/service_guard.py   PreToolUse Bash (neste plano: só proteção dos portões)
plugin/payload/hooks/dispatch_guard.py  PreToolUse Agent
plugin/payload/hooks/managed_guard.py   PreToolUse Edit|Write
plugin/payload/manifest_check.py        confere MANIFEST
plugin/payload/approve                  bash, carimbo manual do dono
plugin/payload/validate                 bash
plugin/payload/update                   bash
plugin/payload/git-hooks/commit-msg     bash
plugin/payload/git-hooks/pre-push       bash
plugin/templates/settings.json
plugin/templates/AGENTS.managed.md
plugin/templates/AGENTS.project.md
plugin/templates/CLAUDE.md
plugin/templates/harness.conf
plugin/templates/docs/agents/domain.md
plugin/templates/docs/agents/issue-tracker.md
tests/helpers.py                        repositório git temporário, execução de hook
tests/test_*.py
```

---

### Task 1: Esqueleto do marketplace e do plugin

**Files:**
- Create: `.claude-plugin/marketplace.json`, `plugin/.claude-plugin/plugin.json`, `plugin/map.json`, `LICENSE`, `tests/helpers.py`, `tests/test_manifests.py`

**Interfaces:**
- Produces: `tests/helpers.py` com
  - `make_repo(name="proj dir") -> pathlib.Path`: cria num diretório temporário um repositório git com um commit inicial na branch `main`, `user.name` e `user.email` configurados, num caminho que contém espaço. Registra limpeza.
  - `git(repo, *args) -> str`: roda git no repositório, devolve stdout sem a quebra final, levanta em erro.
  - `run_hook(script: str, payload, cwd=None, raw=None) -> tuple[int, str, str]`: executa `python3 plugin/payload/hooks/<script>` com `payload` em JSON no stdin (ou `raw` como texto cru); devolve `(exit, stdout, stderr)`.
  - `write_tmp(text: str) -> str`: grava o texto num arquivo temporário e devolve o caminho. Registra limpeza.
  - `ROOT`: `pathlib.Path` da raiz deste repositório.
  - As Tasks 7, 8 e 9 acrescentam a este arquivo `sync`, `commit_file`, `commit_all` e `clone_self_with_tags`, com as assinaturas dadas nelas. Os testes importam esses nomes daqui.
- Produces: `plugin/map.json` com as chaves `spec_glob: "docs/specs/*/spec.md"`, `tickets_glob: "docs/specs/*/issues/*.md"`, `sources` (marketplaces e plugins de terceiros com `ref`) e `steps` (lista de `{step, skill, source, adaptation}`), com o conteúdo da tabela da seção 9 da spec.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_manifests.py
class TestManifests(unittest.TestCase):
    def test_marketplace_points_to_plugin(self):
        m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(m["name"], "fullchico")
        self.assertTrue(m["owner"]["name"])
        self.assertEqual(m["plugins"][0]["name"], "harness")
        self.assertEqual(m["plugins"][0]["source"], "./plugin")

    def test_plugin_manifest(self):
        p = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
        self.assertEqual(p["name"], "harness")
        self.assertRegex(p["version"], r"^\d+\.\d+\.\d+$")

    def test_map_has_spec_paths_and_only_agent_invocable_cycle_skills(self):
        m = json.loads((ROOT / "plugin/map.json").read_text())
        self.assertEqual(m["spec_glob"], "docs/specs/*/spec.md")
        self.assertEqual(m["tickets_glob"], "docs/specs/*/issues/*.md")
        cycle = {s["skill"] for s in m["steps"] if s["step"] != "avulsa-dono"}
        self.assertTrue({"grilling", "domain-modeling", "tdd", "pr"} <= cycle)
        self.assertFalse(cycle & {"to-spec", "to-tickets", "implement-spec", "grill-with-docs"})

    def test_no_personal_paths_in_plugin(self):
        for f in (ROOT / "plugin").rglob("*"):
            if f.is_file():
                text = f.read_text(errors="ignore")
                self.assertNotIn("/Users/", text, f)
                self.assertNotIn("movacrm", text.lower(), f)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python3 -m unittest tests.test_manifests -v`
Expected: FAIL (arquivos não existem).

- [ ] **Step 3: Criar os manifestos, o `map.json`, a `LICENSE` (MIT) e o `tests/helpers.py`**

Versão inicial do plugin: `0.1.0`.

- [ ] **Step 4: Rodar e ver passar; validar com a ferramenta oficial**

Run: `python3 -m unittest tests.test_manifests -v` → PASS
Run: `claude plugin validate .` → sem erros.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin plugin LICENSE tests
git commit -m "feat(plugin): add marketplace and plugin skeleton"
```

---

### Task 2: `common.py`, base dos hooks

**Files:**
- Create: `plugin/payload/hooks/common.py`
- Test: `tests/test_common.py`

**Interfaces:**
- Produces:
  - `read_payload() -> dict`: lê JSON do stdin; devolve `{}` se vazio ou inválido.
  - `deny(reason: str) -> NoReturn`: escreve `reason` em stderr e sai com 2.
  - `repo_root(cwd: str) -> str | None`: raiz do worktree (`git rev-parse --show-toplevel`), ou `None` fora de git.
  - `state_dir(cwd: str) -> str | None`: `<git-common-dir absoluto>/harness`, ou `None` fora de git. Não cria o diretório.
  - `head_sha(cwd: str) -> str | None`: `git rev-parse HEAD`.
  - `read_conf(path: str) -> dict[str, str]`: lê `harness.conf`: linhas `CHAVE=valor`, ignora vazias e `#`, remove um par de aspas simples ou duplas em volta do valor, não expande variáveis. Arquivo ausente devolve `{}`.
  - `approval_path(state: str, gate: str, sha: str) -> str`: `<state>/approvals/<gate>/<sha>.json`.
  - `GATES = ("seguranca", "revisao")`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestCommon(unittest.TestCase):
    def test_state_dir_is_shared_between_worktrees(self):
        repo = make_repo()
        wt = repo.parent / "wt two"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "other")
        self.assertEqual(common.state_dir(str(repo)), common.state_dir(str(wt)))
        self.assertTrue(common.state_dir(str(repo)).endswith("/.git/harness"))

    def test_outside_git_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(common.state_dir(d))
            self.assertIsNone(common.repo_root(d))

    def test_read_conf(self):
        f = write_tmp('PROJECT=meuapp\n# c\n\nSERVICES="web api"\nA=\'x y\'\nB=${X}/y\n')
        self.assertEqual(common.read_conf(f),
                         {"PROJECT": "meuapp", "SERVICES": "web api", "A": "x y", "B": "${X}/y"})
        self.assertEqual(common.read_conf("/nao/existe"), {})

    def test_approval_path(self):
        self.assertEqual(common.approval_path("/s", "revisao", "abc"), "/s/approvals/revisao/abc.json")
```

- [ ] **Step 2: Rodar e ver falhar** — `python3 -m unittest tests.test_common -v` → FAIL (módulo não existe).
- [ ] **Step 3: Implementar `common.py`** com as assinaturas acima.
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(hooks): add shared hook helpers"`

---

### Task 3: `gate_stamp.py`, o carimbo automático

**Files:**
- Create: `plugin/payload/hooks/gate_stamp.py`
- Test: `tests/test_gate_stamp.py`

**Interfaces:**
- Consumes: `common` (Task 2).
- Produces:
  - `parse_verdict(message: str) -> dict | None`: devolve `{"verdict", "commit", "resumo"}` só se a mensagem tiver, cada uma como linha inteira: exatamente uma linha `VEREDITO: APPROVED` ou `VEREDITO: REJECTED` (maiúsculas), exatamente uma `COMMIT: <40 hex>`, e uma `RESUMO: <texto não vazio>`. Qualquer outra forma devolve `None`.
  - `gate_for(agent_type: str) -> str | None`: `harness:seguranca` → `seguranca`; `harness:revisor` → `revisao`; qualquer outro → `None`. Sem prefixo de plugin também devolve `None`.
  - Execução como script: lê o payload de `SubagentStop`; campos usados: `agent_type`, `last_assistant_message`, `agent_transcript_path`, `cwd`.
  - Arquivo de aprovação (JSON): `{"gate", "sha", "status": "PASS", "resumo", "by": "hook", "agent_type", "transcript", "timestamp"}` (timestamp UTC ISO 8601).

Regras: carimba só se `gate_for` devolver portão, o veredito for `APPROVED` e `commit == head_sha(cwd)`. Veredito `REJECTED` válido para o HEAD atual apaga a aprovação existente daquele portão e hash. Em qualquer outro caso não faz nada. Sempre exit 0.

- [ ] **Step 1: Escrever os testes que falham**

```python
def payload(repo, agent="harness:seguranca", msg=None, sha=None):
    sha = sha or git(repo, "rev-parse", "HEAD")
    msg = msg if msg is not None else f"Revisado.\nVEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: sem achados"
    return {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(repo),
            "last_assistant_message": msg, "agent_transcript_path": "/t.jsonl"}

def stamped(repo, gate):
    sha = git(repo, "rev-parse", "HEAD")
    return os.path.exists(common.approval_path(common.state_dir(str(repo)), gate, sha))

class TestGateStamp(unittest.TestCase):
    def test_approved_stamps_the_gate_of_that_agent(self):
        repo = make_repo()
        self.assertEqual(run_hook("gate_stamp.py", payload(repo))[0], 0)
        self.assertTrue(stamped(repo, "seguranca")); self.assertFalse(stamped(repo, "revisao"))
        run_hook("gate_stamp.py", payload(repo, agent="harness:revisor"))
        self.assertTrue(stamped(repo, "revisao"))

    def test_approval_file_content(self):
        repo = make_repo(); run_hook("gate_stamp.py", payload(repo))
        sha = git(repo, "rev-parse", "HEAD")
        a = json.load(open(common.approval_path(common.state_dir(str(repo)), "seguranca", sha)))
        self.assertEqual((a["gate"], a["sha"], a["status"], a["by"], a["resumo"], a["agent_type"]),
                         ("seguranca", sha, "PASS", "hook", "sem achados", "harness:seguranca"))

    def test_never_stamps(self):
        repo = make_repo(); sha = git(repo, "rev-parse", "HEAD")
        cases = [
            payload(repo, agent="general-purpose"),
            payload(repo, agent="seguranca"),                      # sem prefixo do plugin
            payload(repo, agent="outro:seguranca"),
            payload(repo, msg=f"VEREDITO: REJECTED\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nCOMMIT: {'0'*40}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: "),
            payload(repo, msg=f"veredito: approved\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"o texto diz VEREDITO: APPROVED aqui\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nVEREDITO: REJECTED\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nRESUMO: x"),
        ]
        for p in cases:
            self.assertEqual(run_hook("gate_stamp.py", p)[0], 0)
            self.assertFalse(stamped(repo, "seguranca"), p["last_assistant_message"])

    def test_bad_input_exits_zero_without_stamping(self):
        self.assertEqual(run_hook("gate_stamp.py", None, raw="")[0], 0)
        self.assertEqual(run_hook("gate_stamp.py", None, raw="{nao json")[0], 0)

    def test_rejected_removes_existing_approval(self):
        repo = make_repo(); sha = git(repo, "rev-parse", "HEAD")
        run_hook("gate_stamp.py", payload(repo)); self.assertTrue(stamped(repo, "seguranca"))
        run_hook("gate_stamp.py", payload(repo, msg=f"VEREDITO: REJECTED\nCOMMIT: {sha}\nRESUMO: achei x"))
        self.assertFalse(stamped(repo, "seguranca"))

    def test_stamp_in_one_worktree_is_visible_from_another(self):
        repo = make_repo(); wt = repo.parent / "wt two"
        git(repo, "worktree", "add", "-q", "--detach", str(wt))
        run_hook("gate_stamp.py", payload(wt))
        self.assertTrue(stamped(repo, "seguranca"))
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `gate_stamp.py`.**
- [ ] **Step 4: Rodar e ver passar** — `python3 -m unittest tests.test_gate_stamp -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(gates): stamp approvals from reviewer verdicts"`

---

### Task 4: `approve` do dono e proteção dos portões no `service_guard.py`

**Files:**
- Create: `plugin/payload/approve`, `plugin/payload/hooks/service_guard.py`
- Test: `tests/test_approve.py`, `tests/test_service_guard_gates.py`

**Interfaces:**
- Consumes: `common` (Task 2); formato do arquivo de aprovação (Task 3).
- Produces:
  - `approve <seguranca|revisao> "<resumo>"`: grava a aprovação do HEAD atual com `"by": "owner"`, `"agent_type": null`. Resumo vazio ou portão inválido: exit 1 com uso em stderr. Fora de git: exit 1.
  - `service_guard.py`: `classify(command: str, state: str | None) -> str | None` devolve o motivo da negação ou `None`. Execução como script: `PreToolUse` com `tool_name == "Bash"`; nega com exit 2.

Regras de negação deste plano (o plano 2 acrescenta as de serviço no mesmo arquivo):
1. o comando cita o diretório de estado (caminho absoluto resolvido, ou o trecho `/harness/approvals`);
2. algum token do comando termina em `.harness/approve`, `hooks/gate_stamp.py` ou é `approve` logo após um `cd` para `.harness`;
3. o comando contém `--no-verify`, `core.hooksPath` ou `HUSKY=`.
Comando que só lê arquivos com esses nomes como texto de busca (`grep approve`, `git log --grep=no-verify`) também é negado: falso positivo aqui é aceitável, porque são nomes que um agente não tem motivo para tocar.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestApprove(unittest.TestCase):
    def test_owner_stamp(self):
        repo = make_repo(); sha = git(repo, "rev-parse", "HEAD")
        r = subprocess.run([str(ROOT / "plugin/payload/approve"), "revisao", "li o diff"],
                           cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = json.load(open(common.approval_path(common.state_dir(str(repo)), "revisao", sha)))
        self.assertEqual((a["by"], a["status"], a["resumo"]), ("owner", "PASS", "li o diff"))

    def test_rejects_bad_usage(self):
        repo = make_repo()
        for args in (["revisao", ""], ["revisao", "   "], ["quality", "x"], []):
            r = subprocess.run([str(ROOT / "plugin/payload/approve"), *args], cwd=repo, capture_output=True)
            self.assertEqual(r.returncode, 1, args)

class TestServiceGuardGates(unittest.TestCase):
    def hook(self, repo, command):
        return run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(repo),
                                             "tool_input": {"command": command}})[0]
    def test_denies(self):
        repo = make_repo(); state = common.state_dir(str(repo))
        for c in ['.harness/approve seguranca "ok"', 'bash .harness/approve revisao x',
                  'cd .harness && ./approve revisao x', f'echo x > "{state}/approvals/revisao/a.json"',
                  'ls .git/harness/approvals', 'python3 .harness/hooks/gate_stamp.py < p.json',
                  'git push --no-verify', 'git -c core.hooksPath=/dev/null push', 'HUSKY=0 git push']:
            self.assertEqual(self.hook(repo, c), 2, c)
    def test_allows(self):
        repo = make_repo()
        for c in ['git status', 'git push origin feat/x', 'ls .harness', 'cat .harness/MANIFEST',
                  'python3 -m unittest', 'git commit -m "feat: add approval flow"']:
            self.assertEqual(self.hook(repo, c), 0, c)
    def test_bad_input_denies(self):
        self.assertEqual(run_hook("service_guard.py", None, raw="{x")[0], 2)
        self.assertEqual(run_hook("service_guard.py", {"tool_name": "Bash", "tool_input": {}})[0], 2)
    def test_other_tools_pass(self):
        self.assertEqual(run_hook("service_guard.py", {"tool_name": "Read", "tool_input": {}})[0], 0)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `approve` (bash) e `service_guard.py`.** Tokenizar com `shlex` usando `punctuation_chars=True`, para enxergar `;`, `&&` e `|` colados ao texto; se a tokenização falhar, negar.
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(gates): add owner stamp and guard gate state from agents"`

---

### Task 5: `dispatch_guard.py`, o pedido de formato fixo

**Files:**
- Create: `plugin/payload/hooks/dispatch_guard.py`
- Test: `tests/test_dispatch_guard.py`

**Interfaces:**
- Consumes: `common` (Task 2).
- Produces: `check(agent: str, prompt: str, root: str) -> str | None` (motivo da negação ou `None`). Execução como script: `PreToolUse` com `tool_name` `Agent` ou `Task`; lê `tool_input.subagent_type` e `tool_input.prompt`.

Regras: só se aplica quando `subagent_type` é `harness:seguranca`, `harness:revisor` ou `harness:revisor-spec`; qualquer outro agente passa. Para esses três, toda linha não vazia do prompt precisa casar `^(spec|ticket|diff|commit|leitura): \S.*$`. Obrigatórios: `diff` e `commit` para `seguranca` e `revisor`; `spec` para `revisor-spec`. `spec` e `ticket` precisam ser caminhos relativos existentes dentro de `root`; `leitura` é lista separada por vírgula de caminhos relativos existentes; `commit` são 40 hex; `diff` casa `^[\w./-]+\.\.\.?[\w./-]+$`. Caminho absoluto ou com `..` é negado.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestDispatchGuard(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo(); (self.repo / "docs/specs/x").mkdir(parents=True)
        (self.repo / "docs/specs/x/spec.md").write_text("s"); (self.repo / "GLOSSARY.md").write_text("g")
        self.sha = git(self.repo, "rev-parse", "HEAD")
    def hook(self, agent, prompt):
        return run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo),
                        "tool_input": {"subagent_type": agent, "prompt": prompt}})[0]
    def test_fixed_format_passes(self):
        ok = f"diff: main...HEAD\ncommit: {self.sha}\nspec: docs/specs/x/spec.md\nleitura: GLOSSARY.md"
        self.assertEqual(self.hook("harness:revisor", ok), 0)
        self.assertEqual(self.hook("harness:seguranca", f"diff: main...HEAD\ncommit: {self.sha}"), 0)
        self.assertEqual(self.hook("harness:revisor-spec", "spec: docs/specs/x/spec.md"), 0)
    def test_narrative_is_denied(self):
        base = f"diff: main...HEAD\ncommit: {self.sha}"
        for extra in ["Acho que está bom, só confirme.", "nota: foco no módulo de auth", "spec: nao/existe.md",
                      "spec: /etc/passwd", "spec: ../fora.md", "leitura: GLOSSARY.md, nao/existe.md"]:
            self.assertEqual(self.hook("harness:revisor", base + "\n" + extra), 2, extra)
    def test_required_keys(self):
        self.assertEqual(self.hook("harness:revisor", "spec: docs/specs/x/spec.md"), 2)
        self.assertEqual(self.hook("harness:revisor-spec", f"commit: {self.sha}"), 2)
        self.assertEqual(self.hook("harness:seguranca", "diff: main...HEAD\ncommit: abc"), 2)
    def test_other_agents_are_free(self):
        self.assertEqual(self.hook("general-purpose", "faça o que quiser, com narrativa"), 0)
        self.assertEqual(self.hook("backend", "implemente o ticket 3"), 0)
    def test_bad_input_denies(self):
        self.assertEqual(run_hook("dispatch_guard.py", None, raw="")[0], 2)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `dispatch_guard.py`.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(hooks): enforce pointer-only prompts to reviewer agents"`

---

### Task 6: `managed_guard.py`, a região gerenciada do `AGENTS.md`

**Files:**
- Create: `plugin/payload/hooks/managed_guard.py`
- Test: `tests/test_managed_guard.py`

**Interfaces:**
- Consumes: `common` (Task 2).
- Produces:
  - `BEGIN = "<!-- harness:begin -->"`, `END = "<!-- harness:end -->"`.
  - `region(text: str) -> str | None`: o texto entre os marcadores, inclusive eles; `None` se faltar algum ou estiverem fora de ordem.
  - Execução como script: `PreToolUse` com `tool_name` `Edit` ou `Write`. `Edit` traz `file_path`, `old_string`, `new_string`, `replace_all`; `Write` traz `file_path`, `content`.

Regras: só age quando `file_path` resolve para `<repo_root>/AGENTS.md`. Calcula o conteúdo resultante (para `Edit`, aplica a troca em memória) e nega se `region(antes) != region(depois)`. Arquivo ainda inexistente, ou sem região: passa. Os demais arquivos gerenciados são protegidos por `permissions.deny` no `settings.json` gerado (Task 7), não por este hook.

- [ ] **Step 1: Escrever os testes que falham**

```python
DOC = "# Proj\n\nlivre antes\n\n<!-- harness:begin -->\nregra 1\n<!-- harness:end -->\n\nlivre depois\n"

class TestManagedGuard(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo(); (self.repo / "AGENTS.md").write_text(DOC)
        self.f = str(self.repo / "AGENTS.md")
    def edit(self, old, new, path=None, replace_all=False):
        return run_hook("managed_guard.py", {"tool_name": "Edit", "cwd": str(self.repo), "tool_input":
            {"file_path": path or self.f, "old_string": old, "new_string": new, "replace_all": replace_all}})[0]
    def write(self, content):
        return run_hook("managed_guard.py", {"tool_name": "Write", "cwd": str(self.repo),
                        "tool_input": {"file_path": self.f, "content": content}})[0]
    def test_project_region_is_free(self):
        self.assertEqual(self.edit("livre antes", "produto X"), 0)
        self.assertEqual(self.write(DOC.replace("livre depois", "onde olhar")), 0)
    def test_managed_region_is_denied(self):
        self.assertEqual(self.edit("regra 1", "regra 2"), 2)
        self.assertEqual(self.edit("<!-- harness:end -->", ""), 2)
        self.assertEqual(self.write("# Proj\nsem região\n"), 2)
        self.assertEqual(self.edit("r", "R", replace_all=True), 2)
    def test_other_files_pass(self):
        self.assertEqual(self.edit("a", "b", path=str(self.repo / "src/x.py")), 0)
        self.assertEqual(self.edit("a", "b", path=str(self.repo / "docs/AGENTS.md")), 0)
    def test_bad_input_denies(self):
        self.assertEqual(run_hook("managed_guard.py", None, raw="{")[0], 2)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `managed_guard.py`.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(hooks): protect the managed region of AGENTS.md"`

---

### Task 7: `bin/sync`, templates e manifesto

**Files:**
- Create: `plugin/bin/sync`, `plugin/payload/manifest_check.py`, `plugin/templates/settings.json`, `plugin/templates/AGENTS.managed.md`, `plugin/templates/AGENTS.project.md`, `plugin/templates/CLAUDE.md`, `plugin/templates/harness.conf`, `plugin/templates/docs/agents/domain.md`, `plugin/templates/docs/agents/issue-tracker.md`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `plugin/map.json` (Task 1); `managed_guard.region` e marcadores (Task 6).
- Produces:
  - `sync <project_dir> --version <tag> [--force]`. Exit 0 ok; 1 se algum arquivo gerenciado foi alterado à mão em relação ao `MANIFEST` existente e `--force` não foi passado (lista os arquivos em stderr e não escreve nada); 2 em uso inválido ou `project_dir` fora de git.
  - `.harness/MANIFEST` (JSON): `{"version": "<tag>", "files": {"<caminho relativo>": "<sha256>"}, "regions": {"AGENTS.md": "<sha256 da região>"}}`.
  - `.harness/map.env`: `SPEC_GLOB=docs/specs/*/spec.md` e `TICKETS_GLOB=docs/specs/*/issues/*.md`, lidos do `map.json`.
  - `python3 .harness/manifest_check.py [project_dir]`: exit 0 se tudo bate com o `MANIFEST`; exit 1 listando em stdout os caminhos divergentes ou ausentes, um por linha.

O que o `sync` faz, nesta ordem: copia `payload/` para `.harness/` preservando o bit de execução; grava `map.env`; gera `.claude/settings.json` (template, com `ref` igual à versão, somado ao fragmento `harness.d/settings.json` se existir); gera `CLAUDE.md` e `docs/agents/*`; no `AGENTS.md`, troca só a região entre marcadores por `AGENTS.managed.md` (se o arquivo não existir, cria com a região seguida de `AGENTS.project.md`; se existir sem marcadores, insere a região no topo e mantém o resto); cria `harness.conf` a partir do template só se não existir; roda `git config core.hooksPath .harness/git-hooks`; grava o `MANIFEST`. Nunca escreve em `harness.conf` existente, `harness.d/`, `CLAUDE.local.md` nem fora da região do `AGENTS.md`.

Soma do fragmento: dicionários são fundidos recursivamente, listas são concatenadas com as do template primeiro. `permissions.deny` e `hooks` do template sempre aparecem inteiros no resultado.

`templates/settings.json` contém: `extraKnownMarketplaces` (`fullchico` com `ref`, `ponytail`), `enabledPlugins` (`harness@fullchico`, `mattpocock-skills@claude-plugins-official`, `ponytail@ponytail`), `hooks` (PreToolUse `Bash` → `service_guard.py` e depois `rtk hook claude`; PreToolUse `Agent|Task` → `dispatch_guard.py`; PreToolUse `Edit|Write` → `managed_guard.py`; SubagentStop com matcher `^harness:(seguranca|revisor)$` → `gate_stamp.py`), todos chamados como `python3 "$CLAUDE_PROJECT_DIR/.harness/hooks/<arquivo>"`, e `permissions.deny` com `Edit(/.harness/**)`, `Edit(/.claude/settings.json)`, `Edit(/CLAUDE.md)`, `Edit(/docs/agents/**)`, `Edit(/harness.conf)`, `Edit(/harness.d/**)`.

`templates/harness.conf` traz todas as chaves da seção 10.4 da spec como comentário, com um exemplo cada, e nenhuma ativa: projeto recém-configurado não roda comando de validação que ele não declarou.

`AGENTS.project.md` traz os títulos `## Produto` e `## Onde olhar`, vazios.

`AGENTS.managed.md` traz, em português: os papéis e as três regras (spec 5.1), a tabela do ciclo (5.2), os portões e a trava de spec (6.1 e 6.2), o contrato de veredito (`VEREDITO`, `COMMIT`, `RESUMO`), e a convenção de commits de contexto (7.1). Abaixo de 8 KiB.

- [ ] **Step 1: Escrever os testes que falham**

```python
# em tests/helpers.py
def sync(repo, *extra):
    return subprocess.run([sys.executable, str(ROOT / "plugin/bin/sync"), str(repo), "--version", "v0.1.0", *extra],
                          capture_output=True, text=True)

class TestSync(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo(); r = sync(self.repo); self.assertEqual(r.returncode, 0, r.stderr)
    def test_layout(self):
        for p in [".harness/hooks/gate_stamp.py", ".harness/git-hooks/pre-push", ".harness/approve",
                  ".harness/MANIFEST", ".harness/map.env", ".claude/settings.json", "CLAUDE.md",
                  "AGENTS.md", "harness.conf", "docs/agents/issue-tracker.md", "docs/agents/domain.md"]:
            self.assertTrue((self.repo / p).exists(), p)
        self.assertTrue(os.access(self.repo / ".harness/git-hooks/pre-push", os.X_OK))
        self.assertEqual(git(self.repo, "config", "core.hooksPath"), ".harness/git-hooks")
    def test_settings_pins_version_and_denies_managed_edits(self):
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(s["extraKnownMarketplaces"]["fullchico"]["source"]["ref"], "v0.1.0")
        self.assertTrue(s["enabledPlugins"]["harness@fullchico"])
        for rule in ["Edit(/.harness/**)", "Edit(/harness.conf)", "Edit(/harness.d/**)", "Edit(/.claude/settings.json)"]:
            self.assertIn(rule, s["permissions"]["deny"])
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", json.dumps(s))
    def test_manifest_check_clean_then_detects_drift(self):
        chk = lambda: subprocess.run([sys.executable, str(self.repo / ".harness/manifest_check.py"), str(self.repo)],
                                     capture_output=True, text=True)
        self.assertEqual(chk().returncode, 0)
        (self.repo / ".harness/approve").write_text("#!/bin/sh\nexit 0\n")
        r = chk(); self.assertEqual(r.returncode, 1); self.assertIn(".harness/approve", r.stdout)
    def test_agents_md_region_only(self):
        f = self.repo / "AGENTS.md"
        f.write_text(f.read_text().replace("## Produto", "## Produto\n\nmeu texto de projeto"))
        self.assertEqual(sync(self.repo).returncode, 0)
        self.assertIn("meu texto de projeto", f.read_text())
        self.assertIsNotNone(managed_guard.region(f.read_text()))
    def test_existing_agents_md_without_markers_is_kept(self):
        repo = make_repo(); (repo / "AGENTS.md").write_text("# Antigo\n\nconteúdo do projeto\n")
        self.assertEqual(sync(repo).returncode, 0)
        text = (repo / "AGENTS.md").read_text()
        self.assertIn("conteúdo do projeto", text); self.assertIsNotNone(managed_guard.region(text))
    def test_manual_drift_blocks_resync_unless_forced(self):
        (self.repo / "CLAUDE.md").write_text("mexi à mão\n")
        r = sync(self.repo); self.assertEqual(r.returncode, 1); self.assertIn("CLAUDE.md", r.stderr)
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), "mexi à mão\n")
        self.assertEqual(sync(self.repo, "--force").returncode, 0)
    def test_project_files_are_never_touched(self):
        (self.repo / "harness.conf").write_text("PROJECT=meu\n")
        (self.repo / "harness.d").mkdir(); frag = {"permissions": {"ask": ["mcp__x"]}, "hooks": {"Stop": [{"hooks": []}]}}
        (self.repo / "harness.d/settings.json").write_text(json.dumps(frag))
        self.assertEqual(sync(self.repo).returncode, 0)
        self.assertEqual((self.repo / "harness.conf").read_text(), "PROJECT=meu\n")
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(s["permissions"]["ask"], ["mcp__x"]); self.assertIn("Stop", s["hooks"])
        self.assertIn("Edit(/.harness/**)", s["permissions"]["deny"]); self.assertIn("PreToolUse", s["hooks"])
    def test_fragment_cannot_drop_harness_rules(self):
        (self.repo / "harness.d").mkdir(exist_ok=True)
        (self.repo / "harness.d/settings.json").write_text(json.dumps({"permissions": {"deny": []}, "hooks": {"PreToolUse": []}}))
        self.assertEqual(sync(self.repo).returncode, 0)
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn("Edit(/.harness/**)", s["permissions"]["deny"]); self.assertTrue(s["hooks"]["PreToolUse"])
    def test_outside_git_is_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sync(pathlib.Path(d)).returncode, 2)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever os templates e implementar `bin/sync` e `manifest_check.py`.**
- [ ] **Step 4: Rodar e ver passar** — `python3 -m unittest tests.test_sync -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(sync): install payload, generate managed files and manifest"`

---

### Task 8: Hooks de git e `validate`

**Files:**
- Create: `plugin/payload/git-hooks/commit-msg`, `plugin/payload/git-hooks/pre-push`, `plugin/payload/validate`
- Test: `tests/test_git_hooks.py`

**Interfaces:**
- Consumes: `sync` e `MANIFEST` (Task 7); aprovações (Tasks 3 e 4); `.harness/map.env`.
- Produces:
  - `commit-msg <arquivo>`: exit 1 com o motivo em stderr se a primeira linha não casar `^(feat|fix|chore|docs|refactor|test)(\([a-z0-9._/-]+\))?!?: .+` ou passar de 80 caracteres, ou se alguma linha casar (sem diferenciar maiúsculas) `^co-authored-by:.*(claude|anthropic|openai|gpt|codex|copilot|gemini)`, `generated with` ou contiver `🤖`. Primeira linha começando com `Merge ` ou `Revert ` passa.
  - `validate --profile <push|merge>`: roda `manifest_check.py`; depois o comando `VALIDATE_PUSH` ou `VALIDATE_MERGE` do `harness.conf` com `bash -c`, se definido. Exit do primeiro que falhar.
  - `pre-push`: lê do stdin as linhas `<ref local> <sha local> <ref remoto> <sha remoto>`. Ignora refs `refs/tags/*` e remoções (sha local zerado). Para cada outra, com `tip` igual ao sha local:
    1. exige aprovação `PASS` de `seguranca` e de `revisao` para `tip`;
    2. trava de spec: `base` = merge-base de `tip` com a branch padrão (`refs/remotes/origin/HEAD`; se não existir, `origin/main`; se não existir, `main`). Se algum assunto de commit em `base..tip` casar `^feat(\(.+\))?!?:`, o `git diff --name-only base..tip` precisa conter um caminho que case `SPEC_GLOB`;
    3. roda `validate --profile push`.
    Falhou qualquer uma: exit 1, com uma linha por motivo em stderr, cada uma dizendo o que fazer.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestCommitMsg(unittest.TestCase):
    def run_hook(self, text):
        f = write_tmp(text); return subprocess.run([str(ROOT / "plugin/payload/git-hooks/commit-msg"), f]).returncode
    def test_accepts(self):
        for m in ["feat(api): add booking endpoint", "fix: keep notes multiline\n\nLong body explaining why.\n",
                  "feat!: drop legacy auth", "Merge branch 'x' into y", 'Revert "feat: x"']:
            self.assertEqual(self.run_hook(m), 0, m)
    def test_rejects(self):
        for m in ["add stuff", "feature: x", "feat: " + "x" * 80,
                  "fix: a\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
                  "fix: a\n\n🤖 Generated with Claude Code", "fix: a\n\nGenerated with some tool"]:
            self.assertEqual(self.run_hook(m), 1, m)

class TestPrePush(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir"); self.repo = make_repo("work dir")
        git(self.repo, "remote", "add", "origin", str(self.origin)); git(self.repo, "fetch", "-q", "origin")
        sync(self.repo); commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
    def push(self):
        return subprocess.run(["git", "push", "-q", "origin", "feat/x"], cwd=self.repo, capture_output=True, text=True)
    def approve_both(self):
        for g in ("seguranca", "revisao"):
            subprocess.run([str(self.repo / ".harness/approve"), g, "ok"], cwd=self.repo, check=True)
    def test_push_without_approvals_is_denied(self):
        commit_file(self.repo, "a.txt", "fix: a")
        r = self.push(); self.assertNotEqual(r.returncode, 0)
        self.assertIn("seguranca", r.stderr); self.assertIn("revisao", r.stderr)
    def test_fix_with_both_approvals_passes(self):
        commit_file(self.repo, "a.txt", "fix: a"); self.approve_both()
        self.assertEqual(self.push().returncode, 0)
    def test_new_commit_invalidates_approvals(self):
        commit_file(self.repo, "a.txt", "fix: a"); self.approve_both()
        commit_file(self.repo, "b.txt", "fix: b")
        self.assertNotEqual(self.push().returncode, 0)
    def test_feat_requires_spec_in_branch(self):
        commit_file(self.repo, "a.txt", "feat(api): add booking"); self.approve_both()
        r = self.push(); self.assertNotEqual(r.returncode, 0); self.assertIn("docs/specs", r.stderr)
        commit_file(self.repo, "docs/specs/booking/spec.md", "docs: add booking spec"); self.approve_both()
        self.assertEqual(self.push().returncode, 0)
    def test_second_push_of_same_feat_branch_is_not_blocked_by_spec(self):
        commit_file(self.repo, "docs/specs/booking/spec.md", "docs: add booking spec")
        commit_file(self.repo, "a.txt", "feat: add booking"); self.approve_both(); self.assertEqual(self.push().returncode, 0)
        commit_file(self.repo, "b.txt", "feat: add cancel"); self.approve_both()
        self.assertEqual(self.push().returncode, 0)
    def test_validate_push_command_blocks(self):
        (self.repo / "harness.conf").write_text('VALIDATE_PUSH="exit 3"\n')
        commit_file(self.repo, "a.txt", "fix: a"); self.approve_both()
        self.assertNotEqual(self.push().returncode, 0)
    def test_manifest_drift_blocks(self):
        (self.repo / "CLAUDE.md").write_text("mexi\n"); commit_all(self.repo, "chore: x"); self.approve_both()
        r = self.push(); self.assertNotEqual(r.returncode, 0); self.assertIn("CLAUDE.md", r.stderr + r.stdout)
    def test_new_branch_without_origin_head(self):
        # origin/HEAD não existe neste remoto recém-adicionado; a base cai para origin/main
        self.assertNotEqual(git(self.repo, "rev-parse", "--verify", "-q", "origin/main"), "")
        commit_file(self.repo, "a.txt", "fix: a"); self.approve_both()
        self.assertEqual(self.push().returncode, 0)
    def test_tag_push_is_ignored(self):
        git(self.repo, "tag", "v0"); r = subprocess.run(["git", "push", "-q", "origin", "v0"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
```

`commit_file(repo, path, subject)` e `commit_all(repo, subject)` entram em `tests/helpers.py`: criam ou alteram o arquivo, fazem `git add -A` e commit com `--no-verify` (os testes do `commit-msg` são à parte).

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar os três scripts em bash.** O `pre-push` chama `python3` só para ler o JSON da aprovação e para o `manifest_check`.
- [ ] **Step 4: Rodar e ver passar** — `python3 -m unittest tests.test_git_hooks -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(gates): enforce approvals, spec lock and validation on push"`

---

### Task 9: `update`

**Files:**
- Create: `plugin/payload/update`
- Test: `tests/test_update.py`

**Interfaces:**
- Consumes: `bin/sync` (Task 7).
- Produces: `.harness/update <tag>`. Variáveis: `HARNESS_REPO` (padrão `https://github.com/FullChico/fullchico-harness.git`), `HARNESS_SKIP_PLUGIN=1` pula os comandos `claude plugin`. Passos: clona a tag com `git clone --depth 1 --branch <tag>` numa pasta temporária; roda o `plugin/bin/sync` **do clone** contra a raiz do projeto, com `--version <tag>`, repassando `--force` se recebido; se o `sync` sair diferente de 0, sai com o mesmo código sem tocar em mais nada; roda `claude plugin marketplace update fullchico` e `claude plugin update harness@fullchico` quando `claude` existir; imprime a lista de arquivos alterados (`git status --short`) e o aviso de `/reload-plugins`. Remove a pasta temporária em qualquer saída. Sem argumento: exit 2 com uso.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestUpdate(unittest.TestCase):
    def setUp(self):
        # "upstream" é uma cópia deste repositório com duas tags, servida por file://
        self.up = clone_self_with_tags("up stream", {"v0.1.0": None, "v0.2.0": ("plugin/templates/CLAUDE.md", "\nlinha nova v2\n")})
        self.repo = make_repo(); sync(self.repo); commit_all(self.repo, "chore: adopt harness")
        self.env = dict(os.environ, HARNESS_REPO=f"file://{self.up}", HARNESS_SKIP_PLUGIN="1")
    def update(self, *args):
        return subprocess.run([str(self.repo / ".harness/update"), *args], cwd=self.repo, env=self.env, capture_output=True, text=True)
    def test_update_brings_new_managed_content_and_version(self):
        r = self.update("v0.2.0"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("linha nova v2", (self.repo / "CLAUDE.md").read_text())
        self.assertEqual(json.loads((self.repo / ".harness/MANIFEST").read_text())["version"], "v0.2.0")
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(s["extraKnownMarketplaces"]["fullchico"]["source"]["ref"], "v0.2.0")
    def test_manual_drift_stops_update(self):
        (self.repo / "CLAUDE.md").write_text("mexi\n")
        self.assertEqual(self.update("v0.2.0").returncode, 1)
        self.assertEqual(json.loads((self.repo / ".harness/MANIFEST").read_text())["version"], "v0.1.0")
    def test_unknown_tag_and_missing_arg(self):
        self.assertNotEqual(self.update("v9.9.9").returncode, 0)
        self.assertEqual(self.update().returncode, 2)
```

`clone_self_with_tags(name, tags)` entra em `tests/helpers.py`: copia a árvore de trabalho deste repositório para um repositório git novo em caminho com espaço, cria um commit e uma tag por entrada, aplicando o acréscimo de texto indicado antes de cada tag.

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `update` em bash.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(update): sync a project to a tagged harness version"`

---

### Task 10: Agentes `seguranca` e `revisor`, e a skill `setup`

**Files:**
- Create: `plugin/agents/seguranca.md`, `plugin/agents/revisor.md`, `plugin/skills/setup/SKILL.md`
- Test: `tests/test_agents.py`

**Interfaces:**
- Consumes: contrato de veredito (Task 3); formato do pedido (Task 5); `bin/sync` (Task 7).
- Produces: dois agentes cujo final de resposta casa com `gate_stamp.parse_verdict`; a skill `/harness:setup`.

Conteúdo dos agentes, em português, com frontmatter `name`, `description`, `model: sonnet`, `tools: Read, Grep, Glob, Bash`:

- Os dois começam dizendo que recebem só ponteiros (`diff`, `commit`, e opcionalmente `spec` e `leitura`), que leem o diff por conta própria com `git diff <diff>`, e que não têm a conversa de quem escreveu o código.
- Os dois terminam com o bloco obrigatório, três linhas inteiras, nesta ordem: `VEREDITO: APPROVED` ou `VEREDITO: REJECTED`; `COMMIT: <o hash recebido em commit>`; `RESUMO: <uma linha>`. Em `REJECTED`, os achados vêm antes do bloco, um por item, com arquivo e linha.
- `seguranca`: procura segredo e credencial no diff, injeção, autorização ausente, dado sensível em log ou em mensagem de erro, dependência nova suspeita, e desativação de guardrail. Só reprova por achado concreto no diff.
- `revisor`: dois eixos. Padrões: o código segue o que o repositório documenta (`AGENTS.md`, `CONTRIBUTING.md`, lint), sem complexidade que a spec não pede. Aderência: o que a spec pede e falta, o que foi feito e não foi pedido, o que parece feito e está errado, citando a linha da spec. Sem spec, só o primeiro eixo. Confere também se o tipo de cada commit bate com a mudança (uma funcionalidade nova rotulada `fix` ou `refactor` é reprovação) e se há termo de domínio novo fora do `GLOSSARY.md` ou sinônimo de termo existente.

Skill `setup`, com `disable-model-invocation: true`: confere os pré-requisitos (`git`, `python3`, `docker`, `rtk`) e relata o que falta; roda `python3 "${CLAUDE_PLUGIN_ROOT}/bin/sync" "<raiz do projeto>" --version <versão do plugin.json>`; se o `sync` sair 1, mostra a lista e pergunta ao dono antes de usar `--force`; lê o repositório e preenche a região do projeto do `AGENTS.md` (Produto e Onde olhar) e o `harness.conf` (nome, comando de instalação, comandos de validação), mostrando o resultado para o dono confirmar; roda `claude plugin install` com `--scope project` para cada plugin de `enabledPlugins`; termina listando o que criou.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestAgents(unittest.TestCase):
    def fm(self, name):
        text = (ROOT / f"plugin/agents/{name}.md").read_text(); head = text.split("---")[1]
        return dict(l.split(": ", 1) for l in head.strip().splitlines() if ": " in l), text
    def test_frontmatter(self):
        for n in ("seguranca", "revisor"):
            fm, _ = self.fm(n)
            self.assertEqual(fm["name"], n); self.assertEqual(fm["model"], "sonnet")
            self.assertTrue(fm["description"]); self.assertNotIn(":", fm["name"])
    def test_agents_teach_the_verdict_contract(self):
        for n in ("seguranca", "revisor"):
            _, text = self.fm(n)
            for token in ("VEREDITO: APPROVED", "VEREDITO: REJECTED", "COMMIT:", "RESUMO:"):
                self.assertIn(token, text, n)
    def test_example_block_in_agent_parses(self):
        sha = "a" * 40
        self.assertEqual(gate_stamp.parse_verdict(f"achados...\nVEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: ok")["verdict"], "APPROVED")
    def test_setup_skill_is_user_invoked_and_calls_sync(self):
        text = (ROOT / "plugin/skills/setup/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", text); self.assertIn("${CLAUDE_PLUGIN_ROOT}/bin/sync", text)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever os dois agentes e a skill.**
- [ ] **Step 4: Rodar e ver passar; revalidar o plugin** — `python3 -m unittest tests.test_agents -v` e `claude plugin validate .`.
- [ ] **Step 5: Commit** — `git commit -m "feat(plugin): add security and review agents and setup skill"`

---

### Task 11: Teste de ponta a ponta e verificação na plataforma real

**Files:**
- Create: `tests/test_e2e.py`, `docs/verificacao-plataforma.md`

**Interfaces:**
- Consumes: tudo acima.

- [ ] **Step 1: Escrever o teste de ponta a ponta**

Um único teste que, num repositório temporário com remoto local: roda `sync`; cria branch com um commit `feat`; confirma push negado; adiciona a spec; simula os dois revisores passando ao `gate_stamp.py` os payloads de `SubagentStop` com o hash do topo; confirma push aceito; cria novo commit e confirma push negado de novo; confirma que o `service_guard.py` nega `.harness/approve` e que o `managed_guard.py` nega editar a região do `AGENTS.md`; confirma que o `manifest_check.py` acusa uma edição manual em `.harness/`.

- [ ] **Step 2: Rodar a suíte inteira**

Run: `python3 -m unittest discover -s tests -v`
Expected: todos PASS.

- [ ] **Step 3: Verificar na plataforma real o que os testes simulam**

Num projeto de rascunho, com o marketplace adicionado por caminho local (`claude plugin marketplace add <caminho deste repositório>`) e `/harness:setup` executado, conferir e registrar em `docs/verificacao-plataforma.md`, um item por linha, com o resultado observado:

1. o `agent_type` que chega ao hook para um agente do plugin é `harness:seguranca`;
2. o `SubagentStop` entrega `last_assistant_message` e o `gate_stamp` carimba;
3. o hook de `Agent` recebe `tool_input.subagent_type` e `tool_input.prompt`, e o nome da ferramenta casa com `Agent|Task`;
4. `model: sonnet` no agente do plugin é respeitado;
5. `$CLAUDE_PROJECT_DIR` e `cwd` dentro de um worktree secundário;
6. a negação nativa `Edit(/.harness/**)` barra Edit e Write;
7. um agente pedindo para rodar `.harness/approve` é barrado.

Para cada item que divergir do que o plano assumiu, ajustar o hook e o teste correspondentes antes de fechar a task.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py docs/verificacao-plataforma.md
git commit -m "test: add end-to-end gate flow and platform verification notes"
```
