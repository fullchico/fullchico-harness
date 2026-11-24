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

ESPELHOS = {"claude": {"opus": ("codex", "sol"), "sonnet": ("codex", "luna"),
                       "haiku": ("codex", "terra"), "fable": ("codex", "astra")},
            "codex": {"sol": ("claude", "opus"), "luna": ("claude", "sonnet"),
                      "terra": ("claude", "haiku"), "astra": ("claude", "fable")}}
PAPEIS = ("planejamento", "execucao", "revisao", "apoio")
PATH = os.path.join(".claude", "trilho.json")
CODEX_IDS = {"sol": "gpt-6.2-sol", "luna": "gpt-6-luna",
             "terra": "gpt-6.1-terra", "astra": "gpt-6.2-astra"}
RATE_LIMIT = ("rate limit", "rate_limit", "usage limit", "quota exceeded", "429", "limite de uso")


def ler(root):
    try:
        with open(os.path.join(root, PATH), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(".claude/trilho.json deve conter um objeto JSON")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError(f".claude/trilho.json não pôde ser lido: {error}") from error


def validar_papel(value):
    try:
        cli, modelo = value.split(":", 1)
    except (AttributeError, ValueError):
        raise ValueError("use cli:modelo, por exemplo claude:sonnet")
    if cli not in ("claude", "codex") or not modelo.strip():
        raise ValueError("CLI deve ser claude ou codex e o modelo não pode ser vazio")
    return {"cli": cli, "modelo": modelo.strip()}


def configurar(root, args):
    if os.environ.get("CLAUDECODE") == "1":
        raise ValueError("Sem permissão para alterar .claude/trilho.json nesta sessão do Claude Code. Rode no terminal do dono.")
    if args and len(args) % 2:
        raise ValueError("informe pares papel cli:modelo")
    chosen = {}
    gates = {}
    current_data = ler(root)
    available = current_data.get("portoes") or {}
    for i in range(0, len(args), 2):
        role, value = args[i], args[i + 1]
        selected = validar_papel(value)
        if role.startswith("portao:"):
            name = role.split(":", 1)[1]
            if name not in available:
                raise ValueError(f"portão não encontrado: {name}")
            if selected["cli"] != "claude":
                raise ValueError("modelo de portão no Agent do Claude deve usar claude:modelo; Codex usa o executor por papel")
            gates[name] = selected
        elif role in PAPEIS:
            chosen[role] = selected
        else:
            raise ValueError(f"papel inválido: {role}; use {', '.join(PAPEIS)} ou portao:<nome>")
    if not args:
        if not sys.stdin.isatty():
            raise ValueError("modo não interativo exige pares papel cli:modelo")
        print("Configure cada papel como cli:modelo (Enter mantém o atual).")
        current = (current_data.get("modelos") or {})
        for role in PAPEIS:
            old = current.get(role, {})
            default = f"{old.get('cli', '')}:{old.get('modelo', '')}" if old else ""
            value = input(f"{role} [{default}]: ").strip()
            if value:
                chosen[role] = validar_papel(value)
        for name, gate in available.items():
            if gate.get("momento") != "fim":
                continue
            old = (current.get("portoes") or {}).get(name, {})
            default = f"{old.get('cli', '')}:{old.get('modelo', '')}" if old else "padrão de revisão"
            value = input(f"revisor do portão {name} [{default}]: ").strip()
            if value:
                selected = validar_papel(value)
                if selected["cli"] != "claude":
                    raise ValueError("modelo de portão no Agent do Claude deve usar claude:modelo")
                gates[name] = selected
    data = current_data
    config = data.get("modelos") if isinstance(data.get("modelos"), dict) else {}
    for role, entry in chosen.items():
        config[role] = entry
    if gates:
        config.setdefault("portoes", {}).update(gates)
    data["modelos"] = config
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


def mostrar(root):
    config = ler(root).get("modelos") or {}
    if not isinstance(config, dict):
        raise ValueError("`modelos` deve ser um objeto em .claude/trilho.json")
    for role in PAPEIS:
        value = config.get(role)
        if role == "apoio" and not value:
            print("apoio: não configurado (usa o espelho inicial do papel que atingiu limite)")
            continue
        if not value:
            print(f"{role}: não configurado")
            continue
        cli, model = value.get("cli"), value.get("modelo")
        mirror = ESPELHOS.get(cli, {}).get(model.lower())
        mirror_text = f"; espelho {mirror[0]}:{mirror[1]}" if mirror else "; sem espelho inicial conhecido"
        available = "disponível" if shutil.which(cli) else "CLI indisponível no PATH"
        print(f"{role}: {cli}:{model}{mirror_text}; {available}")
    for name, value in sorted((config.get("portoes") or {}).items()):
        print(f"portao:{name}: {value['cli']}:{value['modelo']}")


def _runtime_model(choice):
    model = choice["modelo"]
    return CODEX_IDS.get(model.lower(), model) if choice["cli"] == "codex" else model


def _support(config, primary):
    explicit = config.get("apoio")
    if isinstance(explicit, dict) and explicit != primary:
        return explicit
    mirror = ESPELHOS.get(primary["cli"], {}).get(primary["modelo"].lower())
    return {"cli": mirror[0], "modelo": mirror[1]} if mirror else None


def _state_dir(root):
    result = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("execução exige um projeto Git; rode `fullchico-harness install` primeiro")
    return os.path.join(result.stdout.strip(), "harness-runs")


def _invoke(root, role, choice, prompt, folder, number):
    cli, model = choice["cli"], _runtime_model(choice)
    executable = shutil.which(cli)
    if not executable:
        raise ValueError(f"CLI `{cli}` não encontrada no PATH")
    output = os.path.join(folder, f"{number}-{cli}-{role}.out")
    error = os.path.join(folder, f"{number}-{cli}-{role}.err")
    if cli == "claude":
        command = [executable, "-p", "--model", model, "--output-format", "json"]
        if role == "revisao":
            command += ["--permission-mode", "plan"]
        else:
            command += ["--permission-mode", "auto"]
    else:
        command = [executable, "exec", "--model", model, "--json", "-o",
                   os.path.join(folder, f"{number}-last.txt"), "-"]
        command += ["--sandbox", "read-only" if role == "revisao" else "workspace-write"]
    try:
        result = subprocess.run(command, cwd=root, input=prompt, capture_output=True,
                                text=True, timeout=3600)
        status, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        status, stdout, stderr = 124, exc.stdout or "", "tempo limite de 1 hora atingido"
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
    with open(output, "w", encoding="utf-8") as stream:
        stream.write(stdout)
    with open(error, "w", encoding="utf-8") as stream:
        stream.write(stderr)
    return {"cli": cli, "modelo": choice["modelo"], "id_modelo": model, "codigo": status,
            "saida": output, "erros": error, "limite": status != 0 and any(s in (stderr + stdout).lower() for s in RATE_LIMIT)}


def executar(root, role, prompt, ticket=None):
    if role not in PAPEIS[:3]:
        raise ValueError("papel deve ser planejamento, execucao ou revisao")
    config = ler(root).get("modelos") or {}
    choice = config.get(role) if isinstance(config, dict) else None
    if not isinstance(choice, dict) or choice.get("cli") not in ("claude", "codex") or not choice.get("modelo"):
        raise ValueError(f"configure o papel `{role}` antes de executar")
    if ticket:
        import pathlib
        file = (pathlib.Path(root) / ticket).resolve()
        if not file.is_file() or not file.is_relative_to(pathlib.Path(root).resolve()):
            raise ValueError("ticket deve ser um arquivo dentro do projeto")
        prompt = f"Papel: {role}. Ticket: {ticket}\n\n{file.read_text()}\n\nPedido: {prompt}"
    elif not prompt:
        raise ValueError("informe --pedido ou --ticket")
    instructions = {
        "planejamento": "Você é o planejador. Defina requisitos, dependências, critérios e portões aplicáveis.",
        "execucao": "Você é o executor. Implemente a tarefa, registre evidências e deixe a revisão para outro agente.",
        "revisao": "Você é o revisor independente. Não edite arquivos. Examine código e evidências, liste defeitos concretos e conclua com VEREDITO: APPROVED ou REJECTED.",
    }
    prompt = instructions[role] + "\n\n" + prompt
    state = _state_dir(root)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = os.path.join(state, run_id)
    os.makedirs(folder, exist_ok=False)
    with open(os.path.join(folder, "pedido.txt"), "w", encoding="utf-8") as stream:
        stream.write(prompt)
    attempts = [_invoke(root, role, choice, prompt, folder, 1)]
    if attempts[0]["limite"]:
        support = _support(config, choice)
        if support:
            followup = (prompt + "\n\nHandoff: o modelo anterior atingiu limite. Examine o estado atual do "
                        "projeto e a saída em " + attempts[0]["saida"] +
                        ". Continue o trabalho sem repetir alterações já feitas.")
            attempts.append(_invoke(root, role, support, followup, folder, 2))
    manifest = {"id": run_id, "papel": role, "ticket": ticket, "tentativas": attempts}
    with open(os.path.join(folder, "manifesto.json"), "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"id": run_id, "papel": role, "modelos": [a["id_modelo"] for a in attempts],
                      "codigo": attempts[-1]["codigo"], "manifesto": os.path.join(folder, "manifesto.json")},
                     ensure_ascii=False))
    return 0 if attempts[-1]["codigo"] == 0 else 1


def main(argv):
    if not argv or argv[0] not in ("configurar", "mostrar", "executar"):
        print("uso: fullchico-harness modelos configurar [papel cli:modelo ...] [portao:<nome> claude:modelo ...] | mostrar | executar <papel> [--pedido texto] [--ticket caminho]", file=sys.stderr)
        return 2
    root, args = os.path.abspath("."), argv[1:]
    for i, arg in enumerate(args):
        if arg == "--projeto" and i + 1 < len(args):
            root = os.path.abspath(args[i + 1])
            del args[i:i + 2]
            break
    if not os.path.isdir(root):
        print(f"projeto não encontrado: {root}", file=sys.stderr)
        return 2
    try:
        if argv[0] == "configurar":
            configurar(root, args)
        elif argv[0] == "mostrar":
            mostrar(root)
        else:
            if not args:
                raise ValueError("informe o papel para executar")
            role, args = args[0], args[1:]
            prompt, ticket = "", None
            while args:
                flag = args.pop(0)
                if flag not in ("--pedido", "--ticket") or not args:
                    raise ValueError("use --pedido texto e/ou --ticket caminho")
                value = args.pop(0)
                if flag == "--pedido":
                    prompt = value
                else:
                    ticket = value
            return executar(root, role, prompt, ticket)
        return 0
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
