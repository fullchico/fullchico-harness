#!/usr/bin/env python3
"""Leva o plugin desta pasta para um projeto de teste, sem publicar: `tools/dev-sync <projeto>`.

O Claude Code carrega cada plugin da pasta de cache da versão instalada naquele projeto
(`installed_plugins.json`); o dev-sync copia o `tr` e o `memory` daqui para essa pasta. No Codex, o harness
mora dentro do projeto (`.codex/harness`) e é recopiado pelo `install_codex` sem baixar skills. Um marcador
`.dev-sync.json` diz qual commit daqui o projeto está rodando. Vale na próxima sessão aberta no projeto.
"""
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys

SOURCE = pathlib.Path(__file__).resolve().parent.parent
PLUGINS = ("tr", "memory")


def installed(project, home):
    """{plugin: pasta de cache} que este projeto carrega."""
    try:
        data = json.loads((home / ".claude/plugins/installed_plugins.json").read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for name in PLUGINS:
        for entry in data.get("plugins", {}).get(f"{name}@fullchico", []):
            if os.path.realpath(entry.get("projectPath", "")) == os.path.realpath(project) and entry.get("installPath"):
                out[name] = pathlib.Path(entry["installPath"])
    return out


def main(argv):
    if len(argv) != 1:
        print("uso: tools/dev-sync <pasta do projeto>", file=sys.stderr)
        return 2
    project = pathlib.Path(argv[0]).resolve()
    home = pathlib.Path(os.path.expanduser("~"))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=SOURCE, capture_output=True,
                            text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=SOURCE, capture_output=True,
                                text=True).stdout.strip())
    marker = {"source": str(SOURCE), "commit": commit + ("+dirty" if dirty else ""),
              "at": datetime.datetime.now().isoformat(timespec="seconds")}
    targets = installed(project, home)
    if not targets:
        print(f"dev-sync: {project} não tem tr/memory instalados no Claude; rode o install uma vez antes.",
              file=sys.stderr)
    for name, path in targets.items():
        shutil.rmtree(path, ignore_errors=True)
        shutil.copytree(SOURCE / "plugins" / name, path, ignore=shutil.ignore_patterns("__pycache__"))
        (path / ".dev-sync.json").write_text(json.dumps(marker))
        print(f"claude: {name} → {path}")
    if (project / ".codex/harness").is_dir():
        run = subprocess.run([sys.executable, "-I", str(SOURCE / "tools/install_codex.py"), str(project)],
                             env=dict(os.environ, FULLCHICO_SKIP_SKILLS="1"), capture_output=True, text=True)
        if run.returncode:
            print(run.stdout + run.stderr, file=sys.stderr)
            return run.returncode
        print("codex: .codex/harness recopiado")
    print(f"dev-sync: {project} roda {marker['commit']}; abra uma sessão nova lá.")
    return 0 if targets or (project / ".codex/harness").is_dir() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
