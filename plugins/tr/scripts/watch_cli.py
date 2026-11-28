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


def folders(root):
    """As pastas deste repositório: a principal e os worktrees (cada demanda em paralelo viaja num worktree
    próprio, ao lado da pasta). Quem olha de uma delas enxerga os trens de todas."""
    run = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=root, capture_output=True, text=True)
    found = [os.path.realpath(line[9:]) for line in run.stdout.splitlines() if line.startswith("worktree ")]
    return found or [root]


def sessions(root):
    """Terminais do tr deste repositório: os desta pasta, os das vagas dos executores e os das outras demandas."""
    run = terminal._run("list-panes", "-a", "-F", "#{session_name}\t#{pane_current_path}")
    found, places = [], folders(root) + [root]
    for line in run.stdout.splitlines() if not run.returncode else []:
        name, _, path = line.partition("\t")
        inside = any((os.path.realpath(path) + os.sep).startswith(place + os.sep) for place in places)
        if name.split("-")[0] in ("orq", "exec", "rev") and inside and name not in found:
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
    import certs
    known = terminal.roster(root)
    here = certs.demand(root) or ""

    def demand_of(name):
        found = (known.get(name) or {}).get("demand")
        if found is not None and name in known:
            return found
        if name.startswith("orq-"):  # terminais abertos antes deste registro: o nome do orquestrador traz a demanda
            return name[4:].rsplit("-", 1)[0]
        return here

    def state_of(name):
        if name in asks:
            return f"PEDE AO ORQUESTRADOR: {asks[name]}"
        try:
            return "ESPERA VOCÊ" if terminal.waiting_on_human(terminal.read(name, 60)) else "trabalhando"
        except terminal.Unavailable:
            return "encerrado"
    out = ["topologia", "  maestro (a sua sessão do Claude)"]
    trains = []
    for name in names:
        if demand_of(name) not in trains:
            trains.append(demand_of(name))
    for train in sorted(trains, key=lambda t: t != here):
        orq = [n for n in names if n.startswith("orq-") and demand_of(n) == train]
        mark = "  (a demanda desta pasta)" if train == here and len(trains) > 1 else ""
        out += [f"  └─ {n}{mark}" for n in orq] or [f"  └─ (sem orquestrador aberto) demanda `{train}`{mark}"]
        for name in [n for n in names if not n.startswith("orq-") and demand_of(n) == train]:
            kind = {"exec": "executor", "rev": "revisor "}.get(name.split("-")[0], "")
            out.append(f"     └─ {kind} {name}   {state_of(name)}")
    if not names:
        out.append("  └─ (nenhum orquestrador aberto)")
    return out


def journey(root, names):
    """A viagem da demanda desta pasta, etapa por etapa: a partida (quem foi escolhido), o caminho (tickets e
    ajustes) e a chegada (cada portão de fim: certificado, reprovado, em revisão agora, quantas tentativas)."""
    import json
    import attempts
    import certs
    import registry
    import tasks
    demand = certs.demand(root)
    if not demand:
        return ["viagem", "  nenhuma demanda ativa nesta pasta."]
    try:
        reg = registry.load(root) or {"gates": {}}
    except registry.RegistryError:
        return []

    def read(name):
        try:
            with open(tasks.coordination(root, name), encoding="utf-8") as stream:
                return json.load(stream)
        except (OSError, ValueError):
            return {}
    run, orq = read("run.json"), read("orchestrator.json")
    out = [f"viagem · demanda `{demand}`" + (f" · assinatura `{tasks.trip(root)}`" if tasks.trip(root) else "")]
    start = [f"{n} {'✓' if registry.satisfied(root, n, reg) else '…'}" for n in registry.required(root, "start", reg)]
    start.append("aceite … (ainda sem spec e tickets)" if not certs.criterion(root) else
                 f"aceite {'✓' if certs.accepted(root) else '✗ (o critério mudou ou falta aceitar)'}")
    out.append("  embarque  " + " · ".join(start))
    if orq:
        who = f"{orq.get('cli', '?')}:{orq.get('model') or '?'}"
        out.append(f"  partida   {time.strftime('%H:%M', time.localtime(orq.get('at', 0)))} · orquestrador {who} · executores "
                   f"{run.get('executors') or 'pela complexidade do ticket'} · revisores {run.get('reviewers') or 'os do registro'}")
    else:
        out.append("  partida   o trem ainda não partiu")
    tickets, adjusts = tasks.tickets(root), tasks.adjustments(root)
    done = lambda items: sum(1 for f in items.values() if f.get("status", "").lower() == "done")  # noqa: E731
    line = f"  caminho   tickets {done(tickets)}/{len(tickets)}"
    if adjusts:
        still = [os.path.basename(p)[:-3] for p, f in adjusts.items() if f.get("status", "").lower() != "done"]
        line += f" · trens de ajuste {done(adjusts)}/{len(adjusts)}" + (f" (em aberto: {', '.join(still)})" if still else "")
    out.append(line)
    arrived = not tasks.open_work(root) and bool(tickets)
    out.append("  chegada   " + ("auditoria dos portões de fim:" if arrived else "ainda não: os portões de fim rodam quando o caminho fechar"))
    doc = certs.document(root)
    for name in registry.required(root, "end", reg):
        gate = reg["gates"][name]
        found = [e for e in certs.entries(root, doc) if e["name"] == name]
        tries, limit = attempts.status(root, name, gate), gate.get("attempts", 3)
        live = [n for n in names if n.startswith(f"rev-{name}-")]
        if registry.satisfied(root, name, reg):
            state = "✓ certificado"
        elif tries.get("intervention"):
            state = "⛔ passou do limite: a decisão é sua"
        elif live:
            state = f"… em revisão agora ({', '.join(live)})"
        elif found and found[-1]["verdict"] == "REJECTED" and found[-1]["key"] == registry.stamp_key(root, gate):
            state = "✗ reprovado neste estado: " + found[-1]["summary"][:70]
        else:
            state = "… pendente" + (" (o código mudou depois da última reprovação)" if tries["rejections"] else "")
        by = gate.get("agent") or gate["signs"]
        again = f" · reprovações {tries['rejections']}/{limit}" if tries["rejections"] else ""
        turn = " · exclusivo" if gate.get("exclusive") else ""
        out.append(f"    {name:<11}{state}{again}{turn}   [{by}]")
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
    import certs
    seats = os.sep + os.path.join(".claude", "worktrees") + os.sep
    trains = [root] + [place for place in folders(root)
                       if place != root and seats not in place + os.sep and certs.demand(place)]
    for place in trains:  # a viagem desta pasta e a de cada demanda em paralelo (um worktree por demanda)
        try:
            lines_ = journey(place, names)
            if place != root and lines_:
                lines_[0] += f"   (em {os.path.relpath(place, os.path.dirname(root))}; para ver de lá: cd e ./tr l)"
            out += [""] + lines_
        except Exception as error:  # o painel nunca cai por um registro que não conseguiu ler
            out += ["", f"viagem: não consegui ler ({type(error).__name__})"]
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


def pick(names, wanted):
    """O agente pedido: nome exato, começo do nome ou trecho dele. Devolve (nome, None) ou (None, candidatos)."""
    if not wanted:
        return (names[0], None) if len(names) == 1 else (None, names)
    for test in (lambda n: n == wanted, lambda n: n.startswith(wanted), lambda n: wanted in n):
        found = [n for n in names if test(n)]
        if len(found) == 1:
            return found[0], None
        if found:
            return None, found
    return None, []


def attach(root, wanted):
    """`./tr a [nome]`: o dono entra no terminal de um agente deste projeto. Sem nome, escolhe numa lista."""
    names = sessions(root)
    if not names:
        print("nenhum agente aberto neste projeto agora.")
        return 1
    name, options = pick(names, wanted)
    if not name and not options:
        print(f"nenhum agente com `{wanted}` no nome. Abertos: " + ", ".join(names))
        return 1
    if not name:
        for number, option in enumerate(options, 1):
            print(f"  {number}. {option}")
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("diga qual: ./tr a <começo do nome>")
            return 1
        answer = input("qual? (número) ").strip()
        if not answer.isdigit() or not 1 <= int(answer) <= len(options):
            return 1
        name = options[int(answer) - 1]
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(f"para entrar: tmux attach -t {name}   (precisa de um terminal de verdade)")
        return 1
    print(f"entrando em {name}. Para sair sem encerrar o agente: Ctrl-b e depois d.")
    time.sleep(1)
    verb = "switch-client" if os.environ.get("TMUX") else "attach"  # dentro do tmux, troca em vez de aninhar
    os.execvp("tmux", ["tmux", verb, "-t", name])


def mirror(name, look=None):
    """Um painel da visão: repete a tela de um agente, com as cores, até ele encerrar. A tecla `q` fecha a visão
    inteira (só a visão: os agentes seguem trabalhando)."""
    import select
    import shutil
    import termios
    import tty
    keys = sys.stdin.fileno() if sys.stdin.isatty() else None
    saved = termios.tcgetattr(keys) if keys is not None else None

    def pressed_q(wait):
        if keys is None:
            time.sleep(wait)
            return False
        ready, _, _ = select.select([keys], [], [], wait)
        return bool(ready) and os.read(keys, 32).lower().startswith(b"q")
    try:
        if keys is not None:
            tty.setcbreak(keys)
        ended = False
        while True:
            if not ended and terminal.alive(name):
                run = terminal._run("capture-pane", "-p", "-e", "-t", name)
                rows = run.stdout.rstrip().splitlines() if not run.returncode else []
                height = max(shutil.get_terminal_size((80, 24)).lines - 1, 1)
                sys.stdout.write("\033[H\033[2J" + "\n".join(rows[-height:]))
                sys.stdout.flush()
            elif not ended:
                ended = True
                print(f"\n\n{name}: encerrado")
            if pressed_q(1):
                if look:
                    terminal._run("kill-session", "-t", look)
                return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if saved is not None:
            termios.tcsetattr(keys, termios.TCSADRAIN, saved)


def view(root, open_it=True):
    """`./tr v`: uma janela do tmux com um painel por agente deste projeto, todos ao vivo, só para olhar.
    Cada painel mostra a tela do agente sem entrar no terminal dele: não dá para digitar ali, e o agente não
    percebe que há alguém olhando. Devolve o nome da sessão de visão, ou None."""
    names = sessions(root)
    if not names:
        print("nenhum agente aberto neste projeto agora.")
        return None
    look = "tr-ver-" + "".join(c if c.isalnum() else "-" for c in os.path.basename(root))[:30]
    terminal._run("kill-session", "-t", look)  # a visão é montada de novo a cada vez, com quem está aberto agora

    def pane(name):
        # Cada painel copia a tela do agente uma vez por segundo, em vez de entrar no terminal dele: um cliente
        # a mais mudaria o tamanho do terminal do agente (medido: 150x40 virou 110x27) e bagunçaria a tela dele.
        import shlex
        return f"{shlex.quote(sys.executable)} -I {shlex.quote(os.path.abspath(__file__))} --mirror {shlex.quote(name)} {shlex.quote(look)}"
    made = terminal._run("new-session", "-d", "-s", look, "-x", "220", "-y", "60", "-c", root, pane(names[0]))
    if made.returncode:
        print("não consegui montar a visão: " + (made.stderr or "").strip()[:200], file=sys.stderr)
        return None
    for name in names[1:]:
        terminal._run("split-window", "-t", look, "-c", root, pane(name))
        terminal._run("select-layout", "-t", look, "tiled")
    terminal._run("set-option", "-t", look, "pane-border-status", "top")
    for index, name in enumerate(names):
        terminal._run("select-pane", "-t", f"{look}.{index}", "-T", f"{name} · q fecha a visão")
    if not open_it or not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(f"visão montada com {len(names)} agentes. Para abrir: tmux attach -t {look}")
        return look
    print(f"abrindo a visão com {len(names)} agentes (só leitura). Para fechar: tecla q (os agentes continuam).")
    time.sleep(1)
    os.execvp("tmux", ["tmux", "switch-client" if os.environ.get("TMUX") else "attach", "-t", look])


def main(argv):
    root = os.path.realpath(".")
    if not terminal.executable():
        print("o painel precisa do tmux", file=sys.stderr)
        return 1
    if len(argv) in (2, 3) and argv[0] == "--mirror":
        return mirror(argv[1], argv[2] if len(argv) == 3 else None)
    if argv and argv[0] == "--view":
        return 0 if view(root) else 1
    if argv and argv[0] == "--attach":
        return attach(root, argv[1] if len(argv) > 1 else "")
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
