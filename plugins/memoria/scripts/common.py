"""O mínimo de git e de arquivos que a memória precisa. Python 3, só biblioteca padrão."""
import os
import re
import subprocess

_CONF_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _git(cwd, *args):
    try:
        r = subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=cwd, capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_root(cwd):
    folder = os.path.realpath(cwd)
    while True:
        if os.path.isfile(os.path.join(folder, ".claude", "trilho.json")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return _git(cwd, "rev-parse", "--show-toplevel") or os.path.realpath(cwd)


def head_sha(cwd):
    from ledger import head
    return _git(cwd, "rev-parse", "HEAD") or head(cwd)


def home() -> str:
    return os.path.expanduser("~")


def memory_dir(cwd):
    """Onde fica a memória derivada: dentro do diretório git comum.

    Local, fora dos arquivos versionados, igual para todos os worktrees e gravável pelo agente
    (ao contrário de ~/.claude). É o mesmo lugar em que o plugin antigo do harness gravava.
    """
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.join(common_dir, "harness-memory") if common_dir else os.path.join(os.path.realpath(cwd), ".harness-run", "memory")


def read_conf(path: str) -> dict:
    conf = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return conf
    for line in lines:
        m = _CONF_LINE.match(line.strip())
        if not m:
            continue
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        conf[m.group(1)] = value
    return conf
