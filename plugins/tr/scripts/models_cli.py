#!/usr/bin/env python3
"""Configuração de modelos por papel no projeto."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry
import sign

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10: o agente gerado usa string JSON válida em TOML.
    tomllib = None

MIRRORS = {"claude": {"opus": ("codex", "sol"), "sonnet": ("codex", "luna"),
                       "haiku": ("codex", "terra"), "fable": ("codex", "astra")},
            "codex": {"sol": ("claude", "opus"), "luna": ("claude", "sonnet"),
                      "terra": ("claude", "haiku"), "astra": ("claude", "fable")}}
ROLES = ("planning", "orchestration", "execution", "review", "support")
PATH = os.path.join(".claude", "harness.json")
CODEX_IDS = {"sol": "gpt-6.2-sol", "luna": "gpt-6-luna",
             "terra": "gpt-6.1-terra", "astra": "gpt-6.2-astra"}
RATE_LIMIT = ("rate limit", "rate_limit", "usage limit", "quota exceeded", "429", "limite de uso")


def read_file(root):
    try:
        with open(os.path.join(root, PATH), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(".claude/harness.json deve conter um objeto JSON")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError(f".claude/harness.json não pôde ser lido: {error}") from error


def validate_role(value):
    try:
        cli, model_name = value.split(":", 1)
    except (AttributeError, ValueError):
        raise ValueError("use cli:modelo, por exemplo claude:sonnet")
    if cli not in ("claude", "codex") or not model_name.strip():
        raise ValueError("CLI deve ser claude ou codex e o modelo não pode ser vazio")
    return {"cli": cli, "model": model_name.strip()}


def configure(root, args):
    if os.environ.get("CLAUDECODE") == "1" and not registry.owner_approved(
            root, registry.owner_canonical(["models", "configure", *args])):
        raise ValueError("Sem permissão para alterar .claude/harness.json nesta sessão do Claude Code. Rode no terminal do dono.")
    if args and len(args) % 2:
        raise ValueError("informe pares papel cli:modelo")
    chosen = {}
    gates = {}
    current_data = read_file(root)
    available = current_data.get("gates") or {}
    for i in range(0, len(args), 2):
        role, value = args[i], args[i + 1]
        selected = validate_role(value)
        if role.startswith("gate:"):
            name = role.split(":", 1)[1]
            if name not in available:
                raise ValueError(f"portão não encontrado: {name}")
            if selected["cli"] == "codex" and available[name].get("signs") != "agent":
                raise ValueError("modelo Codex por portão exige `signs: agent`; portão de comando usa o verificador nativo")
            gates[name] = selected
        elif role in ROLES:
            chosen[role] = selected
        else:
            raise ValueError(f"papel inválido: {role}; use {', '.join(ROLES)} ou gate:<nome>")
    if not args:
        if not sys.stdin.isatty():
            raise ValueError("modo não interativo exige pares papel cli:modelo")
        print("Configure cada papel como cli:modelo (Enter mantém o atual).")
        current = (current_data.get("models") or {})
        for role in ROLES:
            old = current.get(role, {})
            default = f"{old.get('cli', '')}:{old.get('model', '')}" if old else ""
            value = input(f"{role} [{default}]: ").strip()
            if value:
                chosen[role] = validate_role(value)
        for name, gate in available.items():
            if gate.get("stage") != "end" and gate.get("signs") != "agent":
                continue
            old = (current.get("gates") or {}).get(name, {})
            default = f"{old.get('cli', '')}:{old.get('model', '')}" if old else "padrão de revisão"
            value = input(f"revisor do portão {name} [{default}]: ").strip()
            if value:
                selected = validate_role(value)
                if selected["cli"] == "codex" and gate.get("signs") != "agent":
                    raise ValueError("modelo Codex por portão exige `signs: agent`")
                gates[name] = selected
    data = current_data
    config = data.get("models") if isinstance(data.get("models"), dict) else {}
    for role, entry in chosen.items():
        config[role] = entry
    if gates:
        config.setdefault("gates", {}).update(gates)
    data["models"] = config
    folder = os.path.join(root, ".claude")
    os.makedirs(folder, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as f:
        try:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            temp = f.name
        except BaseException:
            os.unlink(f.name)
            raise
    os.replace(temp, os.path.join(root, PATH))
    print(f"configuração gravada em {os.path.join(root, PATH)}")


def show(root):
    config = read_file(root).get("models") or {}
    if not isinstance(config, dict):
        raise ValueError("`models` deve ser um objeto em .claude/harness.json")
    for role in ROLES:
        value = config.get(role)
        if role == "support" and not value:
            print("support: não configurado (usa o espelho inicial do papel que atingiu limite)")
            continue
        if role == "orchestration" and not value:
            print("orchestration: não configurado (o orquestrador abre como Claude; escolha por demanda em `tr-harness orchestrate`)")
            continue
        if not value:
            print(f"{role}: não configurado")
            continue
        cli, model = value.get("cli"), value.get("model")
        mirror = MIRRORS.get(cli, {}).get(model.lower())
        mirror_text = f"; espelho {mirror[0]}:{mirror[1]}" if mirror else "; sem espelho inicial conhecido"
        available = "disponível" if shutil.which(cli) else "CLI indisponível no PATH"
        print(f"{role}: {cli}:{model}{mirror_text}; {available}")
    for name, value in sorted((config.get("gates") or {}).items()):
        print(f"gate:{name}: {value['cli']}:{value['model']}")


def _codex_newest(alias):
    """O id mais novo do Codex para um apelido (`terra` → `gpt-6.1-terra`), pela lista de modelos que o Codex desta
    máquina conhece. Um nome é sempre um apelido para a versão mais nova; só um id com versão fixa a versão."""
    import re
    try:
        with open(os.path.join(os.path.expanduser("~"), ".codex", "models_cache.json"), encoding="utf-8") as stream:
            models = json.load(stream).get("models") or []
    except (OSError, ValueError, AttributeError):
        return None
    best = None
    for item in models:
        slug = str((item or {}).get("slug") or "")
        m = re.fullmatch(rf"[a-z]+-(\d+(?:\.\d+)*)-{re.escape(alias)}", slug)
        if m and (item.get("visibility") in (None, "list")):
            version = tuple(int(n) for n in m.group(1).split("."))
            if best is None or version > best[0]:
                best = (version, slug)
    return best[1] if best else None


def _runtime_model(choice):
    model = choice["model"]
    if choice["cli"] != "codex":
        return model  # no Claude, `haiku`/`sonnet`/`opus` já são apelidos da versão mais nova
    if any(ch.isdigit() for ch in model):
        return model  # o dono disse a versão: vale a que ele disse
    return _codex_newest(model.lower()) or CODEX_IDS.get(model.lower(), model)


def _support(config, primary):
    explicit = config.get("support")
    if isinstance(explicit, dict) and explicit != primary:
        return explicit
    mirror = MIRRORS.get(primary["cli"], {}).get(primary["model"].lower())
    return {"cli": mirror[0], "model": mirror[1]} if mirror else None


def _state_dir(root):
    result = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("execução exige um projeto Git; rode `fullchico-harness install` primeiro")
    return os.path.join(result.stdout.strip(), "harness-runs")


def _run_folder(root):
    """A pasta da execução. Com `--detach`, o id vem do processo pai pela variável `FULLCHICO_RUN_ID`."""
    given = os.environ.get("FULLCHICO_RUN_ID")
    run_id = given or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = os.path.join(_state_dir(root), run_id)
    os.makedirs(folder, exist_ok=bool(given))
    return run_id, folder


def detach(root, argv):
    """Roda `models run`/`validate-gate` num processo próprio e devolve o id na hora.

    Quem orquestra não fica preso numa chamada longa do terminal (o Bash do agente tem limite de minutos);
    o resultado sai em `models wait <id>`."""
    run_id, folder = _run_folder(root)
    command = [sys.executable, "-I", os.path.abspath(__file__), *argv, "--project", root]
    script = '"$@" > "$0/result.out" 2> "$0/result.err"; echo $? > "$0/exit"'
    subprocess.Popen(["sh", "-c", script, folder, *command], cwd=root, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=dict(os.environ, FULLCHICO_RUN_ID=run_id))
    print(json.dumps({"id": run_id, "status": "running", "wait": f"tr-harness models wait {run_id}"},
                     ensure_ascii=False))
    return 0


def wait(root, run_id, timeout=100, more=()):
    """Espera o fim de uma execução destacada. Sai com o código dela, ou 3 se ainda está rodando."""
    import re
    import time
    ids = [run_id, *more]
    for one in ids:
        if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", one):
            raise ValueError(f"id de execução inválido: {one}")
        if not os.path.isdir(os.path.join(_state_dir(root), one)):
            raise ValueError(f"execução não encontrada: {one}")
    folder = os.path.join(_state_dir(root), run_id)
    if all(os.path.isfile(os.path.join(_state_dir(root), one, "dispatch.json")) for one in ids):
        return _terminal_wait(root, ids, timeout)
    if more:
        return _detached_wait(root, ids, timeout)
    deadline = time.monotonic() + timeout
    while not os.path.isfile(os.path.join(folder, "exit")):
        if time.monotonic() >= deadline:
            print(json.dumps({"id": run_id, "status": "running", "wait": f"tr-harness models wait {run_id}"},
                             ensure_ascii=False))
            return 3
        time.sleep(1)
    with open(os.path.join(folder, "exit"), encoding="utf-8") as stream:
        code = int(stream.read().strip() or 1)
    for name, out in (("result.out", sys.stdout), ("result.err", sys.stderr)):
        with open(os.path.join(folder, name), encoding="utf-8") as stream:
            out.write(stream.read())
    return code


def _invoke(root, role, choice, prompt, folder, number, agent=None):
    cli, model = choice["cli"], _runtime_model(choice)
    executable = shutil.which(cli)
    if not executable:
        raise ValueError(f"CLI `{cli}` não encontrada no PATH")
    output = os.path.join(folder, f"{number}-{cli}-{role}.out")
    error = os.path.join(folder, f"{number}-{cli}-{role}.err")
    if cli == "claude":
        command = [executable, "-p", "--model", model, "--output-format", "json"]
        if agent:
            command += ["--agent", agent]
        if role == "review":
            command += ["--permission-mode", "plan"]
        else:
            command += ["--permission-mode", "auto"]
    else:
        command = [executable, "exec", "--model", model, "--json", "-o",
                   os.path.join(folder, f"{number}-last.txt"), "-"]
        # O codex recusa `--approve-for-me` junto de `--sandbox`: a aprovação automática já implica workspace-write.
        command += ["--sandbox", "read-only"] if role == "review" else ["--approve-for-me"]
    try:
        # O hook reconhece o executor externo por aqui: ele escreve código mesmo sendo a sessão principal do CLI.
        environment = dict(os.environ, FULLCHICO_ROLE=role, FULLCHICO_RUN_DIR=folder)
        if cli == "claude":
            # A nova CLI é uma sessão independente, não uma tentativa de aninhar a sessão atual.
            environment.pop("CLAUDECODE", None)
            environment.pop("CLAUDE_CODE_ENTRYPOINT", None)
        if cli == "codex" and role != "review":
            prompt = ("If Docker, localhost or another resource is blocked by the sandbox, "
                      "request escalation for that specific command from the automatic reviewer. "
                      "Try an allowed path before declaring a blocker; do not change the "
                      "project's security settings.\n\n" + prompt)
        result = subprocess.run(command, cwd=root, input=prompt, capture_output=True,
                                text=True, timeout=3600, env=environment)
        status, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        status, stdout, stderr = 124, exc.stdout or "", "tempo limite de 1 hora atingido"
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
    if cli == "codex" and role == "execution" and status == 0 and not os.path.isfile(os.path.join(folder, "hooks-alive")):
        # Hook de projeto não revisado não roda no `codex exec`, e nada avisa: o executor teria trabalhado sem trilho.
        status = 125
        stderr += ("\nos hooks do tr não rodaram nesta execução Codex: o trabalho pode ter sido feito, mas sem trilho, e "
                   "por isso não conta. É um passo do dono, uma vez por checkout: abra `codex` nesta pasta, escolha "
                   "confiar nos hooks do projeto e rode de novo. Não repita a execução antes disso.\n")
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(stdout)
    with open(error, "w", encoding="utf-8") as stream:
        stream.write(stderr)
    return {"cli": cli, "model": choice["model"], "model_id": model, "code": status,
            "output": output, "erros": error, "limit": status != 0 and any(s in (stderr + stdout).lower() for s in RATE_LIMIT)}


def _agent_instructions(root, agent, cli="codex"):
    """Instruções do agente do portão para uma revisão em CLI separada. Para o Claude vale a definição inteira
    do agente (a do projeto, ou a do plugin); a versão resumida do Codex é só para o Codex."""
    name = agent.split(":")[-1]
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError(f"nome de agente inválido: {agent}")
    candidates = [os.path.join(root, ".codex", "agents", agent.replace(":", "-") + ".toml"),
                  os.path.join(root, ".claude", "agents", name + ".md"),
                  os.path.join(root, ".codex", "harness", "tr", "agents", name + ".md"),
                  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", name + ".md")]
    if cli == "claude":
        candidates = [c for c in candidates if c.endswith(".md") and "/.codex/" not in c] + \
                     [c for c in candidates if not (c.endswith(".md") and "/.codex/" not in c)]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "rb") as stream:
                if path.endswith(".toml"):
                    if tomllib:
                        return tomllib.load(stream).get("developer_instructions", "")
                    for line in stream.read().decode("utf-8").splitlines():
                        if line.startswith("developer_instructions = "):
                            return json.loads(line.split(" = ", 1)[1])
                    raise ValueError(f"agente `{agent}` sem developer_instructions legíveis")
                return stream.read().decode("utf-8")
    raise ValueError(f"agente `{agent}` não instalado para revisão Codex; instale a skill/agente antes de configurar o portão")


def _final_text(attempt):
    if attempt["cli"] == "codex":
        # O arquivo -o do Codex tem o número da tentativa antes do papel.
        path = os.path.join(os.path.dirname(attempt["output"]),
                            os.path.basename(attempt["output"]).split("-", 1)[0] + "-last.txt")
        try:
            with open(path, encoding="utf-8") as stream:
                return stream.read()
        except OSError:
            return ""
    try:
        with open(attempt["output"], encoding="utf-8") as stream:
            data = json.load(stream)
        return data.get("result", "") if isinstance(data, dict) else ""
    except (OSError, ValueError):
        return ""


def validate_gate(root, name, ticket=None, request=""):
    reg = registry.load(root)
    if not reg or name not in reg["gates"]:
        raise ValueError(f"portão não encontrado: {name}")
    gate = reg["gates"][name]
    if gate["signs"] != "agent":
        raise ValueError(f"portão `{name}` não é validado por agente")
    if ticket:
        import pathlib
        path = (pathlib.Path(root) / ticket).resolve()
        if not path.is_file() or not path.is_relative_to(pathlib.Path(root).resolve()):
            raise ValueError("ticket deve ser um arquivo dentro do projeto")
    config = reg.get("models") or {}
    choice = (config.get("gates") or {}).get(name) or config.get("review")
    import tasks as _tasks
    chosen = _tasks.run_model(root, "reviewers")
    if chosen:  # o revisor escolhido para esta demanda, na partida
        choice = {"cli": chosen[0], "model": chosen[1]}
    in_terminal = bool(_tasks.run_choice(root).get("terminals")) and bool(__import__("terminal").executable())
    if not isinstance(choice, dict) or choice.get("cli") not in ("claude", "codex") or not choice.get("model"):
        raise ValueError(f"configure `gate:{name}` ou `review` antes de validar por CLI")
    if choice["cli"] == "codex":
        instructions = _agent_instructions(root, gate["agent"])
    else:
        instructions = ""
    if gate["stage"] == "end":
        import tasks
        pending = tasks.open_work(root)
        if pending:  # a auditoria é a chegada do trem: com trabalho aberto, nada de revisor de fim
            raise ValueError("o trem ainda não chegou: termine e integre " + ", ".join(pending[:4]) +
                             " antes da auditoria")
    snapshot = ledger.head(root)
    key = registry.stamp_key(root, gate)
    if not snapshot or not key or (gate["stage"] == "end" and registry.dirty(root)):
        raise ValueError("estado sem snapshot válido ou árvore suja; prepare a entrega antes da revisão")
    context = ""
    if ticket:
        with open(os.path.join(root, ticket), encoding="utf-8") as stream:
            context = f"Ticket: {ticket}\n{stream.read()}\n"
    prompt = (f"You are the independent reviewer of gate `{name}` ({gate['agent']}). "
              "Do not edit files. Examine the current state yourself, against the criterion the owner accepted "
              f"({__import__('certs').document(root)} and its tickets), and your own instructions. "
              f"Expected snapshot: {snapshot} (a tr content hash of the working files, not a Git commit: do not look "
              f"it up in Git; copy it verbatim into COMMIT)\n{context}"
              # o relato de quem pede não chega ao revisor: o julgado não instrui o juiz (fica no manifesto)
              "Validate the delta between the planned (the accepted spec, its tickets and the artifacts approved "
              "at the start) and the delivered, observed in the delivered state: the running product, the code "
              "and the tests that exercise it. An artifact of the plan is the reference, never the evidence. "
              "Evidence captured for this exact state is listed by `tr-harness evidence`; anything produced for "
              "another state is not evidence. When that list is empty, or the command cannot run where you are, that "
              "is NOT a reason to reject: judge from the delivered state itself (read the code and the tests, run "
              "the checks you are allowed to run). Reject for missing evidence only when your gate's own instructions "
              "require a captured proof that nothing else replaces. "
              "Answer with concrete findings and end with exactly three lines: "
              "VERDICT: APPROVED or REJECTED, COMMIT: <the expected snapshot, verbatim>, SUMMARY: <one sentence>.\n"
              + (f"Agent instructions:\n{instructions}\n" if instructions else ""))
    _, folder = _run_folder(root)
    with open(os.path.join(folder, "pedido.txt"), "w", encoding="utf-8") as stream:
        stream.write(prompt)
    try:  # a pasta da prova nasce aqui, fora do sandbox do revisor: ele só precisa conseguir ler
        import evidence_cli
        evidence_cli.folder(root, create=True)
    except Exception:
        pass
    if in_terminal:
        attempts = [_review_in_terminal(root, choice, prompt, folder, name, gate["agent"])]
    else:
        attempts = [_invoke(root, "review", choice, prompt, folder, 1,
                            gate["agent"] if choice["cli"] == "claude" else None)]
    if attempts[0]["limit"]:
        support = _support(config, choice)
        if support:
            fallback_instructions = ""
            if support["cli"] == "codex":
                fallback_instructions = "\nInstruções do agente:\n" + _agent_instructions(root, gate["agent"])
            attempts.append(_invoke(root, "review", support,
                                    prompt + fallback_instructions +
                                    "\nHandoff: o modelo anterior atingiu limite. Revise o estado atual.",
                                    folder, 2, gate["agent"] if support["cli"] == "claude" else None))
    final = attempts[-1]
    verdict_text = (final.get("text") if "text" in final else _final_text(final)) if final["code"] == 0 else ""
    final.pop("text", None)
    verdict = sign.once(r"^[ \t]*VERDICT: (APPROVED|REJECTED)[ \t]*$", verdict_text)
    commit = sign.once(r"^[ \t]*COMMIT: ([0-9a-f]{40})[ \t]*$", verdict_text)
    summary = sign.once(r"^[ \t]*SUMMARY: (\S.*?)[ \t]*$", verdict_text)
    current = ledger.head(root)
    accepted = bool(verdict and commit == snapshot == current and summary and
                    registry.stamp_key(root, gate) == key and
                    (gate["stage"] != "end" or not registry.dirty(root)))
    if accepted:
        import certs
        model = f"{final['cli']}:{final['model']}"
        refused = certs.certify(root, name, key, verdict, gate["agent"], f"{summary} ({model})")
        if refused:
            print(f"certificado recusado: {refused}", file=sys.stderr)
            accepted = False
    manifest = {"gate": name, "agent": gate["agent"], "snapshot": snapshot, "caller_report": request,
                "attempts": attempts, "verdict": verdict if accepted else None,
                "stamped": accepted and verdict == "APPROVED"}
    manifest_path = os.path.join(folder, "manifesto.json")
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"gate": name, "model": f"{final['cli']}:{final['model']}",
                      "verdict": manifest["verdict"], "stamped": manifest["stamped"],
                      "manifesto": manifest_path}, ensure_ascii=False))
    return 0 if manifest["stamped"] else 1


def _request(root, role, prompt, ticket=None):
    """O pedido canônico do papel: a instrução, o ticket inteiro e o handoff de quem pediu."""
    if ticket:
        import pathlib
        file = (pathlib.Path(root) / ticket).resolve()
        if not file.is_file() or not file.is_relative_to(pathlib.Path(root).resolve()):
            raise ValueError("ticket deve ser um arquivo dentro do projeto")
        prompt = f"Role: {role}. Ticket: {ticket}\n\n{file.read_text()}\n\nRequest: {prompt}"
    elif not prompt:
        raise ValueError("informe --prompt ou --ticket")
    instructions = {
        "planning": "You are the planner. Define requirements, dependencies, criteria and applicable gates.",
        "execution": "You are the independent executor of this ticket. Read the spec cited in the handoff and respect Start, Gates, Files and Blocked by. Use TDD when applicable, run the ticket's checks and record evidence. Do not sign your own review; hand a summary to the orchestrator.",
        "review": "You are the independent reviewer. Do not edit files. Examine code and evidence, list concrete defects and conclude with VERDICT: APPROVED or REJECTED.",
    }
    return instructions[role] + "\n\n" + prompt


def _choice(root, role):
    config = read_file(root).get("models") or {}
    choice = config.get(role) if isinstance(config, dict) else None
    import tasks
    chosen = tasks.next_executor(root) if role == "execution" else tasks.run_model(root, {"review": "reviewers"}.get(role, ""))
    if chosen:  # a escolha da partida vale para a demanda inteira, sem mudar o registro
        choice = {"cli": chosen[0], "model": chosen[1]}
    if not isinstance(choice, dict) or choice.get("cli") not in ("claude", "codex") or not choice.get("model"):
        raise ValueError(f"configure o papel `{role}` antes de executar")
    return choice


def _free_dead_seats(root, seats):
    """Uma vaga cujo executor morreu sem relato (terminal encerrado à mão, queda) ficaria ocupada para sempre.
    Se o terminal não existe mais, não há relato e o worktree não tem trabalho por commitar, a vaga é liberada."""
    import glob
    import terminal
    for path in glob.glob(os.path.join(_state_dir(root), "*", "dispatch.json")):
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            continue
        work = data.get("worktree") or ""
        if not work.startswith(seats) or not os.path.isdir(work) or terminal.alive(data.get("session") or ""):
            continue
        report = data.get("report") or ""
        if report and os.path.isfile(report if os.path.isabs(report) else os.path.join(root, report)):
            continue  # relatou: quem integra é o orquestrador, e é ele que remove
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=work, capture_output=True, text=True).stdout.strip()
        if dirty:
            continue  # ficou trabalho sem commit: não se joga fora; o orquestrador decide pelo handoff
        subprocess.run(["git", "worktree", "remove", "--force", work], cwd=root, capture_output=True)
        if data.get("branch"):
            subprocess.run(["git", "branch", "-D", data["branch"]], cwd=root, capture_output=True)


def unfinished_operation(root):
    """Nome da operação do Git deixada pela metade no checkout (merge, rebase, cherry-pick, revert), ou None.
    Um commit feito com ela aberta a conclui: é assim que trabalho de uma viagem cancelada entra sem ninguém pedir."""
    git_dir = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=root, capture_output=True,
                             text=True).stdout.strip()
    for mark, name in (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                       ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")):
        if git_dir and os.path.exists(os.path.join(git_dir, mark)):
            return name
    return None


def integrate(root, run_ids):
    """Integra o trabalho dos executores na branch da demanda, um por vez, e só desmonta a vaga depois de
    conferir que o trabalho entrou. É o que a chegada não desfaz: branch apagada antes do merge é trabalho perdido."""
    def git(*args, cwd=root):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)

    pending = unfinished_operation(root)
    if pending:
        print(f"há um {pending} pela metade neste checkout (de outra partida): nada foi integrado. Reporte ao "
              f"maestro; é ele, com o dono, que decide concluir ou abortar.", file=sys.stderr)
        return 1
    for run_id in run_ids:
        try:
            with open(os.path.join(_state_dir(root), run_id, "dispatch.json"), encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            print(f"{run_id}: execução não encontrada", file=sys.stderr)
            return 1
        work, branch = data.get("worktree") or "", data.get("branch") or ""
        if os.path.isdir(work) and git("status", "--porcelain", "--", ".", ":!.harness-run", cwd=work).stdout.strip():
            # o executor Codex não commita (o sandbox dele não grava em .git): o commit é feito aqui
            git("add", "-A", "--", ".", ":!.harness-run", cwd=work)
            done = git("commit", "-m", f"chore(tr): work of executor {run_id[-8:]}", cwd=work)
            if done.returncode:
                print(f"{run_id}: o commit do trabalho falhou; vaga e branch mantidas.\n{(done.stderr or done.stdout)[-600:]}",
                      file=sys.stderr)
                return 1
        merged = git("merge", "--no-ff", "-m", f"chore(tr): merge executor {run_id[-8:]}", branch)
        if merged.returncode or git("merge-base", "--is-ancestor", branch, "HEAD").returncode:
            conflicts = git("diff", "--name-only", "--diff-filter=U").stdout.strip()
            if unfinished_operation(root):
                git("merge", "--abort")
            print(f"{run_id}: o merge de `{branch}` não entrou; vaga e branch mantidas, nada foi desmontado."
                  + (f"\nconflito em: {conflicts}" if conflicts else f"\n{(merged.stderr or merged.stdout)[-600:]}"),
                  file=sys.stderr)
            return 1
        if os.path.isdir(work):
            git("worktree", "remove", "--force", work)
        git("branch", "-d", branch)
        print(f"{run_id}: integrado ({branch}) e vaga desmontada")
    return 0


def terminal_execute(root, prompt, ticket=None):
    """O executor abre num terminal próprio (tmux) e num worktree próprio, nascido da branch da demanda: uma
    sessão inteira, que o orquestrador (e o maestro) lê e encerra. Devolve o id na hora; o executor avisa
    gravando o relato dele (o hook de parada cobra), e `models wait <id>...` espera por esse arquivo."""
    import terminal
    choice = _choice(root, "execution")
    text = _request(root, "execution", prompt, ticket)
    run_id, folder = _run_folder(root)
    short = run_id[-8:]
    # Vagas fixas: a pasta do executor é `tr-seat-<n>`, reaproveitada entre tickets. Um CLI que pede confiança
    # por pasta (o Codex) pergunta uma vez por vaga, não uma vez por ticket.
    seats = os.path.join(root, ".claude", "worktrees")
    _free_dead_seats(root, seats)
    number = next(n for n in range(1, 100) if not os.path.exists(os.path.join(seats, f"tr-seat-{n}")))
    branch, work = f"tr-exec-{short}", os.path.join(seats, f"tr-seat-{number}")
    subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True)
    made = subprocess.run(["git", "worktree", "add", "-q", "-b", branch, work, "HEAD"], cwd=root, capture_output=True, text=True)
    if made.returncode:
        raise ValueError(f"o Git não criou o worktree do executor: {(made.stderr or made.stdout).strip()[-200:]}")
    report = os.path.join(work, ".harness-run", f"executor-{short}.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(os.path.join(os.path.dirname(report), ".gitignore"), "w", encoding="utf-8") as stream:
        stream.write("*\n")
    request = os.path.join(folder, "pedido.txt")
    with open(request, "w", encoding="utf-8") as stream:
        stream.write(text + f"\n\nYou work in your own worktree, `{work}`, on branch `{branch}`, born from the demand "
                     "branch. " + ("Do not commit: your sandbox cannot write to `.git`, and it may refuse to listen "
                                   "on a port. Leave the files in place; if a check needs a port, say the exact command "
                                   "in the report and the orchestrator runs it. " if choice["cli"] == "codex" else
                                   "Commit your work there; ") + "do not merge and do not switch branches. You report to the "
                     f"orchestrator: as the LAST thing you do, write `{report}` with a first line DONE or BLOCKED and "
                     "up to 8 lines of what you did, the checks you ran and what is left. Do not ask questions in "
                     "this terminal: nobody answers them here.\n")
    subject = os.path.basename(ticket)[:-3] if ticket and ticket.endswith(".md") else (ticket or short)
    session = terminal.name("exec", subject, choice["model"])
    import time
    started = time.time()
    terminal.open_agent(work, session, choice["cli"], _runtime_model(choice), request,
                        {"FULLCHICO_ROLE": "execution", "FULLCHICO_RUN_DIR": folder, "TR_REPORT": report},
                        record=os.path.join(folder, "terminal.raw.log"))
    with open(os.path.join(folder, "dispatch.json"), "w", encoding="utf-8") as stream:
        json.dump({"session": session, "report": report, "ticket": ticket, "branch": branch, "worktree": work,
                   "cli": choice["cli"], "started": started}, stream)
    print(json.dumps({"id": run_id, "status": "running", "terminal": session, "branch": branch,
                      "wait": f"tr-harness models wait {run_id}"}, ensure_ascii=False))
    return 0


HUMAN_GRACE = 90  # segundos que uma tela de confiança pode ficar aberta antes de virar bloqueio do dono


def _terminal_state(root, run_id, folder):
    """(estado, texto): `done`/`blocked` com o relato, `human`/`dead` com o motivo, ou `running`."""
    import time
    import terminal
    with open(os.path.join(folder, "dispatch.json"), encoding="utf-8") as stream:
        dispatch = json.load(stream)
    report = dispatch["report"] if os.path.isabs(dispatch["report"]) else os.path.join(root, dispatch["report"])
    head = f"== {dispatch.get('ticket') or run_id} · branch `{dispatch.get('branch', '')}` · terminal `{dispatch['session']}`\n"
    if os.path.isfile(report):
        with open(report, encoding="utf-8") as stream:
            text = stream.read()
        log = os.path.join(folder, "terminal.log")
        terminal.stop(dispatch["session"], log)  # o executor é descartável: relatou, é desmontado
        work = f"worktree: {dispatch['worktree']}\n" if dispatch.get("worktree") else ""
        record = terminal.transcript(dispatch.get("cli", "claude"), dispatch.get("worktree") or root, dispatch.get("started", 0))
        trail = f"log: {log}\n" + (f"transcript: {record}\n" if record else "")
        return ("done" if text.lstrip().upper().startswith("DONE") else "blocked"), head + work + trail + text
    if not terminal.alive(dispatch["session"]):
        return "dead", head + "encerrou sem gravar o relato"
    try:
        screen = terminal.read(dispatch["session"])
        if terminal.settle(dispatch["session"], screen):
            return "running", head
        human = terminal.waiting_on_human(screen)
    except terminal.Unavailable:
        return "dead", head + "encerrou sem gravar o relato"
    if not human:
        return "running", head
    # o dono pode estar olhando e responder em seguida: só vira bloqueio se a tela ficar parada
    mark = os.path.join(folder, "human-since")
    if not os.path.exists(mark):
        open(mark, "w").close()
    if time.time() - os.path.getmtime(mark) < HUMAN_GRACE:
        return "running", head
    return "human", head + "espera uma resposta que só o dono dá:\n" + human


def _detached_wait(root, run_ids, timeout):
    """Espera vários processos destacados (os revisores) de uma vez: volta quando todos saíram."""
    import time
    deadline = time.monotonic() + timeout
    def done(one):
        return os.path.isfile(os.path.join(_state_dir(root), one, "exit"))
    while not all(done(one) for one in run_ids):
        if time.monotonic() >= deadline:
            print(json.dumps({"status": "running", "running": [r for r in run_ids if not done(r)],
                              "wait": "tr-harness models wait " + " ".join(run_ids)}, ensure_ascii=False))
            return 3
        time.sleep(1)
    worst = 0
    for one in run_ids:
        base = os.path.join(_state_dir(root), one)
        with open(os.path.join(base, "exit"), encoding="utf-8") as stream:
            worst = max(worst, int(stream.read().strip() or 1))
        for name, out in (("result.out", sys.stdout), ("result.err", sys.stderr)):
            with open(os.path.join(base, name), encoding="utf-8") as stream:
                out.write(stream.read())
    return worst


def _review_in_terminal(root, choice, prompt, folder, gate_name, agent):
    """O revisor do portão abre num terminal próprio; o veredito volta num arquivo, e quem assina é este comando."""
    import time
    import terminal
    report = os.path.join(root, ".harness-run", f"review-{gate_name}-{os.path.basename(folder)[-8:]}.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    ignore = os.path.join(os.path.dirname(report), ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as stream:
            stream.write("*\n")
    try:
        instructions = _agent_instructions(root, agent, choice["cli"])
    except ValueError:
        instructions = ""
    request = os.path.join(folder, "pedido-terminal.txt")
    with open(request, "w", encoding="utf-8") as stream:
        base = prompt.split("Agent instructions:\n")[0]
        stream.write(base + (f"Agent instructions (follow them in full: they say how deep this review goes):\n{instructions}\n" if instructions else "")
                     + f"\nYou are in your own terminal; nobody answers questions here. You do not edit the project. As "
                     f"the LAST thing you do, write your whole answer, ending with the three lines (VERDICT, COMMIT, "
                     f"SUMMARY), to `{report}` (a folder ignored by git, outside the content you are judging).\n")
    session = terminal.name("rev", gate_name, choice["model"])
    terminal.open_agent(root, session, choice["cli"], _runtime_model(choice), request, {"TR_ROLE": "reviewer", "TR_REPORT": report},
                        record=os.path.join(folder, "terminal.raw.log"))
    deadline, since = time.monotonic() + 1500, None
    while not os.path.isfile(report):
        if not terminal.alive(session) or time.monotonic() >= deadline:
            break
        try:
            screen = terminal.read(session)
            human = None if terminal.settle(session, screen) else terminal.waiting_on_human(screen)
        except terminal.Unavailable:
            break
        since = (since or time.monotonic()) if human else None
        if since and time.monotonic() - since > HUMAN_GRACE:
            break
        time.sleep(1)
    text = ""
    if os.path.isfile(report):
        with open(report, encoding="utf-8") as stream:
            text = stream.read()
        os.remove(report)  # o veredito já foi lido; o arquivo não fica na pasta do projeto
    log = os.path.join(folder, "terminal.log")
    terminal.stop(session, log)
    output = os.path.join(folder, "1-terminal-review.out")
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(text)
    return {"cli": choice["cli"], "model": choice["model"], "model_id": _runtime_model(choice), "code": 0 if text else 1,
            "output": output, "erros": log, "limit": False, "terminal": session, "text": text}


def _terminal_wait(root, run_ids, timeout):
    """Espera vários executores de uma vez: volta quando todos relataram, ou quando um precisa de gente."""
    import time
    deadline, states = time.monotonic() + timeout, {}
    while True:
        for run_id in run_ids:
            if states.get(run_id, ("running",))[0] == "running":
                states[run_id] = _terminal_state(root, run_id, os.path.join(_state_dir(root), run_id))
        kinds = [states[r][0] for r in run_ids]
        if all(k in ("done", "blocked") for k in kinds) or any(k in ("dead", "human") for k in kinds):
            break
        if time.monotonic() >= deadline:
            print(json.dumps({"status": "running", "running": [r for r in run_ids if states[r][0] == "running"],
                              "wait": "tr-harness models wait " + " ".join(run_ids)}, ensure_ascii=False))
            return 3
        time.sleep(1)
    for run_id in run_ids:
        print(states[run_id][1].rstrip() + "\n")
    if any(k in ("dead", "human") for k in kinds):
        waiting = [r for r in run_ids if states[r][0] == "human"]
        print("Um executor não consegue seguir: é bloqueio do dono. Reporte ao maestro; não troque de executor por "
              "conta própria." + (" O terminal dele continua aberto, esperando o dono: diga no relato o nome do terminal "
              "e o run (" + ", ".join(waiting) + "); quando o dono responder, o próximo orquestrador adota esse executor "
              "em vez de despachar de novo." if waiting else ""), file=sys.stderr)
        return 1
    return 0 if all(k == "done" for k in kinds) else 1


def execute(root, role, prompt, ticket=None):
    if role not in ("planning", "execution", "review"):
        raise ValueError("papel deve ser planning, execution ou review")
    config = read_file(root).get("models") or {}
    choice = _choice(root, role)
    prompt = _request(root, role, prompt, ticket)
    run_id, folder = _run_folder(root)
    with open(os.path.join(folder, "pedido.txt"), "w", encoding="utf-8") as stream:
        stream.write(prompt)
    attempts = [_invoke(root, role, choice, prompt, folder, 1)]
    if attempts[0]["limit"]:
        support = _support(config, choice)
        if support:
            followup = (prompt + "\n\nHandoff: o modelo anterior atingiu limite. Examine o estado atual do "
                        "projeto e a saída em " + attempts[0]["output"] +
                        ". Continue o trabalho sem repetir alterações já feitas.")
            attempts.append(_invoke(root, role, support, followup, folder, 2))
    manifest = {"id": run_id, "role": role, "ticket": ticket, "attempts": attempts}
    with open(os.path.join(folder, "manifesto.json"), "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"id": run_id, "role": role, "models": [a["model_id"] for a in attempts],
                      "code": attempts[-1]["code"], "manifesto": os.path.join(folder, "manifesto.json")},
                     ensure_ascii=False))
    return 0 if attempts[-1]["code"] == 0 else 1


def main(argv):
    if not argv or argv[0] not in ("configure", "show", "run", "validate-gate", "wait", "integrate"):
        print("uso: fullchico-harness models configure [role cli:model ...] [gate:<name> cli:model ...] | show | "
              "run <role> [--prompt texto] [--ticket caminho] [--detach] | "
              "validate-gate <gate> [--ticket caminho] [--prompt texto] [--detach] | wait <id> [--timeout <s>] | "
              "integrate <id> [<id>...]",
              file=sys.stderr)
        return 2
    root, args = os.path.abspath("."), argv[1:]
    for i, arg in enumerate(args):
        if arg == "--project" and i + 1 < len(args):
            root = os.path.abspath(args[i + 1])
            del args[i:i + 2]
            break
    if not os.path.isdir(root):
        print(f"projeto não encontrado: {root}", file=sys.stderr)
        return 2
    if argv[0] in ("run", "validate-gate") and "--detach" in args:
        if argv[0] == "run" and args and args[0] == "execution":
            import terminal
            rest = [a for a in args[1:] if a != "--detach"]
            given = dict(zip(rest[::2], rest[1::2]))
            if terminal.executable() and set(given) <= {"--prompt", "--ticket"} and len(rest) % 2 == 0:
                try:
                    return terminal_execute(root, given.get("--prompt", ""), given.get("--ticket"))
                except terminal.Unavailable as error:
                    print(f"o executor não abriu: {error}. É bloqueio do dono: reporte ao maestro; não troque de "
                          "executor por conta própria.", file=sys.stderr)
                    return 1
                except ValueError as error:
                    print(error, file=sys.stderr)
                    return 2
        try:
            return detach(root, [argv[0]] + [a for a in args if a != "--detach"])
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
    try:
        if argv[0] == "integrate":
            if not args:
                raise ValueError("informe o id da execução")
            return integrate(root, args)
        if argv[0] == "wait":
            if not args:
                raise ValueError("informe o id da execução")
            timeout = 100
            if "--timeout" in args:
                at = args.index("--timeout")
                if at + 1 >= len(args) or not args[at + 1].isdigit():
                    raise ValueError("use: wait <id> [<id>...] [--timeout <segundos>]")
                timeout = int(args[at + 1])
                del args[at:at + 2]
            return wait(root, args[0], timeout, args[1:])
        if argv[0] == "configure":
            configure(root, args)
        elif argv[0] == "show":
            show(root)
        elif argv[0] == "validate-gate":
            if not args:
                raise ValueError("informe o nome do portão")
            name, args = args[0], args[1:]
            request, ticket = "", None
            while args:
                flag = args.pop(0)
                if flag not in ("--prompt", "--ticket") or not args:
                    raise ValueError("use --prompt texto e/ou --ticket caminho")
                value = args.pop(0)
                if flag == "--prompt":
                    request = value
                else:
                    ticket = value
            return validate_gate(root, name, ticket, request)
        else:
            if not args:
                raise ValueError("informe o papel para executar")
            role, args = args[0], args[1:]
            prompt, ticket = "", None
            while args:
                flag = args.pop(0)
                if flag not in ("--prompt", "--ticket") or not args:
                    raise ValueError("use --prompt texto e/ou --ticket caminho")
                value = args.pop(0)
                if flag == "--prompt":
                    prompt = value
                else:
                    ticket = value
            return execute(root, role, prompt, ticket)
        return 0
    except ValueError as error:
        print(error, file=sys.stderr)
        if "Sem permissão" in str(error):
            print(f"No seu terminal: {registry.owner_command(root, ['models', *argv])}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
