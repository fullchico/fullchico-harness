"""Livro de carimbos do trilho: o que cada plugin assinou para cada commit.

Esta é a FONTE. Cada plugin é instalado sozinho, então o arquivo é copiado idêntico para
`plugins/<plugin>/scripts/ledger.py`; um teste confere que as cópias não divergem.

O carimbo mora fora do repositório (`~/.claude/trilho/<id>/stamps/<carimbo>/<sha>.json`), onde o
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
    """Pasta do estado do projeto em `cwd`, ou None fora de um repositório git."""
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    ident = hashlib.sha256(os.path.realpath(common).encode()).hexdigest()[:16]
    return os.path.join(os.path.expanduser("~"), ".claude", "trilho", ident)


def head(cwd):
    """Commit do topo (HEAD) do repositório em `cwd`, ou None."""
    return _git(cwd, "rev-parse", "HEAD")


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
    """Uma linha JSON em log.jsonl: assinou, não assinou e por quê, barrou."""
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
_SHELLS = {"bash", "sh", "zsh"}


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


def _is_send(words):
    while words and (words[0] in _WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
        words = words[1:]
    if not words:
        return False
    if os.path.basename(words[0]) in _SHELLS and "-c" in words[1:-1]:
        return is_send(words[words.index("-c") + 1])
    if words[0] == "gh":
        return words[1:3] == ["pr", "create"]
    if words[0] == "git":
        rest, i = words[1:], 0
        while i < len(rest) and rest[i].startswith("-"):  # git -C pasta push, git -c k=v push
            i += 2 if rest[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
        return i < len(rest) and rest[i] == "push"
    return False


def is_send(command):
    """O comando contém um envio (`git push`, `gh pr create`) em algum ponto do encadeamento?

    Texto citado não conta: `grep "git push" README` é um comando `grep`.
    """
    try:
        return any(_is_send(c) for c in _split(command))
    except ValueError:
        # aspas desbalanceadas: não dá para separar; na dúvida, trata como envio se o texto o menciona
        return bool(re.search(r"\bgit\s+push\b|\bgh\s+pr\s+create\b", command))
