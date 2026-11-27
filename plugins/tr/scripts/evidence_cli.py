#!/usr/bin/env python3
"""A prova do estado entregue e o ambiente no ar.

- `tr-harness evidence`: a pasta de prova do estado atual (`.harness-run/evidence/<estado>/`) e o que há nela. A
  pasta leva o hash do conteúdo: prova de outro estado fica em outra pasta, então não se confunde com a deste.
  Quem produz a prova (saída de comando, captura de tela pela skill que o projeto usar) grava nela.
- `tr-harness ports`: as portas que processos deste checkout estão escutando (o ambiente está no ar?).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402


def folder(root):
    """`.harness-run/evidence/<hash do conteúdo>`: fora do Git e fora do hash."""
    base = os.path.join(root, ".harness-run")
    os.makedirs(base, exist_ok=True)
    ignore = os.path.join(base, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as stream:
            stream.write("*\n")
    return os.path.join(base, "evidence", (ledger.head(root) or "sem-estado")[:12])


def listening(root):
    """[(porta, comando)] dos processos que escutam TCP e têm a pasta de trabalho dentro deste checkout."""
    try:
        out = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpcn"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found, pid, name = [], None, ""
    real = os.path.realpath(root)
    for line in out.splitlines():
        if line.startswith("p"):
            pid, name = line[1:], ""
        elif line.startswith("c"):
            name = line[1:]
        elif line.startswith("n") and pid:
            cwd = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
            where = next((l[1:] for l in cwd.splitlines() if l.startswith("n")), "")
            if os.path.realpath(where).startswith(real):
                found.append((line.rsplit(":", 1)[-1], name))
    return sorted(set(found))


def main(argv):
    root = registry.toplevel(os.getcwd())
    command = argv[0] if argv else ""
    if command == "evidence":
        path = folder(root)
        os.makedirs(path, exist_ok=True)  # quem revisa em modo só leitura precisa encontrar a pasta pronta
        print(os.path.relpath(path, root))
        for name in sorted(os.listdir(path)):
            print("  " + name)
        return 0
    if command == "ports":
        ports = listening(root)
        if ports is None:
            print("tr-harness ports: não consegui listar as portas (`lsof` indisponível)", file=sys.stderr)
            return 1
        if not ports:
            print("nenhuma porta escutando neste checkout: o ambiente não está no ar")
            return 1
        for port, name in ports:
            print(f"{port} {name}")
        return 0
    print("uso: tr-harness evidence | ports", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
