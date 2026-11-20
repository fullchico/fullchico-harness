"""Apoio dos testes: repositórios git temporários e execução de hooks."""
import atexit
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "plugin/payload/hooks"
sys.path.insert(0, str(HOOKS))

# Isola os testes da configuração git da máquina (hooks globais, assinatura).
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


def _tmpdir() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="harness t ")).resolve()
    atexit.register(shutil.rmtree, d, True)
    return d


def git(repo, *args) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.rstrip("\n")


def _forget_state(repo) -> None:
    """O estado do harness de um repositório de teste fica em ~/.claude/harness; apaga ao sair."""
    import common
    state = common.state_dir(str(repo))
    if state:
        atexit.register(shutil.rmtree, state, True)


def make_repo(name="proj dir") -> pathlib.Path:
    repo = _tmpdir() / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    _forget_state(repo)
    git(repo, "config", "user.name", "Teste")
    git(repo, "config", "user.email", "teste@example.com")
    (repo / "README.md").write_text("# projeto\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "chore: initial commit")
    return repo


def write_tmp(text: str) -> str:
    f = _tmpdir() / "arquivo.txt"
    f.write_text(text)
    return str(f)


def run_hook(script: str, payload, cwd=None, raw=None):
    data = raw if raw is not None else json.dumps(payload)
    r = subprocess.run([sys.executable, str(HOOKS / script)], input=data,
                       capture_output=True, text=True, cwd=cwd, timeout=60)
    return r.returncode, r.stdout, r.stderr


def read_approval(repo, gate):
    """Aprovação gravada para o commit atual do repositório, como dicionário."""
    import common
    path = common.approval_path(common.state_dir(str(repo)), gate, git(repo, "rev-parse", "HEAD"))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sync(repo, *extra):
    return subprocess.run([sys.executable, str(ROOT / "plugin/bin/sync"), str(repo),
                           "--version", "v0.1.0", *extra], capture_output=True, text=True)


def clone_repo(origin, name="work dir") -> pathlib.Path:
    """Clone de trabalho de `origin`, com identidade de commit configurada."""
    repo = _tmpdir() / name
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Teste")
    git(repo, "config", "user.email", "teste@example.com")
    _forget_state(repo)
    return repo


def commit_all(repo, subject: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", subject)
    return git(repo, "rev-parse", "HEAD")


def commit_file(repo, path: str, subject: str) -> str:
    target = pathlib.Path(repo) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(subject + "\n")
    return commit_all(repo, subject)


def clone_self_with_tags(name: str, tags: dict) -> pathlib.Path:
    """Cópia deste repositório como "upstream" local, com uma tag por entrada.

    `tags` mapeia tag -> None ou (caminho relativo, texto a acrescentar antes da tag).
    """
    up = _tmpdir() / name
    shutil.copytree(ROOT, up, ignore=shutil.ignore_patterns(".git", ".superpowers", "__pycache__", "*.pyc"))
    git(up, "init", "-q", "-b", "main")
    git(up, "config", "user.name", "Teste")
    git(up, "config", "user.email", "teste@example.com")
    for tag, change in tags.items():
        if change:
            with open(up / change[0], "a", encoding="utf-8") as f:
                f.write(change[1])
        git(up, "add", "-A")
        git(up, "commit", "-q", "--allow-empty", "-m", f"chore: release {tag}")
        git(up, "tag", tag)
    return up


def owner_approve(repo, gate, resumo="ok"):
    """Roda .harness/approve como o dono: com um terminal de verdade na entrada."""
    import pty
    master, slave = pty.openpty()
    try:
        return subprocess.run([str(pathlib.Path(repo) / ".harness/approve"), gate, resumo], cwd=str(repo),
                              stdin=slave, capture_output=True, text=True)
    finally:
        os.close(master)
        os.close(slave)


def bug_review_passes(repo, ref):
    """O caçador de bugs aprovou o commit de `ref` (a ponta da branch de um implementador, ou o HEAD)."""
    sha = git(repo, "rev-parse", ref)
    return run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": "harness:revisor-bugs",
                                      "cwd": str(repo),
                                      "last_assistant_message": f"VEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: sem defeito"})
