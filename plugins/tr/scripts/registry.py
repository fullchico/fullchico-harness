"""Registro de portões do projeto (`.claude/trilho.json`, chave `portoes`).

Portão = etapa obrigatória do fluxo, com momento (`inicio` ou `fim`) e um modo de assinar. O
carimbo é a prova, gravada pelo hook fora do repositório (ver `ledger.py`). Este módulo só lê e
decide; quem barra é o `gate.py`, quem assina é o `sign.py`.
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

MOMENTOS = ("inicio", "fim")
MODOS = ("comando", "artefato", "agente")
DEFINIR = "@definir"  # comando ainda sem dono: o portão barra até o dono definir
VERIFICADOR = "tr:qualidade-verificador"  # quem valida os portões de comando, um disparo por portão
# O invoker de cada validador do tr (`/tr:<portão>-<ação>`), para a mensagem apontar o caminho.
INVOKERS = {VERIFICADOR: "/tr:qualidade-verificar", "tr:bugs-cacador": "/tr:bugs-cacar"}
# Modelo por papel: a sessão principal (opus) planeja e orquestra; o subagente executa.
COMPLEXIDADE = {"simples": "haiku", "complexa": "sonnet"}
MODELO_EXECUTOR = "sonnet"
IGNORADOS = ("docs", ".claude", ".git")


class RegistryError(ValueError):
    """Registro inválido; a mensagem já vem em português, pronta para o dono."""


def _git(root, *args):
    return ledger._git(root, *args)


def toplevel(cwd):
    folder = os.path.realpath(cwd)
    while True:
        if os.path.isfile(os.path.join(folder, ".claude", "trilho.json")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return _git(cwd, "rev-parse", "--show-toplevel") or os.path.realpath(cwd)


def load(root):
    """Devolve {"codigo": [...] | None, "portoes": {...}}, ou None se o projeto não tem portões."""
    path = os.path.join(root, ".claude", "trilho.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise RegistryError(f".claude/trilho.json não pôde ser lido: {e}")
    if not isinstance(data, dict) or "portoes" not in data:
        return None
    portoes = data["portoes"]
    if not isinstance(portoes, dict) or not portoes:
        raise RegistryError("`portoes` em .claude/trilho.json deve ser um objeto com ao menos um portão.")
    codigo = data.get("codigo")
    if codigo is not None and not (isinstance(codigo, list) and all(isinstance(c, str) and c for c in codigo)):
        raise RegistryError("`codigo` em .claude/trilho.json deve ser uma lista de caminhos (texto).")
    base_ref = data.get("base_ref")
    if base_ref is not None and (not isinstance(base_ref, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", base_ref)):
        raise RegistryError("`base_ref` deve ser uma referência Git válida em texto.")
    for name, gate in portoes.items():
        _validate(name, gate)
    return {"codigo": codigo, "portoes": portoes, "base_ref": base_ref}


def has_gates(root):
    """O projeto tem registro de portões? Registro quebrado conta: quem aplica é o trilho."""
    try:
        return load(root) is not None
    except RegistryError:
        return True


def _validate(name, gate):
    where = f"portão `{name}` em .claude/trilho.json"
    if name == "entrega":
        raise RegistryError("`entrega` é reservado para a validação final (`portao entrega`).")
    if not re.fullmatch(r"[\w.-]+", name):
        raise RegistryError(f"{where}: o nome só pode ter letras, números, `_`, `.` e `-`.")
    if not isinstance(gate, dict):
        raise RegistryError(f"{where}: deve ser um objeto.")
    if gate.get("momento") not in MOMENTOS:
        raise RegistryError(f"{where}: `momento` deve ser `inicio` ou `fim` (veio {gate.get('momento')!r}).")
    mode = gate.get("assina")
    if mode not in MODOS:
        raise RegistryError(f"{where}: `assina` deve ser `comando`, `artefato` ou `agente` (veio {mode!r}).")
    if not isinstance(gate.get(mode), str) or not gate[mode].strip():
        raise RegistryError(f"{where}: `assina: {mode}` exige o campo `{mode}` preenchido.")
    for opt in ("valida", "descricao"):
        if opt in gate and not isinstance(gate[opt], str):
            raise RegistryError(f"{where}: `{opt}` deve ser texto.")
    if "sempre" in gate and not isinstance(gate["sempre"], bool):
        raise RegistryError(f"{where}: `sempre` deve ser true ou false.")


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
    """O caminho é código do app? Com `codigo`, por prefixo; sem, tudo menos docs/, .claude/, .md e o ignorado."""
    rel = relative(root, path)
    if rel is None:
        return False
    if reg is None:
        reg = load(root)
    codigo = (reg or {}).get("codigo")
    if codigo is not None:
        return any(rel == p.strip("/") or rel.startswith(p.strip("/") + "/") for p in codigo)
    if rel.split("/")[0] in IGNORADOS or rel.endswith(".md"):
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
                   glob.glob(os.path.join(root, gate["artefato"]), recursive=True) if os.path.isfile(f))
    active = os.path.join(root, ".claude", "demanda-atual")
    if gate["artefato"].startswith("docs/specs/") and os.path.isfile(active):
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
        files = [f for f in files if f.startswith(f"docs/specs/{demand}/")]
    return files


def dirty(root, files=None):
    """Carimbos usam o estado atual; mudanças sem commit são válidas."""
    return False


def _hash(*parts):
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def stamp_key(root, gate):
    """Chave do carimbo (40 hex). Fim: snapshot do código. Início: artefato ou definição do portão."""
    if gate["momento"] == "fim":
        return ledger.head(root)
    if gate["assina"] == "artefato":
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


def stamped_commit(root, name, gate):
    """O commit cujo carimbo vale para o topo, ou None.

    Início: a chave do plano. Fim: o topo; ou um commit anterior carimbado, se do carimbo até o topo
    só mudou documentação (um commit de relatório não refaz a rodada inteira de portões).
    """
    key = stamp_key(root, gate)
    if not key:
        return None
    if ledger.has(root, name, key):
        return key
    return None


def satisfied(root, name, reg=None):
    reg = reg or load(root)
    return stamped_commit(root, name, reg["portoes"][name]) is not None


_PORTOES = re.compile(r"(?mi)^[\s>*_-]*port(?:õ|o)es[*_]*:[*_]*\s*(.+?)\s*$")


def passaporte(root, reg):
    """Os portões que a demanda pede: a linha `Portões: a, b` da spec ativa (o artefato dos portões
    de início). None quando nenhuma spec traz a linha: aí valem todos os portões de fim."""
    found = None
    active = os.path.join(root, ".claude", "demanda-atual")
    demand = None
    if os.path.isfile(active):
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
    for gate in reg["portoes"].values():
        if gate["momento"] != "inicio" or gate["assina"] != "artefato":
            continue
        for rel in artifact_files(root, gate):
            if demand and not rel.startswith(f"docs/specs/{demand}/"):
                continue
            with open(os.path.join(root, rel), encoding="utf-8") as stream:
                text = stream.read()
            for m in _PORTOES.finditer(text):
                # nome como o registro escreve: sem crase, negrito ou pontuação em volta (`e2e`, **seo**, e2e.)
                names = {re.sub(r"^[^\w]+|[^\w]+$", "", n) for n in re.split(r"[,;\s]+", m.group(1))}
                found = (found or set()) | {n for n in names if n}
    return found


def exigidos(root, momento, reg):
    """Os portões do momento que valem para esta demanda: no fim, os `sempre` (padrão) e os do passaporte."""
    names = [n for n, g in reg["portoes"].items() if g["momento"] == momento]
    import tasks  # tickets com passaporte próprio tornam portões opcionais locais à task
    if momento != "fim":
        return ([n for n in names if reg["portoes"][n].get("sempre", True)]
                if tasks.tickets(root) else names)
    pedido = passaporte(root, reg)
    if pedido is None:
        if tasks.tickets(root):
            pedido = set()
    if pedido is None:
        return names
    return [n for n in names if reg["portoes"][n].get("sempre", True) or n in pedido]


def missing(root, momento, reg=None):
    reg = reg or load(root)
    return [n for n in exigidos(root, momento, reg) if not satisfied(root, n, reg)]


def passos(name, gate):
    """O que fazer para o portão assinar, um passo por item."""
    mode = gate["assina"]
    if mode == "comando" and gate["comando"] == DEFINIR:
        return [f"o comando do portão `{name}` ainda não foi definido: só o dono o define, no terminal, com "
                f'`fullchico-harness portoes --definir {name} "<comando>"`']
    if mode == "comando":
        return [f"{INVOKERS[VERIFICADOR]} (o `{VERIFICADOR}` roda `{gate['comando']}` e o carimbo sai dele)"]
    if mode == "artefato":
        valida = f" e que passe em `{gate['valida']}`" if gate.get("valida") else ""
        depois = f"depois {INVOKERS[VERIFICADOR]} (o carimbo sai do `{VERIFICADOR}`)"
        return [f"produza `{gate['artefato']}` no projeto{valida}", depois]
    if gate["agente"] in INVOKERS:
        return [INVOKERS[gate["agente"]]]
    return [f"dispare o agente `{gate['agente']}` sobre o estado atual do projeto", "só ele assina"]


def howto(name, gate):
    return "; ".join(passos(name, gate))


def validadores(reg):
    """agent_type de cada validador -> os portões que ele valida (comando e artefato: o verificador)."""
    out = {}
    for name, gate in reg["portoes"].items():
        who = gate["agente"] if gate["assina"] == "agente" else VERIFICADOR
        if who:
            out.setdefault(who, []).append(name)
    return out


_MD = re.compile(r"[\w./-]+\.md\b")
_COMPLEXIDADE = re.compile(r"(?mi)^\s*complexidade:\s*(\w+)")


def modelo_do_ticket(root, prompt):
    """`haiku` ou `sonnet` pela linha `Complexidade:` do primeiro `.md` do repositório citado no pedido."""
    for ref in _MD.findall(prompt or ""):
        rel = relative(root, ref)
        if not rel:
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                m = _COMPLEXIDADE.search(f.read())
        except OSError:
            continue
        if m:
            return COMPLEXIDADE.get(m.group(1).lower())
    return None
