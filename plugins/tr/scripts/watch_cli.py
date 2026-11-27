#!/usr/bin/env python3
"""`tr-harness watch`: o painel do dono. Num segundo terminal, mostra ao vivo o quadro da demanda e as últimas
linhas de cada terminal de peixe deste projeto (orquestrador, executores, revisores). Só lê; não interfere."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terminal  # noqa: E402


def sessions(root):
    """Terminais do tr cujo diretório está neste projeto (as vagas dos executores ficam dentro dele)."""
    run = terminal._run("list-panes", "-a", "-F", "#{session_name}\t#{pane_current_path}")
    found = []
    for line in run.stdout.splitlines() if not run.returncode else []:
        name, _, path = line.partition("\t")
        if name.split("-")[0] in ("orq", "exec", "rev") and (os.path.realpath(path) + os.sep).startswith(root + os.sep) \
                and name not in found:
            found.append(name)
    return sorted(found, key=lambda n: (("orq", "exec", "rev").index(n.split("-")[0]), n))


def frame(root, lines):
    out = [f"tr · {os.path.basename(root)} · {time.strftime('%H:%M:%S')}   (Ctrl-C sai; nada é interrompido)", ""]
    status = subprocess.run([sys.executable, "-I", os.path.join(HERE, "status.py")], cwd=root, capture_output=True, text=True)
    out += status.stdout.rstrip().splitlines()
    names = sessions(root)
    if not names:
        out += ["", "nenhum terminal aberto: o trem está parado (na estação, ou a demanda fechou)."]
    for name in names:
        try:
            screen = terminal.read(name, 200)
        except terminal.Unavailable:
            continue
        mark = "  ← ESPERA VOCÊ: tmux attach -t " + name if terminal.waiting_on_human(screen) else ""
        out += ["", f"── {name}{mark}"] + ["   " + line[:200] for line in screen.splitlines()[-lines:]]
    out += ["", "para entrar num terminal: tmux attach -t <nome>   (sair sem encerrar: Ctrl-b d)"]
    return "\n".join(out)


def main(argv):
    root = os.path.realpath(".")
    if not terminal.executable():
        print("o painel precisa do tmux", file=sys.stderr)
        return 1
    lines = int(argv[argv.index("--lines") + 1]) if "--lines" in argv and argv[-1].isdigit() else 8
    if "--once" in argv:
        print(frame(root, lines))
        return 0
    try:
        while True:
            text = frame(root, lines)
            sys.stdout.write("\033[2J\033[H" + text + "\n")
            sys.stdout.flush()
            time.sleep(2)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
