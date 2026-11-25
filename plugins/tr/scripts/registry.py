"""Registro de portões do projeto (`.claude/harness.json`, chave `gates`).

Portão = etapa obrigatória do fluxo, com momento (`start` ou `end`) e um modo de assinar. O
carimbo é a prova, gravada pelo hook fora do repositório (ver `ledger.py`). Este módulo só lê e
decide; quem barra é o `guard.py`, quem assina é o `sign.py`.
"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import attempts  # noqa: E402

STAGES = ("start", "middle", "end")
MODES = ("command", "artifact", "agent")
TO_DEFINE = "@define"  # comando ainda sem dono: o portão barra até o dono definir
ORCHESTRATORS = {"tr:orchestrator", "tr-orchestrator", "orchestrator"}
CHECKER = "tr:quality-checker"  # quem valida os portões de comando, um disparo por portão
# O invoker de cada validador do tr (`/tr:<portão>-<ação>`), para a mensagem apontar o caminho.
INVOKERS = {CHECKER: "/tr:quality-check", "tr:bug-hunter": "/tr:bugs-hunt", "tr:scope-checker": "/tr:scope-check"}
# Modelo por papel: a sessão principal planeja; o orquestrador coordena executores e fiscais.
COMPLEXITY = {"simple": "haiku", "complex": "sonnet"}
EXECUTOR_MODEL = "sonnet"
IGNORED = ("docs", ".claude", ".git", ".codex", ".agents")  # configuração e plano, não código do app


def owner_command(root, args):
    """O comando que o dono roda no terminal, na versão do harness fixada no projeto (o ref do marketplace)."""
    import shlex
    try:
        with open(os.path.join(root, ".claude", "settings.json"), encoding="utf-8") as f:
            ref = (json.load(f).get("extraKnownMarketplaces") or {}).get("fullchico", {}).get("source", {}).get("ref", "")
    except (OSError, ValueError, AttributeError):
        ref = ""
    spec = "@fullchico/harness" + ("@" + ref[1:] if isinstance(ref, str) and ref.startswith("v") else "")
    text = args if isinstance(args, str) else shlex.join(args)
    return f"npx {spec} {text}".rstrip()


OWNER_APPROVAL_TTL = 120  # segundos de validade, uso único: cobre o diálogo, não sobra para outro caminho


def owner_canonical(words):
    """O comando do dono sem `--project <pasta>`: é o texto que a aprovação cobre."""
    import shlex
    out, skip = [], False
    for word in words:
        if skip:
            skip = False
        elif word == "--project":
            skip = True
        else:
            out.append(word)
    return shlex.join(out)


def _approvals(root):
    return os.path.join(ledger.state_dir(root), "owner-approvals.json")


def _load_approvals(root):
    import time
    try:
        with open(_approvals(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    now = time.time()
    return {k: v for k, v in data.items() if isinstance(v, (int, float)) and v > now}


def grant_owner(root, canonical):
    """O hook pediu a aprovação do dono para este comando exato: vale uma vez, por pouco tempo."""
    import time
    data = _load_approvals(root)
    data[hashlib.sha256(canonical.encode()).hexdigest()] = time.time() + OWNER_APPROVAL_TTL
    os.makedirs(os.path.dirname(_approvals(root)), exist_ok=True)
    with open(_approvals(root), "w", encoding="utf-8") as f:
        json.dump(data, f)


def owner_approved(root, canonical):
    """O CLI dentro da sessão só grava com uma aprovação viva para este comando; ela é consumida aqui."""
    data = _load_approvals(root)
    key = hashlib.sha256(canonical.encode()).hexdigest()
    if key not in data:
        return False
    del data[key]
    with open(_approvals(root), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return True


class RegistryError(ValueError):
    """Registro inválido; a mensagem já vem em português, pronta para o dono."""


def _git(root, *args):
    return ledger._git(root, *args)


def toplevel(cwd):
    folder = os.path.realpath(cwd)
    while True:
        if os.path.isfile(os.path.join(folder, ".claude", "harness.json")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return _git(cwd, "rev-parse", "--show-toplevel") or os.path.realpath(cwd)


def load(root):
    """Devolve {"code": [...] | None, "gates": {...}}, ou None se o projeto não tem portões."""
    path = os.path.join(root, ".claude", "harness.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        # Registro só no formato antigo: sem barrar, os portões do projeto sumiriam em silêncio.
        if os.path.isfile(os.path.join(root, ".claude", "trilho.json")):
            raise RegistryError("o registro está no formato antigo (.claude/trilho.json). "
                                f"Rode `{owner_command(root, 'install')}` no seu terminal para migrar.")
        return None
    except (OSError, ValueError) as e:
        raise RegistryError(f".claude/harness.json não pôde ser lido: {e}")
    if not isinstance(data, dict) or "gates" not in data:
        return None
    gates = data["gates"]
    if not isinstance(gates, dict) or not gates:
        raise RegistryError("`gates` em .claude/harness.json deve ser um objeto com ao menos um portão.")
    code = data.get("code")
    if code is not None and not (isinstance(code, list) and all(isinstance(c, str) and c for c in code)):
        raise RegistryError("`code` em .claude/harness.json deve ser uma lista de caminhos (texto).")
    base_ref = data.get("base_ref")
    if base_ref is not None and (not isinstance(base_ref, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", base_ref)):
        raise RegistryError("`base_ref` deve ser uma referência Git válida em texto.")
    for name, gate in gates.items():
        _validate(name, gate)
    models = data.get("models") or {}
    if not isinstance(models, dict):
        raise RegistryError("`models` em .claude/harness.json deve ser um objeto.")
    return {"code": code, "gates": gates, "base_ref": base_ref, "models": models}


def has_gates(root):
    """O projeto tem registro de portões? Registro quebrado conta: quem aplica é o trilho."""
    try:
        return load(root) is not None
    except RegistryError:
        return True


def _validate(name, gate):
    where = f"portão `{name}` em .claude/harness.json"
    if name == "delivery":
        raise RegistryError("`delivery` é reservado para a validação final (`gate delivery`).")
    if not re.fullmatch(r"[\w.-]+", name):
        raise RegistryError(f"{where}: o nome só pode ter letras, números, `_`, `.` e `-`.")
    if not isinstance(gate, dict):
        raise RegistryError(f"{where}: deve ser um objeto.")
    if gate.get("stage") not in STAGES:
        raise RegistryError(f"{where}: `stage` deve ser `start`, `middle` ou `end` (veio {gate.get('stage')!r}).")
    mode = gate.get("signs")
    if mode not in MODES:
        raise RegistryError(f"{where}: `signs` deve ser `command`, `artifact` ou `agent` (veio {mode!r}).")
    if gate["stage"] == "middle" and mode == "agent":
        raise RegistryError(f"{where}: portão de meio aceita `command` ou `artifact`; agente próprio ainda não é suportado.")
    if not isinstance(gate.get(mode), str) or not gate[mode].strip():
        raise RegistryError(f"{where}: `signs: {mode}` exige o campo `{mode}` preenchido.")
    for opt in ("check", "description"):
        if opt in gate and not isinstance(gate[opt], str):
            raise RegistryError(f"{where}: `{opt}` deve ser texto.")
    if "always" in gate and not isinstance(gate["always"], bool):
        raise RegistryError(f"{where}: `always` deve ser true ou false.")
    if "attempts" in gate and (type(gate["attempts"]) is not int or gate["attempts"] < 0):
        raise RegistryError(f"{where}: `attempts` deve ser um inteiro não negativo.")
    if gate.get("approval", "auto") not in ("auto", "human"):
        raise RegistryError(f"{where}: `approval` deve ser `auto` ou `human`.")
    if gate.get("approval") == "human" and gate["stage"] != "end":
        raise RegistryError(f"{where}: aprovação humana só se aplica a portões finais.")


def relative(root, path):
    """Caminho relativo à raiz (com `/`), ou None se cair fora dela."""
    root = os.path.realpath(root)
    full = path if os.path.isabs(path) else os.path.join(root, path)
    full = os.path.join(os.path.realpath(os.path.dirname(full)), os.path.basename(full))
    rel = os.path.relpath(full, root)
    if rel == "." or rel.startswith(".."):
        return None
    return rel.replace(os.sep, "/")


def is_code(root, path, reg=None):
    """O caminho é código do app? Com `code`, por prefixo; sem, tudo menos docs/, .claude/, .md e o ignorado."""
    rel = relative(root, path)
    if rel is None:
        return False
    if reg is None:
        reg = load(root)
    code = (reg or {}).get("code")
    if code is not None:
        return any(rel == p.strip("/") or rel.startswith(p.strip("/") + "/") for p in code)
    if rel == ".gitignore" or rel.split("/")[0] in IGNORED or rel.endswith(".md"):
        return False
    r = subprocess.run(["git", "check-ignore", "-q", "--", rel], cwd=root, capture_output=True)
    return r.returncode != 0


def base(root):
    """Base Git configurada pelo projeto; por padrão, o primeiro commit local."""
    reg = load(root)
    ref = reg.get("base_ref") if reg else None
    if ref:
        return ref if _git(root, "rev-parse", "--verify", "-q", ref) else None
    roots = (_git(root, "rev-list", "--max-parents=0", "HEAD") or "").splitlines()
    return roots[0] if roots else None


def merge_base(root):
    b = base(root)
    return _git(root, "merge-base", "HEAD", b) if b else None


def branch(root):
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"


def artifact_files(root, gate):
    """Arquivos atuais que casam com o glob do portão."""
    import glob
    files = sorted(os.path.relpath(f, root).replace(os.sep, "/") for f in
                   glob.glob(os.path.join(root, gate["artifact"]), recursive=True) if os.path.isfile(f))
    active = os.path.join(root, ".claude", "current-demand")
    if gate["artifact"].startswith("docs/specs/") and os.path.isfile(active):
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
        files = [f for f in files if f.startswith(f"docs/specs/{demand}/")]
    return files


def dirty(root, files=None):
    """Carimbos usam o estado atual; mudanças sem commit são válidas."""
    return False


def _hash(*parts):
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def stamp_key(root, gate, ticket=None):
    """Chave do carimbo (40 hex). Fim: snapshot do código. Início: artefato ou definição do portão."""
    if gate["stage"] == "middle":
        if not ticket:
            return None
        try:
            with open(os.path.join(root, ticket), encoding="utf-8") as stream:
                content = stream.read()
        except OSError:
            return None
        content = re.sub(r"(?mi)^\s*Status:\s*(?:open|done)\s*$", "Status: <state>", content)
        version = hashlib.sha1(content.encode()).hexdigest()
        return _hash(ticket, version, ledger.head(root))
    if gate["stage"] == "end":
        return ledger.head(root)
    if gate["signs"] == "artifact":
        files = artifact_files(root, gate)
        if not files:
            return None
        blobs = []
        for file in files:
            with open(os.path.join(root, file), "rb") as stream:
                blobs.append(f"{file} {hashlib.sha1(stream.read()).hexdigest()}")
        return _hash(*blobs)
    return _hash(os.path.realpath(root), json.dumps(gate, sort_keys=True))


DOC_ONLY_DEPTH = 50  # quantos commits para trás o carimbo de fim é procurado


def doc_only(path):
    """Arquivo que não muda o que um portão de fim verifica: só documentação (`docs/` ou `.md`)."""
    return path.startswith("docs/") or path.endswith(".md")


def stamped_commit(root, name, gate, ticket=None):
    """O commit cujo carimbo vale para o topo, ou None.

    Início: a chave do plano. Fim: o topo; ou um commit anterior carimbado, se do carimbo até o topo
    só mudou documentação (um commit de relatório não refaz a rodada inteira de portões).
    """
    key = stamp_key(root, gate, ticket)
    if not key:
        return None
    stamp = scoped_stamp(name, ticket) if ticket else name
    if ledger.has(root, stamp, key):
        return key
    return None


def scoped_stamp(name, ticket):
    return f"{name}-{hashlib.sha1(ticket.encode()).hexdigest()[:12]}" if ticket else name


def satisfied(root, name, reg=None, ticket=None):
    reg = reg or load(root)
    gate = reg["gates"][name]
    key = stamped_commit(root, name, gate, ticket)
    if key is None:
        return False
    if gate["stage"] == "end" and (gate.get("approval") == "human" or attempts.status(root, name).get("intervention")):
        return ledger.has(root, "approval-" + name, key)
    return True


_GATES_LINE = re.compile(r"(?mi)^[\s>*_-]*gates[*_]*:[*_]*\s*(.+?)\s*$")


def passport(root, reg):
    """Os portões que a demanda pede: a linha `Gates: a, b` da spec ativa (o artefato dos portões
    de início). None quando nenhuma spec traz a linha: aí valem todos os portões de fim."""
    found = None
    active = os.path.join(root, ".claude", "current-demand")
    demand = None
    if os.path.isfile(active):
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
    for gate in reg["gates"].values():
        if gate["stage"] != "start" or gate["signs"] != "artifact":
            continue
        for rel in artifact_files(root, gate):
            if demand and not rel.startswith(f"docs/specs/{demand}/"):
                continue
            with open(os.path.join(root, rel), encoding="utf-8") as stream:
                text = stream.read()
            for m in _GATES_LINE.finditer(text):
                # nome como o registro escreve: sem crase, negrito ou pontuação em volta (`e2e`, **seo**, e2e.)
                names = {re.sub(r"^[^\w]+|[^\w]+$", "", n) for n in re.split(r"[,;\s]+", m.group(1))}
                found = (found or set()) | {n for n in names if n}
    return found


def required(root, stage, reg):
    """Os portões do momento que valem para esta demanda: no fim, os `always` (padrão) e os do passaporte."""
    names = [n for n, g in reg["gates"].items() if g["stage"] == stage]
    import tasks  # tickets com passaporte próprio tornam portões opcionais locais à task
    if stage == "middle":
        return []  # meio é sempre escopado a ticket e conferido por tasks.audit
    if stage != "end":
        return ([n for n in names if reg["gates"][n].get("always", True)]
                if tasks.tickets(root) else names)
    request = passport(root, reg)
    if request is None:
        if tasks.tickets(root):
            request = set()
    if request is None:
        return names
    return [n for n in names if reg["gates"][n].get("always", True) or n in request]


def missing(root, stage, reg=None):
    reg = reg or load(root)
    return [n for n in required(root, stage, reg) if not satisfied(root, n, reg)]


def steps(name, gate, models=None, root=None):
    """O que fazer para o portão assinar, um passo por item."""
    mode = gate["signs"]
    if mode == "command" and gate["command"] == TO_DEFINE:
        return [f"o comando do portão `{name}` ainda não foi definido: só o dono o define, no terminal, com "
                f'`{owner_command(root or ".", ["gates", "--set", name, "<command>"])}`']
    if mode == "command":
        return [f"{INVOKERS[CHECKER]} (o `{CHECKER}` roda `{gate['command']}` e o carimbo sai dele)"]
    if mode == "artifact":
        check_cmd = f" e que passe em `{gate['check']}`" if gate.get("check") else ""
        after_step = f"depois {INVOKERS[CHECKER]} (o carimbo sai do `{CHECKER}`)"
        return [f"produza `{gate['artifact']}` no projeto{check_cmd}", after_step]
    choice = ((models or {}).get("gates") or {}).get(name) or (models or {}).get("review")
    if isinstance(choice, dict) and choice.get("cli") in ("claude", "codex") and choice.get("model"):
        return [f"rode `tr-harness models validate-gate {name} --detach` "
                f"(fiscal {gate['agent']} em {choice['cli']}:{choice['model']})"]
    if gate["agent"] in INVOKERS:
        return [INVOKERS[gate["agent"]]]
    return [f"dispare o agente `{gate['agent']}` sobre o estado atual do projeto", "só ele assina"]


def howto(name, gate, models=None, root=None):
    return "; ".join(steps(name, gate, models, root))


def validators(reg):
    """agent_type de cada validador -> os portões que ele valida (comando e artefato: o verificador)."""
    out = {}
    for name, gate in reg["gates"].items():
        who = gate["agent"] if gate["signs"] == "agent" else CHECKER
        if who:
            out.setdefault(who, []).append(name)
    return out


_MD = re.compile(r"[\w./-]+\.md\b")
_COMPLEXITY = re.compile(r"(?mi)^\s*complexity:\s*(\w+)")


def ticket_model(root, prompt):
    """`haiku` ou `sonnet` pela linha `Complexity:` do primeiro `.md` do repositório citado no pedido."""
    for ref in _MD.findall(prompt or ""):
        rel = relative(root, ref)
        if not rel:
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                m = _COMPLEXITY.search(f.read())
        except OSError:
            continue
        if m:
            return COMPLEXITY.get(m.group(1).lower())
    return None


if __name__ == "__main__" and sys.argv[1:2] == ["owner"]:
    print(owner_command(toplevel(os.getcwd()), sys.argv[2:]))
