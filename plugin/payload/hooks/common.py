"""Base dos hooks do harness: leitura de entrada, estado dos portões e configuração."""
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys

sys.dont_write_bytecode = True

GATES = ("seguranca", "revisao", "qualidade", "bugs", "ambiente")
_CONF_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def read_payload() -> dict:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


_WHERE = {}


def watch(hook: str, cwd) -> None:
    """Diz de que hook e de que repositório são as negações que vierem: é o que vai para o registro."""
    _WHERE.update(hook=hook, cwd=cwd if isinstance(cwd, str) else None)


def log(cwd, hook: str, what: str, detail: str = "") -> None:
    """Uma linha em `<estado>/log.jsonl`. Os hooks são silenciosos para a plataforma: sem isto, ninguém
    sabe o que foi negado, o que não foi carimbado nem se o trilho rodou. Nunca derruba o hook."""
    try:
        state = state_dir(cwd) if isinstance(cwd, str) else None
        if not state:
            return
        os.makedirs(state, exist_ok=True)
        import datetime
        line = {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "hook": hook, "what": what, "detail": detail[:400]}
        with open(os.path.join(state, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def deny(reason: str):
    if _WHERE.get("cwd"):
        log(_WHERE["cwd"], _WHERE.get("hook", "?"), "negou", reason)
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


def pendings_dir(cwd):
    """Onde ficam as pendências da feature deste worktree: achados simples do caçador de bugs,
    que não bloquearam o ticket mas precisam ser conferidos antes do push."""
    state, root = state_dir(cwd), repo_root(cwd)
    if not state or not root:
        return None
    feature = os.path.realpath(feature_root(root))
    return os.path.join(state, "pendings", hashlib.sha256(feature.encode("utf-8")).hexdigest()[:16])


def pendings(cwd) -> list:
    """Todas as pendências da feature, abertas e resolvidas, em ordem de criação."""
    folder = pendings_dir(cwd)
    found = []
    try:
        names = sorted(os.listdir(folder), key=lambda n: int(n[1:-5]) if n[1:-5].isdigit() else 0)
    except (OSError, TypeError):
        return found
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                found.append(json.load(f))
        except (OSError, ValueError):
            continue
    return found


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


AGENT_MARK = "/.claude/worktrees/"


def feature_root(root: str) -> str:
    """O worktree da feature a que este worktree pertence; ele mesmo, se não for de agente.

    O Claude Code cria os worktrees de agente sob o checkout principal, mesmo quando a
    sessão está no worktree de uma feature. A pasta não diz de quem ele é; o git diz: a
    feature é o worktree de cujo histórico o agente mais recentemente saiu.
    """
    if AGENT_MARK not in root:
        return root
    listed = _git(root, "worktree", "list", "--porcelain") or ""
    trees, path = [], None
    for line in listed.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("HEAD ") and path and AGENT_MARK not in path:
            trees.append((path, line[len("HEAD "):]))
    parent = root.split(AGENT_MARK)[0]
    main = trees[0][0] if trees else parent
    if os.path.realpath(parent) != os.path.realpath(main):
        return parent  # agente criado dentro da pasta da própria feature
    best = None
    for index, (path, tip) in enumerate(trees):
        base = _git(root, "merge-base", tip, "HEAD")
        ahead = _git(root, "rev-list", "--count", f"{base}..HEAD") if base else None
        if ahead is None or not ahead.isdigit():
            continue
        # Menos commits fora do histórico do candidato ganha; no empate, a feature e não o principal.
        rank = (int(ahead), index == 0, index)
        if best is None or rank < best[0]:
            best = (rank, path)
    return best[1] if best else parent


def file_digest(rel: str, data: bytes) -> str:
    """Impressão digital de um arquivo gerenciado.

    Arquivo JSON é comparado pelo conteúdo, não pelos bytes: o `claude plugin install`
    regrava o settings.json com as chaves em outra ordem, e isso não é alteração.
    """
    import hashlib
    if rel.endswith(".json"):
        try:
            data = json.dumps(json.loads(data.decode("utf-8")), sort_keys=True, ensure_ascii=False).encode("utf-8")
        except ValueError:
            pass
    return hashlib.sha256(data).hexdigest()


def conf_approval_path(root):
    """Onde fica a proposta de harness.conf que o dono acabou de ver, para este worktree."""
    import hashlib
    state = state_dir(root)
    if not state:
        return None
    key = hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()[:16]
    return os.path.join(state, "conf", key)


if __name__ == "__main__":
    # Uso pelos scripts de shell: common.py state-dir | common.py branch-base <sha> | common.py conf-approval <raiz>
    out = None
    if len(sys.argv) == 3 and sys.argv[1] == "feature-root":
        out = feature_root(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "conf-approval":
        out = conf_approval_path(sys.argv[2])
    if sys.argv[1:] == ["pendings"]:
        for item in pendings(os.getcwd()):
            if item.get("status") == "open":
                print(f"{item['id']}: {item['text']} (commit {item['commit'][:7]})")
        sys.exit(0)
    if sys.argv[1:] == ["state-dir"]:
        out = state_dir(os.getcwd())
    elif len(sys.argv) == 3 and sys.argv[1] == "branch-base":
        out = branch_base(os.getcwd(), sys.argv[2])
    if out:
        print(out)
        sys.exit(0)
    sys.exit(1)


# --- Código do aplicativo só muda pelo fluxo -------------------------------------------------
# No worktree da feature ninguém escreve código direto: os implementadores escrevem nos
# worktrees deles. O que não é código (documentos, arquivos do harness, o que o git ignora)
# segue livre. Só o dono libera a edição direta, por sessão (prompt_context.py).
FREE_DIRS = ("docs/", ".harness-run/", ".harness/", ".claude/", "harness.d/")
FREE_FILES = ("harness.conf", "skills-lock.json", "orca.yaml")
# Saída de comando e anotação solta não são código. O `.gitignore` é: ignorar um caminho o tiraria desta regra.
NOT_CODE = (".md", ".log", ".txt", ".out", ".tmp", ".patch", ".diff")
DENY_CODE = ("Neste worktree o código do aplicativo só muda pelo fluxo: invoque a skill `harness:entregar` com o "
             "pedido (quem escreve são os implementadores, nos worktrees deles). Edição direta só quando o dono "
             "liberar nesta sessão com `/harness:direto`. Não contorne por outro comando: diga ao dono o que falta.")


def is_code(cwd, path) -> bool:
    """O caminho é código do aplicativo no worktree de uma feature (e não num worktree de agente)?"""
    if not isinstance(cwd, str) or not isinstance(path, str) or not path:
        return False
    target = os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))
    if AGENT_MARK in target + os.sep:
        return False
    root = repo_root(cwd)
    base = os.path.realpath(root) if root else None
    if not base or AGENT_MARK in base + os.sep or not target.startswith(base + os.sep):
        return False
    rel = os.path.relpath(target, base)
    if rel.endswith(NOT_CODE) or rel in FREE_FILES or (rel + "/").startswith(FREE_DIRS):
        return False
    try:
        ignored = subprocess.run(["git", "-C", base, "check-ignore", "-q", "--", rel], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    return ignored.returncode != 0


def direct_path(cwd, session):
    state = state_dir(cwd)
    if not state or not isinstance(session, str) or not session:
        return None
    return os.path.join(state, "direct", re.sub(r"[^\w-]", "_", session))


def direct_open(cwd, session) -> bool:
    path = direct_path(cwd, session)
    return bool(path) and os.path.exists(path)
