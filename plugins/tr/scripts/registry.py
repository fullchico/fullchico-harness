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
IGNORADOS = ("docs", ".claude", ".git")


class RegistryError(ValueError):
    """Registro inválido; a mensagem já vem em português, pronta para o dono."""


def _git(root, *args):
    return ledger._git(root, *args)


def toplevel(cwd):
    return _git(cwd, "rev-parse", "--show-toplevel") or cwd


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
    for name, gate in portoes.items():
        _validate(name, gate)
    return {"codigo": codigo, "portoes": portoes}


def has_gates(root):
    """O projeto tem registro de portões? Registro quebrado conta: quem aplica é o trilho."""
    try:
        return load(root) is not None
    except RegistryError:
        return True


def _validate(name, gate):
    where = f"portão `{name}` em .claude/trilho.json"
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
    """A referência da base: origin/HEAD, senão origin/main, main, master. None se nenhuma existe."""
    ref = _git(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if ref and _git(root, "rev-parse", "--verify", "-q", ref):
        return ref
    for cand in ("origin/main", "main", "master"):
        if _git(root, "rev-parse", "--verify", "-q", cand):
            return cand
    return None


def merge_base(root):
    b = base(root)
    return _git(root, "merge-base", "HEAD", b) if b else None


def branch(root):
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"


def artifact_files(root, gate):
    """Arquivos que casam com o glob `artefato`, adicionados ou modificados nesta branch (em commit)."""
    mb = merge_base(root)
    if not mb:
        return []
    out = _git(root, "diff", "--name-only", "--diff-filter=AM", mb, "HEAD") or ""
    return sorted(f for f in out.splitlines() if fnmatch.fnmatchcase(f, gate["artefato"]))


def dirty(root, files=None):
    """Há alteração sem commit (nos `files`, se dados)?"""
    args = ["status", "--porcelain"] + (["--", *files] if files else [])
    return bool(_git(root, *args))


def _hash(*parts):
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def stamp_key(root, gate):
    """Chave do carimbo (40 hex). Fim: o commit do topo. Início: o plano (branch + artefato, ou branch + base)."""
    if gate["momento"] == "fim":
        return ledger.head(root)
    if gate["assina"] == "artefato":
        files = artifact_files(root, gate)
        blobs = [_git(root, "rev-parse", f"HEAD:{f}") for f in files]
        return _hash(branch(root), *[f"{f} {b}" for f, b in zip(files, blobs)]) if files else None
    return _hash(branch(root), merge_base(root) or "sem-base")


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
    if gate["momento"] != "fim":
        return None
    revs = (_git(root, "rev-list", "--first-parent", f"--max-count={DOC_ONLY_DEPTH}", "HEAD") or "").splitlines()[1:]
    for commit in revs:
        changed = (_git(root, "diff", "--name-only", commit, "HEAD") or "").splitlines()
        if not all(doc_only(f) for f in changed):
            return None  # daqui para trás o diff só cresce: nenhum carimbo anterior vale
        if ledger.has(root, name, commit):
            return commit
    return None


def satisfied(root, name, reg=None):
    reg = reg or load(root)
    return stamped_commit(root, name, reg["portoes"][name]) is not None


def missing(root, momento, reg=None):
    reg = reg or load(root)
    return [n for n, g in reg["portoes"].items() if g["momento"] == momento and not satisfied(root, n, reg)]


def howto(name, gate):
    mode = gate["assina"]
    if mode == "comando" and gate["comando"] == DEFINIR:
        return (f"o comando do portão `{name}` ainda não foi definido: só o dono o define, no terminal, com "
                f'`fullchico-harness portoes --definir {name} "<comando>"`')
    if mode == "comando":
        return f"rode `portao {name}` (sozinho numa chamada): `{gate['comando']}`"
    if mode == "artefato":
        valida = f" e que passe em `{gate['valida']}`" if gate.get("valida") else ""
        return (f"produza e faça o commit de `{gate['artefato']}` nesta branch{valida}; depois rode `portao {name}` "
                "(sozinho numa chamada)")
    return f"dispare o agente `{gate['agente']}` sobre o commit do topo; só ele assina"
