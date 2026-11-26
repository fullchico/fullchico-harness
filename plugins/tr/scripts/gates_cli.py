#!/usr/bin/env python3
"""`fullchico-harness gates [--analyze] [--write] [--default] [--set <portão> "<command>"] [--register <esboço.json>] [--project <folder>]`.

Lê o projeto e PROPÕE o registro de portões, com o porquê de cada um; com `--write`, grava em
`.claude/harness.json` (preservando as outras chaves) e protege o arquivo no sandbox. `--register`
grava os portões de um esboço JSON (`{"name": {portão}}`): acrescenta os novos e substitui os de mesmo nome.
`--remove <portão>` tira um portão do registro.

O registro é do dono: dentro de uma sessão com sandbox o arquivo é protegido e este comando para
antes de gravar qualquer coisa, dizendo para rodá-lo no terminal.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402

DEFAULT_REGISTRY = {
    "gates": {
        "process": {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md",
                     "description": "spec da mudança, saída da entrevista"},
        "domain": {"stage": "start", "signs": "artifact", "artifact": "GLOSSARY.md",
                   "description": "glossário do domínio, saída do planejamento (domain-modeling)"},
        "quality": {"stage": "end", "signs": "command", "command": "@discover"},
        "bugs": {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"},
        "scope": {"stage": "end", "signs": "agent", "agent": "tr:scope-checker",
                  "description": "a entrega cumpre a spec e os tickets, dentro do Files: de cada um"},
    }
}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def plugin_on(settings, prefix):
    enabled = settings.get("enabledPlugins") or {}
    return any(k.startswith(prefix) and v for k, v in enabled.items())


def quality_scripts(project):
    """Os scripts lint, typecheck e test do `package.json` (nessa ordem) e o gerenciador pelo lockfile."""
    scripts = read_json(os.path.join(project, "package.json")).get("scripts") or {}
    found = [s for s in ("lint", "typecheck", "test") if s in scripts]
    has = lambda f: os.path.isfile(os.path.join(project, f))  # noqa: E731
    return found, "pnpm" if has("pnpm-lock.yaml") else "yarn" if has("yarn.lock") else "npm"


def scripts_command(found, pm):
    run = {"pnpm": "pnpm {}", "yarn": "yarn {}", "npm": "npm run {}"}[pm]
    return " && ".join("npm test" if pm == "npm" and s == "test" else run.format(s) for s in found)


def discover(project):
    """Comando de checagem do projeto: o do `harness.json` antigo, senão os scripts do package.json, senão `@define`."""
    legacy = read_json(os.path.join(project, ".claude", "harness.json")).get("quality")
    if isinstance(legacy, dict) and isinstance(legacy.get("command"), str) and legacy["command"].strip():
        return legacy["command"]
    found, pm = quality_scripts(project)
    return scripts_command(found, pm) if found else "@define"


def merge(project, entries_in, replace=False):
    """Acrescenta ao registro os portões que faltam (resolvendo `@discover`). Com `replace` (o esboço do dono),
    também substitui os de mesmo nome e o `code`; sem ele (plugins que se registram), nunca toca em um que já
    existe. Devolve os nomes gravados. Não cria o arquivo se não há nada a gravar."""
    path = os.path.join(project, ".claude", "harness.json")
    data = read_json(path)
    gates = data.get("gates") if isinstance(data.get("gates"), dict) else {}
    new_items = {}
    # `code` no esboço: as pastas do código do app. Só entra se o registro ainda não tem a chave.
    code = entries_in.get("code")
    new_code = code if (isinstance(code, list) and code and all(isinstance(c, str) and c for c in code)
                        and ("code" not in data or (replace and data["code"] != code))) else None
    for gate_name, gate in entries_in.items():
        if gate_name == "code" or (gate_name in gates and not replace) or not isinstance(gate, dict):
            continue
        gate = dict(gate)
        if gate.get("command") == "@discover":
            gate["command"] = discover(project)
        if gates.get(gate_name) != gate:  # igual ao gravado: nada a regravar
            new_items[gate_name] = gate
    if not new_items and not new_code:
        return []
    check_writable(project)
    data["gates"] = {**gates, **new_items}
    if new_code:
        data["code"] = new_code
    write_json(path, data)
    protect_sandbox(project)
    return list(new_items) + (["code"] if new_code else [])


USAGE_TEXT = ('uso: fullchico-harness gates [--analyze] [--write] [--default] [--approve <portão>] [--parallel <n>] [--set <portão> "<comando>"] '
       "[--register <esboço.json>] [--remove <portão>] [--accept] [--project <pasta>]")


class NoPermission(Exception):
    """O registro (ou o settings que o protege) não pode ser gravado daqui."""


def _writable(path):
    """Tenta abrir para escrita sem mudar nada: o sandbox nega na abertura. Arquivo novo: testa a pasta."""
    try:
        if os.path.exists(path):
            with open(path, "a", encoding="utf-8"):
                pass
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            probe = path + ".gravavel"
            with open(probe, "w", encoding="utf-8"):
                pass
            os.remove(probe)
        return True
    except OSError:
        return False


def check_writable(project):
    """Antes de gravar: o registro e o settings (quando há sandbox a proteger) precisam aceitar escrita.

    Assim nada fica pela metade (registro gravado e settings sem a proteção)."""
    if os.environ.get("CLAUDECODE") == "1" and not registry.owner_approved(project, OWNER_COMMAND[0]):
        raise NoPermission(
            "Sem permissão para gravar .claude/harness.json nesta sessão do Claude Code.\n"
            "O registro de portões é do dono. Rode este comando no seu terminal, fora da sessão. Nada foi gravado.")
    targets_list = [os.path.join(project, ".claude", "harness.json")]
    sp = os.path.join(project, ".claude", "settings.json")
    if isinstance(read_json(sp).get("sandbox"), dict):
        targets_list.append(sp)
    denied = [a for a in targets_list if not _writable(a)]
    if denied:
        raise NoPermission(
            "Sem permissão para gravar " + " e ".join(os.path.relpath(a, project) for a in denied) + ".\n"
            "O registro de portões é do dono, e o sandbox da sessão o protege do agente. Rode este mesmo\n"
            "comando no seu terminal, fora da sessão do Claude Code. Nada foi gravado.")


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def protect_sandbox(project):
    """Com sandbox ligado no projeto, garante `.claude/harness.json` no `denyWrite`."""
    sp = os.path.join(project, ".claude", "settings.json")
    settings = read_json(sp)
    if isinstance(settings.get("sandbox"), dict):
        fs = settings["sandbox"].setdefault("filesystem", {})
        deny = fs.setdefault("denyWrite", [])
        if ".claude/harness.json" not in deny:
            deny.append(".claude/harness.json")
            write_json(sp, settings)
            print(f"acrescentado ao sandbox.filesystem.denyWrite: .claude/harness.json ({sp})")


def set_command(project, gate_name, command_text):
    """Troca só o comando de um portão que assina por comando. É do dono."""
    path = os.path.join(project, ".claude", "harness.json")
    data = read_json(path)
    gate = (data.get("gates") or {}).get(gate_name)
    if not isinstance(gate, dict) or gate.get("signs") != "command":
        print(f"portão `{gate_name}` não existe ou não assina por comando.", file=sys.stderr)
        return 2
    check_writable(project)
    gate["command"] = command_text
    write_json(path, data)
    print(f"portão `{gate_name}`: comando definido como `{command_text}`")
    return 0


def remove_gate(project, gate_name):
    """Tira um portão do registro. É do dono."""
    path = os.path.join(project, ".claude", "harness.json")
    data = read_json(path)
    if gate_name not in (data.get("gates") or {}):
        print(f"portão `{gate_name}` não existe; existem: {', '.join(data.get('gates') or {}) or 'nenhum'}.",
              file=sys.stderr)
        return 2
    check_writable(project)
    del data["gates"][gate_name]
    write_json(path, data)
    print(f"portão `{gate_name}` removido do registro")
    return 0


def accept(project):
    """O aceite do dono sobre o critério da demanda (spec e tickets), no fim da entrevista. É do dono."""
    import certs
    if (os.environ.get("CLAUDECODE") == "1" and not registry.owner_approved(project, OWNER_COMMAND[0])) \
            or os.environ.get("CODEX_THREAD_ID"):
        raise NoPermission("O aceite do critério é do dono, no diálogo de permissão ou no terminal.")
    criterion = certs.criterion(project)
    if not criterion:
        print("sem demanda ativa (.claude/current-demand) com spec em docs/specs/<demanda>/", file=sys.stderr)
        return 2
    refused = certs.certify(project, certs.ACCEPT, criterion, "APPROVED", certs.OWNER, "critério aceito pelo dono")
    if refused:
        print(refused, file=sys.stderr)
        return 1
    print(f"critério da demanda `{certs.demand(project)}` aceito pelo dono ({criterion[:10]}).")
    return 0


def approve(project, gate_name):
    """Aprovação explícita do dono, vinculada ao mesmo estado que o fiscal validou."""
    if (os.environ.get("CLAUDECODE") == "1" and not registry.owner_approved(project, OWNER_COMMAND[0])) \
            or os.environ.get("CODEX_THREAD_ID"):
        raise NoPermission("A aprovação humana deve ser executada pelo dono no terminal, fora da sessão do agente.")
    reg = registry.load(project)
    gate = (reg or {}).get("gates", {}).get(gate_name)
    if not gate or gate["stage"] != "end":
        print(f"portão final `{gate_name}` não encontrado.", file=sys.stderr)
        return 2
    key = registry.stamped_commit(project, gate_name, gate)
    if not key:
        print(f"portão `{gate_name}` ainda não passou pela validação técnica.", file=sys.stderr)
        return 1
    import certs
    refused = certs.certify(project, "approval-" + gate_name, key, "APPROVED", certs.OWNER, "aprovação humana explícita")
    if refused:
        print(refused, file=sys.stderr)
        return 1
    print(f"portão `{gate_name}` aprovado pelo dono no estado {key[:10]}.")
    return 0


def analyze(project):
    """Devolve (registro, [(portão, porquê)])."""
    p = lambda *a: os.path.join(project, *a)  # noqa: E731
    settings = read_json(p(".claude", "settings.json"))
    gates, why = {}, []

    grill = bool(glob.glob(p(".claude", "skills", "*grilling*"))) or plugin_on(settings, "mattpocock-skills")
    interview = " (entrevista com grilling)" if grill else ""
    if os.path.isdir(p("openspec")):
        gates["process"] = {"stage": "start", "signs": "command", "command": "openspec validate --all",
                               "description": "spec da mudança validada pelo OpenSpec" + interview}
        why.append(("process", "a pasta `openspec/` existe: a etapa é a spec valer, conferida por `openspec validate --all`"))
    elif os.path.isdir(p("docs", "specs")):
        gates["process"] = {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md",
                               "description": "spec da mudança, saída da entrevista" + (" (grilling)" if grill else "")}
        why.append(("process", "a pasta `docs/specs/` existe: a etapa é haver uma spec para a demanda atual"))
    if grill and "process" in gates:
        why.append(("process", "há skill de entrevista (grilling) no projeto: a descrição a cita"))

    if "process" in gates:
        gates["domain"] = dict(DEFAULT_REGISTRY["gates"]["domain"])
        why.append(("domain", "há spec da demanda: o glossário `GLOSSARY.md` é saída do planejamento e a etapa confere que existe"))

    found, pm = quality_scripts(project)
    if found:
        gates["quality"] = {"stage": "end", "signs": "command", "command": scripts_command(found, pm)}
        why.append(("quality", f"`package.json` tem os scripts {', '.join(found)}; gerenciador {pm} pelo lockfile"))

    gates["bugs"] = {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"}
    why.append(("bugs", "o caçador de bugs do tr (`/tr:bugs-hunt`) valida o diff num subagente limpo"))
    if "process" in gates:
        gates["scope"] = dict(DEFAULT_REGISTRY["gates"]["scope"])
        why.append(("scope", "há spec da demanda: o `tr:scope-checker` (`/tr:scope-check`) confere a entrega contra ela"))

    reg = {}
    code = [d for d in ("apps", "packages", "src") if os.path.isdir(p(d))]
    if code:
        reg["code"] = code
        why.append(("code", f"as pastas {', '.join(code)} existem: só elas contam como código do app"))
    reg["gates"] = gates
    return reg, why


def write_registry(project, reg):
    check_writable(project)
    path = os.path.join(project, ".claude", "harness.json")
    data = read_json(path)
    data.update(reg)
    write_json(path, data)
    print(f"gravado: {path}")
    protect_sandbox(project)


OWNER_COMMAND = [""]  # o comando desta execução, como o hook o aprovou


def main(argv):
    OWNER_COMMAND[0] = registry.owner_canonical(["gates", *argv])
    project, flags, i, setting, register, approving, parallel = ".", set(), 0, None, None, None, None
    removing = None
    while i < len(argv):
        if argv[i] == "--project":
            i += 1
            project = argv[i] if i < len(argv) else "."
        elif argv[i] == "--set" and i + 2 < len(argv):
            setting = (argv[i + 1], argv[i + 2])
            i += 2
        elif argv[i] == "--register" and i + 1 < len(argv):
            i += 1
            register = argv[i]
        elif argv[i] == "--remove" and i + 1 < len(argv):
            i += 1
            removing = argv[i]
        elif argv[i] == "--approve" and i + 1 < len(argv):
            i += 1
            approving = argv[i]
        elif argv[i] == "--parallel" and i + 1 < len(argv) and argv[i + 1].isdigit() and int(argv[i + 1]) >= 1:
            i += 1
            parallel = int(argv[i])
        elif argv[i] in ("--analyze", "--write", "--default", "--accept"):
            flags.add(argv[i])
        else:
            print(USAGE_TEXT, file=sys.stderr)
            return 2
        i += 1
    try:
        if "--accept" in flags:
            return accept(os.path.abspath(project))
        if approving:
            return approve(os.path.abspath(project), approving)
        if parallel:
            return set_parallel(os.path.abspath(project), parallel)
        if removing:
            return remove_gate(os.path.abspath(project), removing)
        return execute(os.path.abspath(project), flags, setting, register)
    except NoPermission as e:
        print(e, file=sys.stderr)
        print("Na sessão: rode este comando sozinho na chamada (sem `&&`, pipe ou redirecionamento); o hook pede a "
              "aprovação do dono ali mesmo.", file=sys.stderr)
        print(f"No terminal do dono: {registry.owner_command(os.path.abspath(project), ['gates', *argv])}", file=sys.stderr)
        return 1


def set_parallel(project, value):
    """Quantos executores rodam ao mesmo tempo. É do dono."""
    path = os.path.join(project, ".claude", "harness.json")
    data = read_json(path)
    if not isinstance(data.get("gates"), dict):
        print("o projeto ainda não tem registro de portões; rode /tr:configure.", file=sys.stderr)
        return 2
    check_writable(project)
    data["max_parallel"] = value
    write_json(path, data)
    print(f"executores simultâneos: até {value}")
    return 0


def default_registry(project):
    """O registro padrão do plugin, com o comando de qualidade tirado do próprio projeto."""
    reg = json.loads(json.dumps(DEFAULT_REGISTRY))
    reg["gates"]["quality"]["command"] = discover(project)
    return reg


def execute(project, flags, setting, register):
    if setting:
        return set_command(project, *setting)
    if register:
        draft_file = read_json(register)
        if not draft_file:
            print(f"esboço vazio ou inválido: {register}", file=sys.stderr)
            return 2
        if isinstance(draft_file.get("gates"), dict):  # esboço no formato do registro inteiro
            draft_file = {**draft_file["gates"], **({"code": draft_file["code"]} if "code" in draft_file else {})}
        target = os.path.join(project, ".claude", "harness.json")
        before = open(target, encoding="utf-8").read() if os.path.isfile(target) else None
        existing = set((read_json(target).get("gates") or {}) if before else {})
        names = merge(project, draft_file, replace=True)
        try:
            registry.load(project)
        except registry.RegistryError as error:  # nada inválido fica gravado
            if before is None:
                os.remove(target)
            else:
                with open(target, "w", encoding="utf-8") as stream:
                    stream.write(before)
            print(f"esboço recusado, nada foi gravado: {error}", file=sys.stderr)
            return 2
        for gate_name in names:
            if gate_name == "code":
                print(f"pastas de código registradas: {', '.join(draft_file['code'])}")
                continue
            gate = read_json(os.path.join(project, ".claude", "harness.json"))["gates"][gate_name]
            verb = "substituído" if gate_name in existing else "registrado"
            print(f"portão `{gate_name}` {verb}: {gate.get('command') or gate.get('agent') or gate.get('artifact')}")
        return 0
    if "--default" in flags:
        reg, why = default_registry(project), [("padrão", "o registro padrão do plugin; qualidade com o comando do projeto")]
    else:
        reg, why = analyze(project)
    print(json.dumps(reg, ensure_ascii=False, indent=2))
    print()
    for name, reason in why:
        print(f"- {name}: {reason}")
    if not reg["gates"]:
        print("\nNada reconhecido para propor; escreva `.claude/harness.json` à mão ou use --default.")
    elif "--write" in flags:
        print()
        write_registry(project, reg)
    else:
        print("\nProposta apenas; para gravar, rode de novo com --write.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
