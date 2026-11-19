"""Base dos hooks do harness: leitura de entrada, estado dos portões e configuração."""
import hashlib
import json
import os
import pwd
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


def home() -> str:
    """Pasta do usuário, pelo sistema e não pela variável HOME, que um comando pode trocar."""
    return pwd.getpwuid(os.getuid()).pw_dir


def state_root() -> str:
    return os.path.join(home(), ".claude", "harness")


def state_dir(cwd):
    """Onde ficam as aprovações e os hooks de git deste repositório.

    Fica em ~/.claude, que o sandbox do Bash não deixa o agente gravar, e não dentro
    do .git, que uma sessão num worktree consegue alterar. Um diretório por
    repositório, igual para todos os worktrees.
    """
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common_dir:
        return None
    repo_id = hashlib.sha256(os.path.realpath(common_dir).encode("utf-8")).hexdigest()[:16]
    return os.path.join(state_root(), repo_id)


def memory_dir(cwd):
    """Onde fica a memória derivada do repositório: o mapa do código e as âncoras.

    Dentro do diretório git comum: local, fora dos arquivos versionados, igual para
    todos os worktrees, e gravável pelo agente (ao contrário de ~/.claude).
    """
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.join(common_dir, "harness-memory") if common_dir else None


def request_path(state: str, gate: str, sha: str) -> str:
    return os.path.join(state, "requests", gate, sha + ".json")


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


def _remote_head(cwd):
    """Commit para o qual aponta o HEAD do remoto `origin`, perguntando ao remoto. None se não der."""
    try:
        r = subprocess.run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=cwd,
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "HEAD" and parts[0] != "ref:":
            return parts[0]
    return None


def branch_base(cwd, sha):
    """Commit em que a branch de `sha` saiu da branch padrão; None se não der para saber.

    A branch padrão é a que o remoto anuncia agora. As referências locais só são
    usadas quando o remoto não responde (sem rede): elas podem ser movidas por
    qualquer comando, e por isso o push confere de novo, sempre contra o remoto.
    """
    remote = _remote_head(cwd)
    if remote and _exists(cwd, remote):
        return _git(cwd, "merge-base", sha, remote)
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


def _exists(cwd, sha) -> bool:
    try:
        return subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], cwd=cwd,
                              capture_output=True).returncode == 0
    except OSError:
        return False


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
    # Uso pelos scripts de shell: common.py state-dir | common.py branch-base <sha>
    out = None
    if sys.argv[1:] == ["state-dir"]:
        out = state_dir(os.getcwd())
    elif len(sys.argv) == 3 and sys.argv[1] == "branch-base":
        out = branch_base(os.getcwd(), sys.argv[2])
    if out:
        print(out)
        sys.exit(0)
    sys.exit(1)
