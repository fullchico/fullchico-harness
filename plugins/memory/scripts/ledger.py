"""Livro de carimbos do trilho: o que cada plugin assinou para cada commit.

Esta é a FONTE. Cada plugin é instalado sozinho, então o arquivo é copiado idêntico para
`plugins/<plugin>/scripts/ledger.py`; um teste confere que as cópias não divergem.

O carimbo mora fora do repositório (`~/.claude/tr/<id>/stamps/<carimbo>/<sha>.json`), onde o
agente com sandbox não grava: quem assina é um hook, não o agente. O `<id>` vem do repositório
comum, então um worktree e o clone principal compartilham o mesmo livro.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone


def _git(cwd, *args):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def state_dir(cwd):
    """Pasta do estado, identificada pelo projeto ou pelo Git comum dos worktrees."""
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ident = hashlib.sha256(os.path.realpath(common or cwd).encode()).hexdigest()[:16]
    return os.path.join(os.path.expanduser("~"), ".claude", "tr", ident)


def _content_files(root, ignored):
    """Arquivos que contam como conteúdo do projeto, em ordem estável.

    Num repositório Git, os versionados e os novos que o `.gitignore` não exclui: o que build e testes geram
    (`*.tsbuildinfo`, `next-env.d.ts`, relatórios) não muda o conteúdo, senão rodar um portão invalidaria o
    carimbo do outro. Fora do Git, a árvore inteira. Nos dois casos ficam de fora as pastas de `ignored` e os
    worktrees dos executores (`.claude/worktrees/`, outros estados do projeto). A configuração do harness no
    projeto (`.claude/`, `.codex/`) é arquivo do projeto como qualquer outro: mudou, o certificado cai."""
    def kept(rel):
        parts = rel.split("/")
        return not (any(p in ignored for p in parts[:-1]) or parts[:2] == [".claude", "worktrees"])
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root,
                             capture_output=True, timeout=60)
        listed = out.stdout.decode("utf-8", "surrogateescape").split("\0") if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        listed = None
    if listed is not None:
        return sorted({rel for rel in listed if rel and not rel.endswith("/") and kept(rel)})
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ignored)
        found += [os.path.relpath(os.path.join(folder, n), root).replace(os.sep, "/") for n in files]
    return sorted(rel for rel in found if kept(rel))


def head(cwd):
    """SHA do conteúdo atual do projeto, independente de Git."""
    digest = hashlib.sha1()
    ignored = {".git", ".harness-run", "node_modules", ".venv", "dist", "build", "coverage", ".next", ".turbo", ".cache", ".pytest_cache", "__pycache__", "docs"}
    root = os.path.realpath(cwd)
    for rel in _content_files(root, ignored):
        path = os.path.join(root, rel)
        if rel.endswith(".md") or os.path.islink(path) or not os.path.isfile(path):
            continue
        digest.update(rel.encode() + b"\0")
        try:
            with open(path, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            continue
    return digest.hexdigest()


def _path(cwd, stamp, commit):
    d = state_dir(cwd)
    if not d or not re.fullmatch(r"[\w.-]+", stamp) or not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        return None
    return os.path.join(d, "stamps", stamp, commit + ".json")


def sign(cwd, stamp, commit, plugin, version, by, summary):
    """Grava o carimbo de forma atômica (temporário + os.replace). Devolve o caminho, ou None."""
    path = _path(cwd, stamp, commit)
    if not path:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"stamp": stamp, "commit": commit, "plugin": plugin, "plugin_version": version, "by": by,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": summary}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def has(cwd, stamp, commit):
    path = _path(cwd, stamp, commit)
    return bool(path) and os.path.isfile(path)


def forget(cwd, stamp, commit):
    """Apaga o carimbo daquele commit, se houver."""
    path = _path(cwd, stamp, commit)
    if path and os.path.isfile(path):
        os.remove(path)


def log(cwd, plugin, what, detail):
    """Uma linha JSON em log.jsonl: signed, not_signed e por quê, blocked."""
    d = state_dir(cwd)
    if not d:
        return
    try:
        os.makedirs(d, exist_ok=True)
        line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "plugin": plugin, "what": what,
                "detail": detail}
        with open(os.path.join(d, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


_WRAPPERS = {"sudo", "env", "command", "time", "nohup", "rtk", "exec"}


def _split(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    commands, current = [], []
    for token in lex:
        if set(token) <= set(";&|()\n"):
            commands.append(current)
            current = []
        else:
            current.append(token)
    commands.append(current)
    return [c for c in commands if c]


_HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_]\w*)\1([^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)


def strip_heredocs(command):
    """O comando sem o corpo dos heredocs: o texto que vai para o arquivo não é comando.

    Fica a linha que abre o heredoc (onde está o redirecionamento de verdade, `cat > alvo <<EOF`).
    """
    return _HEREDOC.sub(lambda m: m.group(3), command)
