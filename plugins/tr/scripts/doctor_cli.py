#!/usr/bin/env python3
"""`doctor`: esta máquina e este projeto têm o que o plugin precisa? Diz o que está pronto, o que falta e como
resolver. Só lê; sai com 1 quando falta algo obrigatório."""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import requirements  # noqa: E402

MACHINE = [  # (programa, obrigatório, para quê, como instalar)
    ("git", True, "o histórico é onde os certificados são assinados", "instale o Git do sistema"),
    ("claude", True, "o maestro e os peixes Claude", "https://claude.com/claude-code"),
    *[(name, True, why, how) for name, why, how in requirements.NEEDED],
    ("node", False, "o instalador e o comando `tr-l` (npm)", "instale o Node.js 20 ou mais novo"),
    ("codex", False, "só se você usa orquestrador, executor ou revisor Codex", "https://developers.openai.com/codex"),
    ("gh", False, "abrir e acompanhar PR pelo maestro", "brew install gh"),
    ("lsof", False, "`tr-harness ports` (o ambiente está no ar?)", "pacote `lsof` do sistema"),
]
PLUGINS = ("tr@fullchico", "ponytail@ponytail", "mattpocock-skills@claude-plugins-official")


def version(name):
    flag = {"tmux": "-V", "lsof": None}.get(name, "--version")
    if not flag:
        return ""
    try:
        out = subprocess.run([name, flag], capture_output=True, text=True, timeout=10)
        return (out.stdout or out.stderr).strip().splitlines()[0][:40]
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def machine():
    rows, bad = [], 0
    ok = sys.version_info >= (3, 9)
    rows.append(("✓" if ok else "✗", f"python3 {sys.version.split()[0]}" + ("" if ok else ": o plugin precisa do 3.9 ou mais novo")))
    bad += not ok
    for name, required, why, how in MACHINE:
        if shutil.which(name):
            rows.append(("✓", f"{name}  {version(name)}"))
        else:
            rows.append(("✗" if required else "·", f"{name}: falta ({why}). {how}" if required
                         else f"{name}: não instalado (opcional: {why})"))
            bad += required
    return rows, bad


def project(root):
    rows, bad = [], 0
    if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root, capture_output=True).returncode:
        return [("·", "esta pasta não é um repositório Git: rode o doctor na pasta do projeto para conferir a instalação")], 0

    def read(rel):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as stream:
                return json.load(stream)
        except (OSError, ValueError):
            return None
    settings = read(".claude/settings.json")
    if settings is None:
        return [("✗", "o plugin não está instalado neste projeto: npx @fullchico/harness install")], 1
    enabled = settings.get("enabledPlugins") or {}
    for name in PLUGINS:
        on = bool(enabled.get(name))
        rows.append(("✓" if on else "✗", f"plugin {name}" + ("" if on else ": não habilitado. Rode npx @fullchico/harness install")))
        bad += not on
    hooked = "rtk hook claude" in json.dumps(settings.get("hooks") or {})
    rows.append(("✓" if hooked else "✗", "hook do rtk no projeto" + ("" if hooked else ": falta. Rode npx @fullchico/harness install")))
    bad += not hooked
    reg = read(".claude/harness.json")
    gates = (reg or {}).get("gates") or {}
    if not gates:
        rows.append(("✗", "portões não configurados: abra o Claude no projeto e rode /tr:configure"))
        bad += 1
    else:
        rows.append(("✓", f"{len(gates)} portões registrados"))
        commands = [n for n, g in gates.items() if g.get("signs") == "command"]
        if commands:
            rows.append(("·", "para saber se os portões de comando rodam nesta máquina: tr-harness gates --check"))
        rows.append(("✓" if reg.get("prepare_seat") else "·", f"preparo da vaga: {reg['prepare_seat']}" if reg.get("prepare_seat")
                     else "preparo da vaga não registrado (os executores começam sem dependências instaladas): "
                          "tr-harness gates --prepare-seat \"<comando>\""))
    return rows, bad


def main(argv):
    root = os.path.abspath(argv[0]) if argv and not argv[0].startswith("-") else os.getcwd()
    total = 0
    for title, (rows, bad) in (("máquina", machine()), (f"projeto ({os.path.basename(root)})", project(root))):
        print(title)
        for mark, text in rows:
            print(f"  {mark} {text}")
        print()
        total += bad
    print("tudo o que é obrigatório está pronto." if not total else f"faltam {total} itens obrigatórios (✗). Os marcados com · são opcionais.")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
