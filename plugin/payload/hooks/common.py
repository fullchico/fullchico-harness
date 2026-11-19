"""Base dos hooks do harness: leitura de entrada, estado dos portões e configuração."""
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True

GATES = ("seguranca", "revisao")
_CONF_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def read_payload() -> dict:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def deny(reason: str):
    sys.stderr.write(reason.rstrip() + "\n")
    sys.exit(2)


def _git(cwd, *args):
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_root(cwd):
    return _git(cwd, "rev-parse", "--show-toplevel")


def state_dir(cwd):
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.join(common_dir, "harness") if common_dir else None


def head_sha(cwd):
    return _git(cwd, "rev-parse", "HEAD")


def git_dirs(cwd):
    """Diretórios git deste checkout: o comum a todos os worktrees e o do próprio worktree."""
    found = []
    for flag in ("--git-common-dir", "--absolute-git-dir"):
        args = ("rev-parse", "--path-format=absolute", flag) if flag == "--git-common-dir" else ("rev-parse", flag)
        value = _git(cwd, *args)
        if value:
            found.append(os.path.realpath(value))
    return found


DEFAULT_REFS = ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master",
                "refs/heads/main", "refs/heads/master")


def branch_base(cwd, sha):
    """Commit em que a branch de `sha` saiu da branch padrão; None se não der para saber.

    A branch padrão vem de DEFAULT_BRANCH no harness.conf, senão de origin/HEAD,
    senão de main ou master. Sem base não há como dizer o que a branch acrescenta.
    """
    root = repo_root(cwd)
    refs = []
    declared = read_conf(os.path.join(root, "harness.conf")).get("DEFAULT_BRANCH") if root else None
    if declared:
        refs += ["refs/remotes/origin/" + declared, "refs/heads/" + declared]
    refs += DEFAULT_REFS
    for ref in refs:
        if _git(cwd, "rev-parse", "-q", "--verify", ref + "^{commit}"):
            return _git(cwd, "merge-base", sha, ref)
    return None


def approval_path(state: str, gate: str, sha: str) -> str:
    return os.path.join(state, "approvals", gate, sha + ".json")


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


if __name__ == "__main__":
    # Uso pelos hooks de git: common.py branch-base <sha>
    if len(sys.argv) == 3 and sys.argv[1] == "branch-base":
        base = branch_base(os.getcwd(), sys.argv[2])
        if base:
            print(base)
            sys.exit(0)
    sys.exit(1)
