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


def make_repo(name="proj dir") -> pathlib.Path:
    repo = _tmpdir() / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
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
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr
