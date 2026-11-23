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
sys.path.insert(0, str(ROOT / "plugins/_shared"))

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
    """O estado do trilho de um repositório de teste fica em ~/.claude/trilho; apaga ao sair."""
    import ledger
    state = ledger.state_dir(str(repo))
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


def hook_verdict(r):
    """Traduz o JSON de decisão de um hook do trilho para o código de saída de antes: bloqueio vira 2, com o
    motivo em `stderr`; o aviso (`systemMessage`) fica em `stdout`. Assim os testes leem "barrou" como sempre."""
    try:
        out = json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        return r
    deny = (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"
    if r.returncode == 0 and (deny or out.get("decision") == "block"):
        reason = out.get("reason") or out["hookSpecificOutput"].get("permissionDecisionReason", "")
        return subprocess.CompletedProcess(r.args, 2, r.stdout, r.stderr + reason)
    return r
