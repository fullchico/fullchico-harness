#!/usr/bin/env python3
"""`tr-harness report <done|blocked> [texto | --file <arquivo>]`: o relato de quem conduz a demanda.

É assim que o orquestrador avisa o nível de cima: grava `.harness-run/report.md` (fora do Git), e quem espera
(`tr-harness orchestrate --wait`) volta na hora. O relato não é a palavra de quem conduz: este comando acrescenta
o resultado do `gate delivery` e o balanço, calculados agora, para o maestro ler sem precisar executar nada."""
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def path(root):
    return os.path.join(root, ".harness-run", "report.md")


def _out(root, script, *args):
    run = subprocess.run([sys.executable, "-I", os.path.join(HERE, script), *args], cwd=root, capture_output=True,
                         text=True, timeout=600)
    return (run.stdout + run.stderr).strip()


def main(argv):
    if not argv or argv[0] not in ("done", "blocked"):
        print("uso: tr-harness report <done|blocked> [texto | --file <arquivo>]", file=sys.stderr)
        return 2
    root = registry.toplevel(os.getcwd())
    if argv[1:2] == ["--file"] and len(argv) > 2:
        with open(argv[2], encoding="utf-8") as stream:
            text = stream.read().strip()
    else:
        text = " ".join(argv[1:]).strip()
    delivery = "\n".join(_out(root, "gate_cli.py", "delivery").splitlines()[-12:])
    balance = _out(root, "balance_cli.py")
    os.makedirs(os.path.dirname(path(root)), exist_ok=True)
    ignore = os.path.join(os.path.dirname(path(root)), ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as stream:
            stream.write("*\n")
    body = "\n".join([argv[0].upper(), "", f"at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}", "",
                      "## What the conductor says", text or "(no text)", "",
                      "## gate delivery (computed now)", delivery or "(no output)", "",
                      "## Balance (computed now)", balance or "(no balance)", ""])
    with open(path(root) + ".tmp", "w", encoding="utf-8") as stream:
        stream.write(body)
    os.replace(path(root) + ".tmp", path(root))  # quem espera nunca lê um relato pela metade
    print(f"relato gravado em {os.path.relpath(path(root), root)}: quem espera por ele já foi avisado.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
