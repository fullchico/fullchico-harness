# Harness v1, plano 2: ambiente por feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada feature, que é um worktree aberto a partir da branch padrão, tem um ambiente Docker próprio, com portas e projeto isolados, usado por todos os subagentes que trabalham nela e levantado por um caminho único que o dono aprova e que não serve de saída do sandbox.

**Architecture:** Scripts bash em `.harness/` (`worktree-env`, `up`, `prepare`, `dev`, `down`, `destroy`) leem o `harness.conf`. `up`, `down` e `destroy` rodam fora do sandbox do Bash, por uma lista de comandos excluídos, e sempre com pergunta ao dono por regra nativa. Antes de subir, `up` confere a configuração final do compose com `compose_check.py` e recusa o que daria ao contêiner acesso fora do projeto. Migration, seed e app rodam depois, dentro do sandbox, falando com `localhost`.

**Tech Stack:** bash compatível com 3.2; Python 3.9+ só com biblioteca padrão; Docker Compose v2; testes com `unittest`, usando um `docker` falso no `PATH` e um teste de integração com Docker real, pulado quando ele não está disponível.

**Spec:** `docs/superpowers/specs/2026-11-18-harness-design.md` (seções 6.3, 6.4, 10 e 11). Este plano altera a seção 11: ver "Decisões deste plano".

**Depende de:** plano 1 (fundação), já implementado.

## Decisões deste plano

Tomadas com o dono em 2026-11-19, depois de o sandbox virar a barreira de escrita:

- **Feature = worktree = ambiente. [dono]** É o modelo que já funciona no movacrm: o Orca ou o Conductor abre um worktree por feature a partir da branch padrão, e o ambiente sai do nome da pasta dele. Os subagentes trabalham em cima desse worktree e usam o ambiente dele.
- Um worktree de agente, criado pelo Claude Code dentro de `.claude/worktrees/` de uma feature, pertence ao ambiente dessa feature: calcula as mesmas portas e não sobe nada. No movacrm esses worktrees nunca tiveram `.env` próprio.
- Só o orquestrador sobe o ambiente, a partir do worktree da feature. É uma pergunta ao dono por feature.
- Limite aceito: subagentes em paralelo na mesma feature compartilham o banco. Tickets que criem migration ou testes que limpem tabelas podem interferir. A regra de validar sem ambiente sempre que der atenua.
- O agente pode pedir para subir, parar e remover o ambiente. O dono é sempre perguntado, por regra nativa `permissions.ask`, que continua perguntando nos modos automático e de permissão liberada, e vira negação no modo sem interface.
- `up` só sobe a infra. `AFTER_UP` e `DEV_CMD` não rodam dentro dele: são código do projeto, que o agente edita, e rodá-los fora do sandbox seria uma saída. Ficam em `prepare` e `dev`, que rodam dentro do sandbox.
- `up` recusa compose com montagem de pasta fora do projeto, contêiner privilegiado, ou espaço de processos da máquina. O socket do Docker cai na primeira regra.
- As "regras de serviço e de porta" do `service_guard`, previstas na spec, não são portadas. Docker não roda dentro do sandbox, então `docker compose up` solto falha pelo sistema; e rodar o app (`pnpm dev`) dentro do sandbox passou a ser o caminho normal. Portas vêm do `.env` que o `worktree-env` grava; a orientação vai para o `AGENTS.md`.

## Global Constraints

- Tudo do plano 1 continua valendo: Python só com biblioteca padrão, bash 3.2, caminhos com espaço, nada de caminho pessoal em `plugin/`, hooks `PreToolUse` negam em erro, `sys.dont_write_bytecode` nos módulos do payload.
- Nenhum script deste plano grava em `.harness/`, `harness.conf` nem no estado do harness. Arquivos de execução (PID, log) ficam em `.harness-run/`, na raiz do worktree, ignorado pelo git.
- `up`, `down` e `destroy` não executam nenhum comando vindo do `harness.conf` além de `docker compose` com `COMPOSE_FILE`.
- Formas exatas dos comandos, as únicas que saem do sandbox e as únicas que disparam a pergunta: `.harness/up`, `.harness/down`, `.harness/destroy`, e as mesmas com `./` na frente.
- **Contexto do ambiente:** `HARNESS_ENV`, se definida; senão o nome da pasta do worktree da feature. Para um worktree cujo caminho contém `/.claude/worktrees/`, a feature é a pasta que vem antes desse trecho. Normalizado para minúsculas, com o que não for letra ou dígito trocado por `-`.
- Bloco de portas: base `20000 + cksum(<caminho do worktree da feature>) % 2000 * 10`; `CONDUCTOR_PORT`, quando definida, é a base. Serviço na posição `i` de `SERVICES` usa `base + i`. No máximo 10 serviços.
- Variável de porta de um serviço: nome em maiúsculas com `-` trocado por `_`, mais `_PORT` (`web` → `WEB_PORT`).
- Nome do projeto Docker: `<PROJECT>-<contexto>`.
- Dono do ambiente: o worktree que rodou `up`. Fica registrado em `<estado do harness>/envs/<contexto>.json` (`worktree`, `base`), que `up` consegue gravar por rodar fora do sandbox.
- Rodar os testes: `python3 -m unittest discover -s tests -v`, fora de uma sessão com sandbox.

## Review Focus

1. Duas features (dois worktrees) recebem blocos e projetos Docker diferentes, e `destroy` de uma não toca na outra. Um worktree de agente dentro de uma feature calcula o mesmo bloco e o mesmo projeto dela, e um `up` vindo dele não recria os contêineres. Testes nas Tasks 2, 4 e 7.
2. Porta do bloco já ocupada por outro processo: o `worktree-env` procura o próximo bloco livre e avisa, sem alterar o `.env` se não achar. Teste na Task 2.
3. Compose que tenta sair: montagem com caminho relativo que sobe para fora (`../..`), link simbólico dentro do projeto apontando para fora, variável expandida para a pasta do usuário, `privileged`, `pid: host`. Testes na Task 3.
4. `destroy` no checkout principal, ou num contexto igual ao do checkout principal: recusa. Teste na Task 4.
5. `harness.conf` sem `SERVICES` ou sem `COMPOSE_FILE`, e Docker ausente ou parado: cada script falha com mensagem que diz o que falta, sem deixar o `.env` pela metade. Testes nas Tasks 2 e 4.

---

## Estrutura de arquivos

```
plugin/payload/worktree-env            bash
plugin/payload/compose_check.py        Python
plugin/payload/up                      bash
plugin/payload/prepare                 bash
plugin/payload/dev                     bash
plugin/payload/down                    bash
plugin/payload/destroy                 bash
plugin/payload/hooks/service_guard.py  alterado: resumo na pergunta
plugin/templates/settings.json         alterado: excluídos, perguntas, rede
plugin/templates/orca.yaml             novo
plugin/templates/conductor.toml        novo
plugin/templates/AGENTS.managed.md     alterado: seção Ambiente
plugin/bin/sync                        alterado: gera orca.yaml e conductor
tests/fake_docker                      docker falso para os testes
tests/test_worktree_env.py, test_compose_check.py, test_env_scripts.py, test_env_settings.py, test_env_integration.py
```

---

### Task 1: Teste real do sandbox com Docker e rede

Nenhum código do harness nesta tarefa. Ela responde o que a documentação deixou em aberto; as tarefas seguintes são ajustadas ao resultado.

**Files:**
- Modify: `docs/verificacao-plataforma.md` (nova seção "Ambiente e rede no sandbox")

- [ ] **Step 1: Montar um projeto de rascunho fora do diretório temporário**

Numa pasta provisória ao lado do repositório (o diretório temporário é gravável dentro do sandbox e contamina o teste): repositório git com um `docker-compose.yml` de um serviço `redis:7-alpine` publicado em `127.0.0.1:26379`, um script `.harness/up` que roda `docker compose up -d --wait`, e `.claude/settings.json` com `sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false`, `excludedCommands: [".harness/up"]`, `network.allowLocalBinding: true`, `network.allowedDomains: ["github.com", "registry.npmjs.org"]`, e um hook `PreToolUse` de Bash que grava a entrada recebida num arquivo.

- [ ] **Step 2: Rodar em `claude -p` e registrar, conferindo pelo estado real**

1. `docker compose up -d` solto, dentro do sandbox: falha?
2. `.harness/up` (excluído): sobe o contêiner? O hook de Bash foi chamado para ele?
3. De dentro do sandbox, com o contêiner de pé: `python3 -c "import socket; socket.create_connection(('127.0.0.1', 26379), 2)"` conecta?
4. `git ls-remote https://github.com/git/git HEAD` funciona com o domínio liberado?
5. `npm view left-pad version` funciona?
6. Acrescentar a `permissions.ask` a forma `Bash(.harness/up)` e rodar de novo: no modo sem interface o comando é negado, e o contêiner não sobe?
7. A partir de um worktree secundário: o `cwd` e `$CLAUDE_PROJECT_DIR` recebidos pelo hook (pendência do plano 1).

- [ ] **Step 3: Registrar em `docs/verificacao-plataforma.md`**, um item por linha com o observado, e apagar a pasta provisória e o contêiner.

- [ ] **Step 4: Ajustar o plano onde o resultado divergir**

Se o item 3 falhar: `prepare` e `dev` não podem rodar no sandbox; parar e levar a decisão ao dono (as alternativas são o dono rodá-los, ou entrarem nos excluídos com a mesma pergunta). Se o item 2 mostrar que o hook não roda para comando excluído: a Task 5 deixa de acrescentar o resumo à pergunta, e `up` passa a imprimir o resumo antes de subir.

- [ ] **Step 5: Commit** — `git commit -m "docs: record sandbox behaviour with docker and network"`

---

### Task 2: `worktree-env`

**Files:**
- Create: `plugin/payload/worktree-env`
- Test: `tests/test_worktree_env.py`

**Interfaces:**
- Consumes: `harness.conf` (`PROJECT`, `SERVICES`, e chaves `ENV_<NOME>`), lido por `hooks/common.py read_conf`.
- Produces: `.harness/worktree-env [--print]`. Grava no `.env` da raiz do worktree, preservando as demais linhas: `HARNESS_ENV_CONTEXT` (o contexto calculado), `COMPOSE_PROJECT_NAME`, uma `<SERVIÇO>_PORT` por serviço, e, para cada chave `ENV_<NOME>` do conf, a linha `<NOME>=<valor>` com `${<SERVIÇO>_PORT}` e `${COMPOSE_PROJECT_NAME}` substituídos. `--print` escreve essas linhas em stdout e não toca em arquivo. Idempotente. Saída 1, sem alterar o `.env`, quando falta `PROJECT` ou `SERVICES`, há mais de 10 serviços, `CONDUCTOR_PORT` é inválida, ou não há bloco livre.

Regras: se o `.env` não existe, parte de `.env.example` quando houver. Se o contexto já tem ambiente registrado no estado do harness (`envs/<contexto>.json`), usa a base registrada lá, para um worktree de agente falar com as mesmas portas da feature mesmo que o bloco inicial estivesse ocupado. Senão, testa as portas do bloco (processo escutando) e avança de 10 em 10 até achar um livre, avisando em stderr; com `CONDUCTOR_PORT`, só procura dentro das 10 portas reservadas, de 1 em 1.

- [ ] **Step 1: Escrever os testes que falham**

```python
def conf(repo, text): (repo / "harness.conf").write_text(text)
def env(repo): return dict(l.split("=", 1) for l in (repo / ".env").read_text().splitlines() if "=" in l)
def run(repo, *args, **env_extra):
    return subprocess.run([str(ROOT / "plugin/payload/worktree-env"), *args], cwd=repo,
                          env=dict(os.environ, **env_extra), capture_output=True, text=True)

class TestWorktreeEnv(unittest.TestCase):
    CONF = 'PROJECT=meuapp\nSERVICES="web api postgres"\nENV_DATABASE_URL=\'postgresql://a:b@localhost:${POSTGRES_PORT}/app\'\n'
    def test_writes_block_and_derived_values(self):
        repo = make_repo("Meu App_2"); conf(repo, self.CONF)
        self.assertEqual(run(repo).returncode, 0)
        e = env(repo); base = int(e["WEB_PORT"])
        self.assertEqual((int(e["API_PORT"]), int(e["POSTGRES_PORT"])), (base + 1, base + 2))
        self.assertEqual(base % 10, 0); self.assertTrue(20000 <= base < 40000)
        self.assertEqual(e["COMPOSE_PROJECT_NAME"], "meuapp-meu-app-2")
        self.assertEqual(e["DATABASE_URL"], f"postgresql://a:b@localhost:{base + 2}/app")
    def test_idempotent_and_preserves_other_keys(self):
        repo = make_repo(); conf(repo, self.CONF); (repo / ".env").write_text("SECRET=abc\nWEB_PORT=1\n")
        run(repo); first = (repo / ".env").read_text(); run(repo)
        self.assertEqual((repo / ".env").read_text(), first)
        self.assertEqual(env(repo)["SECRET"], "abc"); self.assertNotEqual(env(repo)["WEB_PORT"], "1")
    def wt(self, repo, path, branch=None):
        args = ["worktree", "add", "-q", str(path)] + (["-b", branch] if branch else ["--detach"])
        git(repo, *args); return path
    def test_two_features_get_different_blocks_and_projects(self):
        repo = make_repo(); conf(repo, self.CONF); commit_all(repo, "chore: conf")
        a = self.wt(repo, repo.parent / "roseau-audience", "feat/audience")
        b = self.wt(repo, repo.parent / "Fix Dev_Env", "fix/dev-env")
        run(a); run(b)
        self.assertNotEqual(env(a)["WEB_PORT"], env(b)["WEB_PORT"])
        self.assertEqual(env(a)["COMPOSE_PROJECT_NAME"], "meuapp-roseau-audience")
        self.assertEqual(env(b)["COMPOSE_PROJECT_NAME"], "meuapp-fix-dev-env")
    def test_agent_worktree_inside_a_feature_shares_its_environment(self):
        repo = make_repo(); conf(repo, self.CONF); commit_all(repo, "chore: conf")
        feature = self.wt(repo, repo.parent / "roseau-audience", "feat/audience")
        agent = self.wt(repo, feature / ".claude/worktrees/agent-a1b2c3")
        run(feature); run(agent)
        self.assertEqual(env(agent)["WEB_PORT"], env(feature)["WEB_PORT"])
        self.assertEqual(env(agent)["COMPOSE_PROJECT_NAME"], "meuapp-roseau-audience")
        self.assertEqual(env(agent)["HARNESS_ENV_CONTEXT"], "roseau-audience")
    def test_explicit_context_wins(self):
        repo = make_repo(); conf(repo, self.CONF); run(repo, HARNESS_ENV="Demo 1")
        self.assertEqual(env(repo)["COMPOSE_PROJECT_NAME"], "meuapp-demo-1")
    def test_busy_port_moves_to_next_block(self):
        repo = make_repo(); conf(repo, self.CONF)
        base = int(dict(l.split("=", 1) for l in run(repo, "--print").stdout.splitlines())["WEB_PORT"])
        with socket.socket() as s:
            s.bind(("127.0.0.1", base + 1)); s.listen()
            r = run(repo)
        self.assertEqual(int(env(repo)["WEB_PORT"]), base + 10); self.assertIn(str(base + 1), r.stderr)
    def test_conductor_port_is_the_base(self):
        repo = make_repo(); conf(repo, self.CONF); run(repo, CONDUCTOR_PORT="31000")
        self.assertEqual(env(repo)["WEB_PORT"], "31000")
    def test_print_does_not_write(self):
        repo = make_repo(); conf(repo, self.CONF)
        self.assertIn("WEB_PORT=", run(repo, "--print").stdout); self.assertFalse((repo / ".env").exists())
    def test_errors_leave_env_untouched(self):
        for text, extra in [("SERVICES=web\n", {}), ("PROJECT=x\n", {}),
                            ('PROJECT=x\nSERVICES="a b c d e f g h i j k"\n', {}),
                            (self.CONF, {"CONDUCTOR_PORT": "abc"}), (self.CONF, {"CONDUCTOR_PORT": "70000"})]:
            repo = make_repo(); conf(repo, text); (repo / ".env").write_text("SECRET=abc\n")
            r = run(repo, **extra); self.assertEqual(r.returncode, 1, text)
            self.assertEqual((repo / ".env").read_text(), "SECRET=abc\n"); self.assertTrue(r.stderr.strip())
    def test_starts_from_env_example(self):
        repo = make_repo(); conf(repo, self.CONF); (repo / ".env.example").write_text("FOO=bar\n"); run(repo)
        self.assertEqual(env(repo)["FOO"], "bar")
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `worktree-env`,** aproveitando a lógica de `scripts/worktree-env.sh` do movacrm (busca de bloco, `lsof` com alternativa em Python, base reaproveitada), sem nada específico de projeto.
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(env): derive per-worktree ports and compose project"`

---

### Task 3: `compose_check.py`

**Files:**
- Create: `plugin/payload/compose_check.py`
- Test: `tests/test_compose_check.py`

**Interfaces:**
- Produces:
  - `violations(config: dict, root: str) -> list[str]`: uma frase por problema, citando o serviço. `config` é o JSON de `docker compose config --format json`.
  - `summary(config: dict, root: str) -> str`: uma linha por serviço com imagem (ou "build local"), portas publicadas e pastas montadas, relativas à raiz.
  - Como script: `compose_check.py <raiz> [--summary]` lê o JSON do stdin. Sem `--summary`: sai 0 sem saída, ou sai 1 com as violações em stderr. Com `--summary`: imprime o resumo e sai 0. JSON inválido: sai 1.

Viola: montagem do tipo `bind` cuja origem, depois de `os.path.realpath`, não fica dentro de `realpath(root)`; `privileged: true`; `pid: host`; `ipc: host`; `network_mode: host`; `cap_add` não vazio; `devices` não vazio. Volume nomeado e `tmpfs` passam.

- [ ] **Step 1: Escrever os testes que falham**

```python
def cfg(**service): return {"name": "p", "services": {"db": dict({"image": "postgres:16"}, **service)}}
def bind(src, dst="/data"): return {"volumes": [{"type": "bind", "source": src, "target": dst}]}

class TestComposeCheck(unittest.TestCase):
    def setUp(self):
        self.root = make_repo(); (self.root / "data").mkdir()
    def v(self, config): return compose_check.violations(config, str(self.root))
    def test_clean_configs_pass(self):
        self.assertEqual(self.v(cfg()), [])
        self.assertEqual(self.v(cfg(**bind(str(self.root / "data")))), [])
        self.assertEqual(self.v(cfg(volumes=[{"type": "volume", "source": "pgdata", "target": "/var/lib"}])), [])
        self.assertEqual(self.v(cfg(volumes=[{"type": "tmpfs", "target": "/tmp"}])), [])
    def test_bind_outside_the_project_is_a_violation(self):
        home = os.path.expanduser("~")
        for src in [home, os.path.join(home, ".claude"), "/var/run/docker.sock", "/",
                    str(self.root.parent), str(self.root / "data" / ".." / "..")]:
            out = self.v(cfg(**bind(src))); self.assertEqual(len(out), 1, src); self.assertIn("db", out[0])
    def test_symlink_inside_pointing_outside_is_a_violation(self):
        os.symlink(os.path.expanduser("~"), self.root / "link")
        self.assertEqual(len(self.v(cfg(**bind(str(self.root / "link"))))), 1)
    def test_host_access_flags_are_violations(self):
        for extra in [{"privileged": True}, {"pid": "host"}, {"ipc": "host"}, {"network_mode": "host"},
                      {"cap_add": ["SYS_ADMIN"]}, {"devices": [{"source": "/dev/sda", "target": "/dev/sda"}]}]:
            self.assertEqual(len(self.v(cfg(**extra))), 1, extra)
    def test_every_service_is_checked(self):
        c = cfg(); c["services"]["evil"] = {"image": "x", "privileged": True}
        self.assertIn("evil", self.v(c)[0])
    def test_summary_lists_images_ports_and_mounts(self):
        c = cfg(ports=[{"published": "25432", "target": 5432}], **bind(str(self.root / "data")))
        s = compose_check.summary(c, str(self.root))
        for token in ("db", "postgres:16", "25432", "data"): self.assertIn(token, s)
    def test_cli(self):
        run = lambda data, *a: subprocess.run([sys.executable, str(ROOT / "plugin/payload/compose_check.py"),
                                               str(self.root), *a], input=data, capture_output=True, text=True)
        self.assertEqual(run(json.dumps(cfg())).returncode, 0)
        r = run(json.dumps(cfg(privileged=True))); self.assertEqual(r.returncode, 1); self.assertIn("db", r.stderr)
        self.assertEqual(run("{nao json").returncode, 1)
        self.assertIn("postgres:16", run(json.dumps(cfg()), "--summary").stdout)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar `compose_check.py`.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(env): refuse compose configs that reach outside the project"`

---

### Task 4: `up`, `prepare`, `dev`, `down`, `destroy`

**Files:**
- Create: `plugin/payload/up`, `plugin/payload/prepare`, `plugin/payload/dev`, `plugin/payload/down`, `plugin/payload/destroy`, `tests/fake_docker`
- Test: `tests/test_env_scripts.py`

**Interfaces:**
- Consumes: `worktree-env` (Task 2), `compose_check.py` (Task 3), `harness.conf` (`COMPOSE_FILE`, `AFTER_UP`, `DEV_CMD`).
- Produces:
  - `up`: roda `worktree-env`. Se o contexto já tem dono registrado, outro worktree, e o projeto Docker tem contêineres rodando: imprime de quem é o ambiente e sai 0 sem recriar nada. Senão registra este worktree como dono (`envs/<contexto>.json`) e segue: `docker compose --env-file .env -f <COMPOSE_FILE> config --format json`; passa pelo `compose_check.py`; imprime o resumo; `docker compose ... up -d --wait`. Qualquer etapa que falhe encerra com o código dela, sem subir nada.
  - `prepare`: roda `AFTER_UP` com `bash -c`, na raiz, com o `.env` exportado. Sem `AFTER_UP`: sai 0.
  - `dev [--background]`: roda `DEV_CMD` do mesmo jeito. Em segundo plano grava o PID em `.harness-run/dev.pid` e a saída em `.harness-run/dev.log`, e recusa se já houver um processo vivo nesse PID. Sem `DEV_CMD`: sai 1 com mensagem.
  - `down`: encerra o processo de `.harness-run/dev.pid`, se vivo, e roda `docker compose ... stop`.
  - `destroy`: recusa (sai 1) se o worktree é o checkout principal, ou se o contexto é igual ao do checkout principal; senão roda `down`, `docker compose ... down -v --rmi local --remove-orphans`, e apaga o registro `envs/<contexto>.json`. 
  - Todos falham com mensagem clara quando falta `COMPOSE_FILE` no conf, o arquivo não existe, ou `docker` não está no `PATH`.
  - `tests/fake_docker`: executável que anexa seus argumentos a `$FAKE_DOCKER_LOG`, e para `compose ... config --format json` imprime o conteúdo de `$FAKE_DOCKER_CONFIG`; sai com `$FAKE_DOCKER_RC` (padrão 0).

- [ ] **Step 1: Escrever os testes que falham**

Com um `PATH` em que `docker` é o `fake_docker`. Asserções, por teste:

```python
test_up_runs_env_then_check_then_compose_up        # .env criado; log tem "config --format json" antes de "up -d --wait"; -f e o projeto certos
test_up_refuses_violating_compose                  # FAKE_DOCKER_CONFIG com privileged: rc 1, stderr cita o serviço, log NÃO tem "up -d"
test_up_does_not_run_project_commands              # AFTER_UP="touch ran-after" e DEV_CMD="touch ran-dev" no conf: nenhum dos arquivos existe depois do up
test_up_prints_summary                             # stdout tem o nome do serviço e a imagem
test_prepare_runs_after_up_with_env                # AFTER_UP='echo "$WEB_PORT" > out.txt': out.txt tem a porta do .env
test_prepare_without_after_up_is_ok                # rc 0
test_dev_background_writes_pid_and_log_and_down_stops_it   # DEV_CMD="sleep 60": pid vivo; down: pid morto; log tem "compose" e "stop"
test_dev_refuses_second_instance                   # rc 1 enquanto o primeiro está vivo
test_destroy_refuses_main_checkout                 # rc 1, log não tem "down -v"
test_destroy_refuses_context_equal_to_main          # worktree com HARNESS_ENV igual ao contexto do principal: rc 1
test_agent_worktree_does_not_recreate              # up na feature, depois up no worktree de agente dentro dela: rc 0, stdout cita o worktree dono, log sem segundo "up -d"
test_up_registers_owner_and_destroy_clears_it       # envs/<contexto>.json com worktree e base; some depois do destroy
test_destroy_removes_only_its_feature_project      # log tem "down -v --rmi local --remove-orphans" com o projeto da feature, e só ele
test_missing_conf_or_docker_explains               # sem COMPOSE_FILE, arquivo inexistente, PATH sem docker: rc != 0 e stderr diz o que falta
test_scripts_write_nothing_under_harness_dir       # depois de up/prepare/dev/down: git status não mostra .harness/ alterado
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar os cinco scripts e o `fake_docker`.** Um trecho comum (ler conf, achar raiz, montar a linha do compose) fica num arquivo `plugin/payload/env-common.sh`, lido por `.` pelos cinco.
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(env): add up, prepare, dev, down and destroy"`

---

### Task 5: Configurações do sandbox para o ambiente e resumo na pergunta

**Files:**
- Modify: `plugin/templates/settings.json`, `plugin/payload/hooks/service_guard.py`
- Test: `tests/test_env_settings.py`

**Interfaces:**
- Consumes: `compose_check.summary` (Task 3).
- Produces, no `settings.json` gerado:
  - `sandbox.excludedCommands`: `.harness/up`, `./.harness/up`, `.harness/down`, `./.harness/down`, `.harness/destroy`, `./.harness/destroy`;
  - `permissions.ask`: as mesmas seis formas, como `Bash(<forma>)`;
  - `sandbox.network.allowLocalBinding: true` e `sandbox.network.allowedDomains` com `github.com`, `*.github.com`, `registry.npmjs.org`;
  - `sandbox.filesystem.denyWrite` ganha `orca.yaml` e `.conductor`.
- Produces, no `service_guard.py`: para comando Bash que seja exatamente uma das seis formas, saída 0 com JSON em stdout `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": <texto>}}`. Para `up`, o texto traz o resumo do compose (rodando `docker compose config` e `compose_check.summary`); se isso falhar, traz o motivo da falha. Para `down` e `destroy`, diz o que será parado ou apagado e o nome do projeto Docker. As negações do plano 1 (`--no-verify`, `hooksPath`) continuam.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestEnvSettings(unittest.TestCase):
    def setUp(self): self.repo = make_repo(); sync(self.repo); self.s = json.loads((self.repo / ".claude/settings.json").read_text())
    def test_only_exact_env_commands_leave_the_sandbox_and_all_of_them_ask(self):
        forms = [p + c for c in ("up", "down", "destroy") for p in (".harness/", "./.harness/")]
        self.assertEqual(sorted(self.s["sandbox"]["excludedCommands"]), sorted(forms))
        for f in forms: self.assertIn(f"Bash({f})", self.s["permissions"]["ask"])
    def test_network(self):
        net = self.s["sandbox"]["network"]; self.assertIs(net["allowLocalBinding"], True)
        for d in ("github.com", "registry.npmjs.org"): self.assertIn(d, net["allowedDomains"])
    def test_fragment_can_add_domains_but_not_excluded_commands_removal(self):
        (self.repo / "harness.d").mkdir(); (self.repo / "harness.d/settings.json").write_text(json.dumps(
            {"sandbox": {"network": {"allowedDomains": ["api.exemplo.com"]}}, "permissions": {"ask": []}}))
        sync(self.repo, "--force"); s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn("api.exemplo.com", s["sandbox"]["network"]["allowedDomains"])
        self.assertIn("github.com", s["sandbox"]["network"]["allowedDomains"])
        self.assertIn("Bash(.harness/up)", s["permissions"]["ask"])

class TestAskWithSummary(unittest.TestCase):
    def ask(self, repo, command, **env):   # roda service_guard.py com fake_docker no PATH; devolve (rc, json de stdout ou None)
        ...
    def test_up_asks_with_the_compose_summary(self):
        rc, out = self.ask(repo, ".harness/up")     # FAKE_DOCKER_CONFIG com db/postgres:16
        self.assertEqual(rc, 0); h = out["hookSpecificOutput"]
        self.assertEqual((h["hookEventName"], h["permissionDecision"]), ("PreToolUse", "ask"))
        self.assertIn("postgres:16", h["permissionDecisionReason"])
    def test_destroy_reason_names_the_project_and_says_data_is_deleted(self): ...
    def test_summary_failure_still_asks(self):       # FAKE_DOCKER_RC=1: decisão continua "ask", o texto diz que não deu para resumir
    def test_other_forms_get_no_special_treatment(self):
        for c in ("bash .harness/up", ".harness/up --force", "cd x && .harness/up", ".harness/validate --profile push"):
            rc, out = self.ask(repo, c); self.assertEqual((rc, out), (0, None), c)
    def test_hook_skip_flags_still_denied(self):
        self.assertEqual(self.ask(repo, "git push --no-verify")[0], 2)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Alterar o template e o `service_guard.py`.** Se a Task 1 mostrou que o hook não roda para comando excluído, manter a mudança do template e deixar o resumo só no `up`; registrar isso no ledger.
- [ ] **Step 4: Rodar e ver passar; rodar a suíte inteira.**
- [ ] **Step 5: Commit** — `git commit -m "feat(env): let env commands leave the sandbox only with owner consent"`

---

### Task 6: Orca, Conductor e a seção de ambiente do `AGENTS.md`

**Files:**
- Create: `plugin/templates/orca.yaml`, `plugin/templates/conductor.toml`
- Modify: `plugin/bin/sync`, `plugin/templates/AGENTS.managed.md`, `plugin/templates/harness.conf`
- Test: `tests/test_env_templates.py`

**Interfaces:**
- Produces:
  - `orca.yaml` gerado na raiz, gerenciado (entra no `MANIFEST`), com `scripts.setup` e `scripts.archive`. `setup`: copia o `.env` do checkout principal se o worktree não tiver; roda `.harness/worktree-env`; roda `INSTALL_CMD` do conf, se houver; instala os plugins declarados com `claude plugin install ... --scope project` quando `claude` existir. `archive`: roda `.harness/destroy` e ignora a falha.
  - `.conductor/settings.toml` gerado e gerenciado só quando o `harness.conf` tem `CONDUCTOR=1`: `setup`, `archive` e um `run` que chama `.harness/up && .harness/prepare && .harness/dev`.
  - `AGENTS.managed.md` ganha a seção "Ambiente": um ambiente por feature, que é o worktree; subagentes trabalham em cima dele e usam o ambiente dele; só o orquestrador sobe; quando subir (só quando a validação exige); os cinco comandos; que `up`, `down` e `destroy` perguntam ao dono, que as portas vêm do `.env` e não se escolhe porta à mão, e que `docker compose` solto não funciona dentro do sandbox.
  - `templates/harness.conf` ganha, comentada, a chave `CONDUCTOR=1`, e deixa de mencionar `MAX_PARALLEL` (plano 3).

- [ ] **Step 1: Escrever os testes que falham**

```python
test_orca_yaml_is_generated_and_managed      # existe; está em MANIFEST["files"]; setup cita .harness/worktree-env; archive cita .harness/destroy
test_orca_yaml_is_valid_yaml_subset          # toda linha de script começa com indentação consistente; sem tab
test_conductor_only_when_asked               # sem CONDUCTOR=1 não existe; com CONDUCTOR=1 existe e está no manifesto
test_conductor_removed_when_no_longer_asked  # tirar a chave e sincronizar de novo apaga o arquivo e a entrada do manifesto
test_agents_md_has_environment_section_and_fits   # tem "## Ambiente"; AGENTS.md continua abaixo de 8 KiB
test_orca_setup_script_runs                  # extrai o bloco setup, roda com bash num worktree com conf: .env criado com as portas; INSTALL_CMD executado
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever os templates e alterar o `sync`.** O `sync` passa a ler o `harness.conf` para decidir o Conductor, e a apagar gerenciados que deixaram de ser gerados, dentro e fora de `.harness/` (fecha uma pendência menor do plano 1).
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `git commit -m "feat(env): generate Orca and Conductor integration"`

---

### Task 7: Integração com Docker real e fechamento

**Files:**
- Create: `tests/test_env_integration.py`
- Modify: `docs/superpowers/specs/2026-11-18-harness-design.md` (seções 6.4 e 11), `docs/verificacao-plataforma.md`

- [ ] **Step 1: Escrever o teste de integração**

Pulado com `unittest.skipUnless` quando `docker info` falha ou a imagem `redis:7-alpine` não está disponível localmente e não há rede. Num repositório com `harness.conf` de `SERVICES="cache"`, um compose de um serviço `redis:7-alpine` publicado em `127.0.0.1:${CACHE_PORT}`, e quatro worktrees: o checkout principal, as features A e B, e um worktree de agente dentro de A (`A/.claude/worktrees/agent-x`):

1. `up` em A e em B: os dois ambientes ficam saudáveis, em portas diferentes; uma conexão TCP em cada porta funciona.
2. `worktree-env` no worktree de agente de A: o `.env` dele aponta para a mesma porta de A, e a conexão funciona sem subir nada. `up` nele: não cria contêiner novo (`docker ps` continua com um contêiner para A).
3. `destroy` em B: o contêiner de B some; o de A continua respondendo.
4. `destroy` no checkout principal: recusado.
5. Limpeza dos projetos Docker no `tearDown`, com `docker compose down -v` direto.

- [ ] **Step 2: Rodar a suíte inteira** — `python3 -m unittest discover -s tests -v`, todos PASS ou pulados com motivo.

- [ ] **Step 3: Atualizar a spec.** Seção 11: os cinco scripts como ficaram, quem pode chamar o quê, a pergunta ao dono, a checagem do compose, `prepare` e `dev` dentro do sandbox, `.harness-run/`. Seção 6.4: o `service_guard` sem regras de serviço e de porta, com o motivo. Seção 14: os fatos confirmados na Task 1.

- [ ] **Step 4: Commit** — `git commit -m "test(env): cover two worktrees with real docker; align the spec"`
