"""Base dos hooks do harness: leitura de entrada, estado dos portões e configuração."""
import json
import os
import re
import subprocess
import sys

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
