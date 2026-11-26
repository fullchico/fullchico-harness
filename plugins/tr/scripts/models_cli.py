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
ROLES = ("planning", "execution", "review", "support")
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


def _runtime_model(choice):
    model = choice["model"]
    return CODEX_IDS.get(model.lower(), model) if choice["cli"] == "codex" else model


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


def wait(root, run_id, timeout=100):
    """Espera o fim de uma execução destacada. Sai com o código dela, ou 3 se ainda está rodando."""
    import re
    import time
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", run_id):
        raise ValueError(f"id de execução inválido: {run_id}")
    folder = os.path.join(_state_dir(root), run_id)
    if not os.path.isdir(folder):
        raise ValueError(f"execução não encontrada: {run_id}")
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
        command += ["--approve-for-me"]
        command += ["--sandbox", "read-only" if role == "review" else "workspace-write"]
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
        stderr += ("\nos hooks do tr não rodaram nesta execução Codex. Abra `codex` na pasta do projeto, "
                   "revise e confie nos hooks do projeto, e rode de novo.\n")
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(stdout)
    with open(error, "w", encoding="utf-8") as stream:
        stream.write(stderr)
    return {"cli": cli, "model": choice["model"], "model_id": model, "code": status,
            "output": output, "erros": error, "limit": status != 0 and any(s in (stderr + stdout).lower() for s in RATE_LIMIT)}


def _agent_instructions(root, agent):
    """Instruções do agente do portão para uma revisão Codex em CLI separada."""
    name = agent.split(":")[-1]
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError(f"nome de agente inválido: {agent}")
    candidates = [os.path.join(root, ".codex", "agents", agent.replace(":", "-") + ".toml"),
                  os.path.join(root, ".claude", "agents", name + ".md"),
                  os.path.join(root, ".codex", "harness", "tr", "agents", name + ".md")]
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
    if not isinstance(choice, dict) or choice.get("cli") not in ("claude", "codex") or not choice.get("model"):
        raise ValueError(f"configure `gate:{name}` ou `review` antes de validar por CLI")
    if choice["cli"] == "codex":
        instructions = _agent_instructions(root, gate["agent"])
    else:
        instructions = ""
    snapshot = ledger.head(root)
    key = registry.stamp_key(root, gate)
    if not snapshot or not key or (gate["stage"] == "end" and registry.dirty(root)):
        raise ValueError("estado sem snapshot válido ou árvore suja; prepare a entrega antes da revisão")
    context = ""
    if ticket:
        with open(os.path.join(root, ticket), encoding="utf-8") as stream:
            context = f"Ticket: {ticket}\n{stream.read()}\n"
    prompt = (f"You are the independent reviewer of gate `{name}` ({gate['agent']}). "
              "Do not edit files. Examine the current state yourself; the executor's report is context, not proof. "
              f"Expected snapshot: {snapshot} (a tr content hash of the working files, not a Git commit: do not look "
              f"it up in Git; copy it verbatim into COMMIT)\n{context}Report: {request or '(none)'}\n"
              "Answer with concrete findings and end with exactly three lines: "
              "VERDICT: APPROVED or REJECTED, COMMIT: <the expected snapshot, verbatim>, SUMMARY: <one sentence>.\n"
              + (f"Agent instructions:\n{instructions}\n" if instructions else ""))
    _, folder = _run_folder(root)
    with open(os.path.join(folder, "pedido.txt"), "w", encoding="utf-8") as stream:
        stream.write(prompt)
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
    verdict_text = _final_text(final) if final["code"] == 0 else ""
    verdict = sign.once(r"^[ \t]*VERDICT: (APPROVED|REJECTED)[ \t]*$", verdict_text)
    commit = sign.once(r"^[ \t]*COMMIT: ([0-9a-f]{40})[ \t]*$", verdict_text)
    summary = sign.once(r"^[ \t]*SUMMARY: (\S.*?)[ \t]*$", verdict_text)
    current = ledger.head(root)
    accepted = bool(verdict and commit == snapshot == current and summary and
                    registry.stamp_key(root, gate) == key and
                    (gate["stage"] != "end" or not registry.dirty(root)))
    if accepted and verdict == "APPROVED":
        try:
            stamped = ledger.sign(root, name, key, "tr", sign.version(),
                                  f"{gate['agent']} via {final['cli']}:{final['model']}", summary)
            accepted = bool(stamped)
        except OSError:
            accepted = False
    elif accepted and verdict == "REJECTED":
        ledger.forget(root, name, key)
        import attempts as rejections  # `attempts` aqui é a lista de chamadas ao modelo
        rejections.reject(root, name, gate)
    manifest = {"gate": name, "agent": gate["agent"], "snapshot": snapshot,
                "attempts": attempts, "verdict": verdict if accepted else None,
                "stamped": accepted and verdict == "APPROVED"}
    manifest_path = os.path.join(folder, "manifesto.json")
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"gate": name, "model": f"{final['cli']}:{final['model']}",
                      "verdict": manifest["verdict"], "stamped": manifest["stamped"],
                      "manifesto": manifest_path}, ensure_ascii=False))
    return 0 if manifest["stamped"] else 1


def execute(root, role, prompt, ticket=None):
    if role not in ROLES[:3]:
        raise ValueError("papel deve ser planning, execution ou review")
    config = read_file(root).get("models") or {}
    choice = config.get(role) if isinstance(config, dict) else None
    if not isinstance(choice, dict) or choice.get("cli") not in ("claude", "codex") or not choice.get("model"):
        raise ValueError(f"configure o papel `{role}` antes de executar")
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
    prompt = instructions[role] + "\n\n" + prompt
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
    if not argv or argv[0] not in ("configure", "show", "run", "validate-gate", "wait"):
        print("uso: fullchico-harness models configure [role cli:model ...] [gate:<name> cli:model ...] | show | "
              "run <role> [--prompt texto] [--ticket caminho] [--detach] | "
              "validate-gate <gate> [--ticket caminho] [--prompt texto] [--detach] | wait <id> [--timeout <s>]",
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
        try:
            return detach(root, [argv[0]] + [a for a in args if a != "--detach"])
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
    try:
        if argv[0] == "wait":
            if not args:
                raise ValueError("informe o id da execução")
            timeout = 100
            if len(args) == 3 and args[1] == "--timeout" and args[2].isdigit():
                timeout = int(args[2])
            elif len(args) != 1:
                raise ValueError("use: wait <id> [--timeout <segundos>]")
            return wait(root, args[0], timeout)
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
