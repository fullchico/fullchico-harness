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


RAILS = [("maestro", "livre: é a sua sessão; delega o código e pede a sua aprovação nas decisões de dono"),
         ("orquestrador", "dentro do projeto: coordena, concede pedidos, integra e valida; não empurra nem publica"),
         ("executor", "dentro da demanda: o ticket, a branch e a vaga dele; o que a caixa nega, pede ao orquestrador"),
         ("revisor", "só lê e julga o estado entregue; o carimbo sai do comando, não dele")]


def topology(root, names):
    """Quem está de pé e a quem responde, com o que cada executor faz agora (trabalha, pede, espera o dono)."""
    import glob
    import json
    import models_cli
    asks = {}
    for path in glob.glob(os.path.join(models_cli._state_dir(root), "*", "dispatch.json")):
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            continue
        if data.get("request") and os.path.isfile(data["request"]):
            with open(data["request"], encoding="utf-8") as stream:
                asks[data.get("session")] = stream.readline().strip()[:90]
    out = ["topologia", "  maestro (a sua sessão do Claude)"]
    orq = [n for n in names if n.startswith("orq-")]
    out += [f"  └─ {n}" for n in orq] or ["  └─ (nenhum orquestrador aberto)"]
    for name in [n for n in names if not n.startswith("orq-")]:
        state = f"PEDE AO ORQUESTRADOR: {asks[name]}" if name in asks else ""
        if not state:
            try:
                state = "ESPERA VOCÊ" if terminal.waiting_on_human(terminal.read(name, 60)) else "trabalhando"
            except terminal.Unavailable:
                state = "encerrado"
        out.append(f"     └─ {name}   {state}")
    return out


def fired(root, limit=5):
    """Os últimos trilhos que barraram alguma coisa neste projeto (o registro do próprio plugin)."""
    import json
    import ledger
    folder = ledger.state_dir(root)
    try:
        with open(os.path.join(folder or "", "log.jsonl"), encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream.readlines()[-400:] if line.strip()]
    except (OSError, ValueError):
        return []
    hits = [r for r in rows if r.get("what") == "blocked"][-limit:]
    def clock(at):
        from datetime import datetime
        try:
            return datetime.fromisoformat(at).astimezone().strftime("%H:%M:%S")
        except (TypeError, ValueError):
            return "--:--:--"
    return [f"  {clock(r.get('at'))}  {str(r.get('detail', ''))[:110]}" for r in hits]


def frame(root, lines):
    out = [f"tr · {os.path.basename(root)} · {time.strftime('%H:%M:%S')}   (Ctrl-C sai; nada é interrompido)", ""]
    status = subprocess.run([sys.executable, "-I", os.path.join(HERE, "status.py")], cwd=root, capture_output=True, text=True)
    out += status.stdout.rstrip().splitlines()
    names = sessions(root)
    out += [""] + topology(root, names)
    out += ["", "trilhos de cada papel"] + [f"  {who:<13}{what}" for who, what in RAILS]
    hits = fired(root)
    if hits:
        out += ["", "trilhos que barraram algo (últimos)"] + hits
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
