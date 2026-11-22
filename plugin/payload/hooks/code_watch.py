#!/usr/bin/env python3
"""PostToolUse (Bash): confere, depois do comando, se ele alterou código do aplicativo fora do fluxo.

Ler o comando antes de rodar (service_guard.writes_code) é só aviso cedo: `python3 -c`, variável,
laço, `find -delete`, formatador e `git reset --hard` gravam sem que o texto do comando mostre.
Aqui não se adivinha nada: o service_guard guarda, antes do comando, o HEAD e os caminhos de código
sujos do worktree da feature (`begin`); este hook compara com o que ficou depois.

É violação, sem edição direta aberta: caminho de código sujo novo, caminho já sujo com outro
conteúdo, ou HEAD que andou por commit que não é merge e toca código. O comando já rodou, então a
saída é o código 2 com o que desfazer, que a plataforma mostra ao modelo. Erro do próprio hook
nunca derruba a sessão: é registrado e a saída é 0.
"""
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# Só a forma exata abre a janela do integrate: embutido noutro comando, o nome não vale nada.
INTEGRATE = re.compile(r"^(?:\./)?\.harness/integrate(?: [^\s;&|`$<>()]+){2}$")
BIG = 2 * 1024 * 1024  # acima disto o arquivo é comparado por tamanho e hora, não por conteúdo
STALE = 24 * 3600  # linha de base de comando que nunca chegou ao PostToolUse
SHOWN = 20


def _digest(path: str) -> str:
    try:
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode):
            return "link:" + os.readlink(path)
        if not stat.S_ISREG(info.st_mode):
            return "other"
        if info.st_size > BIG:
            return f"big:{info.st_size}:{info.st_mtime_ns}"
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return "gone"


def _run(root: str, *args) -> str:
    r = subprocess.run(["git", "-C", root, "-c", "core.quotepath=off", *args], capture_output=True, timeout=25)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]}: {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return r.stdout.decode("utf-8", "surrogateescape")


def snapshot(root: str) -> dict:
    """HEAD e os caminhos de código sujos do worktree: {caminho: [estado do git, resumo do conteúdo]}.

    O `git status` já deixa de fora o que o git ignora, que não é código (common.is_code)."""
    try:
        head = _run(root, "rev-parse", "-q", "--verify", "HEAD").strip()
    except RuntimeError:
        head = ""  # repositório ainda sem commit
    parts = _run(root, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    dirty, index = {}, 0
    while index < len(parts):
        entry = parts[index]
        index += 1
        if len(entry) < 4:
            continue
        code, names = entry[:2], [entry[3:]]
        if "R" in code or "C" in code:  # renomeado: o caminho de origem vem no campo seguinte
            names.append(parts[index])
            index += 1
        for name in names:
            if common.code_rel(name):
                dirty[name] = [code, _digest(os.path.join(root, name))]
    return {"head": head, "dirty": dirty}


def _baseline(state: str, payload: dict, command: str) -> str:
    key = payload.get("tool_use_id")
    if not isinstance(key, str) or not key:
        key = f"{payload.get('session_id')}-{hashlib.sha256(command.encode('utf-8', 'replace')).hexdigest()[:16]}"
    return os.path.join(state, "watch", re.sub(r"[^\w-]", "_", key)[:120] + ".json")


def begin(payload: dict, command: str, cwd: str) -> None:
    """Chamado pelo service_guard antes do comando. Falha aqui não nega o comando: fica registrada."""
    try:
        _begin(payload, command, cwd)
    except Exception as exc:
        common.log(cwd, "code_watch", "erro", f"linha de base: {exc}")


def _begin(payload: dict, command: str, cwd: str) -> None:
    session = payload.get("session_id")
    if INTEGRATE.match(command.strip()):
        # O integrate roda dentro do sandbox e nem sempre consegue gravar o próprio marcador.
        common.mark_writer(cwd, "integrate", "running")
    if common.direct_open(cwd, session):
        common.mark_writer(cwd, f"direct-{session}", "running")
        return
    root, state = common.repo_root(cwd), common.state_dir(cwd)
    if not root or not state:
        return
    root = os.path.realpath(root)
    if common.AGENT_MARK in root + os.sep:
        return  # worktree de agente: é onde o implementador escreve
    at = time.time()
    base = {"at": at, "root": root, **snapshot(root)}
    path = _baseline(state, payload, command)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for name in os.listdir(os.path.dirname(path)):  # comando negado depois deste hook não tem PostToolUse
        old = os.path.join(os.path.dirname(path), name)
        try:
            if at - os.stat(old).st_mtime > STALE:
                os.remove(old)
        except OSError:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(base, f)


def violations(base: dict, now: dict):
    """(sujos novos, já sujos que mudaram, tocados por commit que não é merge)."""
    before, after = base["dirty"], now["dirty"]
    fresh = sorted(p for p in after if p not in before)
    again = sorted(p for p in after if p in before and after[p][1] != before[p][1])
    committed = []
    if base["head"] and now["head"] and base["head"] != now["head"]:
        # Merge é a junção feita pelo integrate; pela primeira linha, os commits do implementador não contam.
        # E o que já está no remoto não foi escrito aqui: trazer a branch padrão é o passo 0 da entrega.
        names = _run(base["root"], "log", "--no-merges", "--first-parent", "--format=", "--name-only",
                     f"{base['head']}..{now['head']}", "--not", "--remotes").splitlines()
        committed = sorted({n for n in names if n and common.code_rel(n)})
    return fresh, again, committed


def message(base: dict, now: dict, fresh, again, committed) -> str:
    paths = sorted(set(fresh) | set(again) | set(committed))
    lines = ["code-watch: este comando alterou código do aplicativo no worktree da feature, fora do fluxo:"]
    lines += [f"  {p}" for p in paths[:SHOWN]]
    if len(paths) > SHOWN:
        lines.append(f"  ... e mais {len(paths) - SHOWN}")
    lines.append("Código do aplicativo só muda pelo fluxo (skill `harness:entregar`: quem escreve são os "
                 "implementadores, nos worktrees deles) ou com `/harness:direto` do dono. A alteração já "
                 f"aconteceu. Desfaça agora, numa chamada só, na raiz do worktree ({base['root']}), e diga ao dono o que falta:")
    quote = lambda names: " ".join(shlex.quote(n) for n in names)
    untracked = [p for p in fresh if now["dirty"][p][0] == "??"]
    tracked = sorted(set(committed) | {p for p in fresh if now["dirty"][p][0] != "??"})
    undo = [f"git reset --soft {base['head']}"] if committed else []
    if tracked:
        undo.append(f"git restore --staged --worktree -- {quote(tracked)}")
    if untracked:
        undo.append(f"git clean -f -- {quote(untracked)}")
    if undo:
        lines.append("  " + " && ".join(undo))
    if again:
        lines.append(f"Já tinham alteração antes do comando, e restaurar apagaria as duas: {quote(again)}. "
                     "Nesses, desfaça à mão só o que este comando mudou (`git diff -- <caminho>`).")
    lines.append("Se a alteração não veio deste comando (outro agente ou outra sessão no mesmo worktree), "
                 "não desfaça: relate ao dono.")
    return "\n".join(lines)


def main() -> int:
    payload = common.read_payload()
    command = (payload.get("tool_input") or {}).get("command")
    if payload.get("tool_name") != "Bash" or not isinstance(command, str):
        return 0
    # O comando pode ter saído do repositório com `cd`: o estado ainda se acha pela pasta do projeto.
    cwd = next((c for c in (payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR"))
                if isinstance(c, str) and common.state_dir(c)), None)
    if not cwd:
        return 0
    try:
        return check(payload, command, cwd)
    except Exception as exc:
        common.log(cwd, "code_watch", "erro", str(exc))
        return 0


def check(payload: dict, command: str, cwd: str) -> int:
    session = payload.get("session_id")
    if INTEGRATE.match(command.strip()):
        common.mark_writer(cwd, "integrate", "done")
    direct = common.direct_open(cwd, session)
    if direct:
        common.mark_writer(cwd, f"direct-{session}", "done")
    state = common.state_dir(cwd)
    path = _baseline(state, payload, command)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            base = json.load(f)
    finally:
        os.remove(path)
    if direct or common.writer_active(state, base["at"], time.time()):
        return 0
    now = snapshot(base["root"])
    fresh, again, committed = violations(base, now)
    if not (fresh or again or committed):
        return 0
    common.log(cwd, "code_watch", "violou", " ".join(sorted(set(fresh) | set(again) | set(committed))))
    sys.stderr.write(message(base, now, fresh, again, committed) + "\n")
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 0
    sys.exit(code)
