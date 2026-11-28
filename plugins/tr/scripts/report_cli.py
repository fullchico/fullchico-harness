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
    if argv[0] == "done":
        try:
            import tasks
            tasks.close_trip(root)  # chegou: a próxima partida desta demanda é outra viagem, com outra assinatura
        except Exception:
            pass
    dismantle_later(root)
    return 0


GRACE = 180  # segundos entre o relato e a primeira tentativa de desmonte, se ninguém desmontar antes
QUIET = 60   # o terminal só é encerrado depois de ficar este tempo sem mudar nada na tela
LIMIT = 3600  # depois disso o desmonte de segurança desiste: um terminal que segue ativo é decisão de gente


def safe_to_stop(root, session, stamp, quiet=None):
    """Só se desmonta quem parou de verdade. Devolve True (pode encerrar), False (ainda trabalha: olhe de novo)
    ou None (não é mais caso deste desmonte: o terminal sumiu, ou o relato mudou porque há outra partida)."""
    import time
    import tasks
    import terminal
    if not terminal.alive(session):
        return None
    try:
        if os.path.getmtime(path(root)) != stamp:
            return None
    except OSError:
        return None  # o relato foi apagado: uma nova partida começou nesta pasta
    if tasks._raw_in_flight(root):
        return False  # há executor em voo: ele ainda coordena alguém
    try:
        before = terminal.read(session, 80)
        time.sleep(QUIET if quiet is None else quiet)
        return terminal.read(session, 80) == before  # a tela mudou: recebeu um recado e voltou a trabalhar
    except terminal.Unavailable:
        return None


def watchdog(root, session, log, stamp, grace):
    import time
    import terminal
    time.sleep(grace)
    deadline = time.time() + LIMIT
    while time.time() < deadline:
        verdict = safe_to_stop(root, session, stamp)
        if verdict is None:
            return 0
        if verdict:
            terminal.stop(session, log)
            return 0
        time.sleep(30)
    return 0


def dismantle_later(root):
    """O orquestrador é descartável: relatou, é desmontado. Quem faz isso é o maestro, ao receber o relato; mas
    se ninguém estava esperando (o maestro leu o arquivo direto, ou a sessão dele fechou), o terminal ficaria
    aberto para sempre e confundiria a próxima demanda. Aqui fica um desmonte de segurança: ele só encerra um
    terminal parado, sem executor em voo, e desiste se o orquestrador voltar a trabalhar."""
    if os.environ.get("TR_ROLE") != "orchestrator":
        return
    try:
        import orchestrate_cli
        import tasks
        session = orchestrate_cli._session(root)
        if not session:
            return
        log = tasks.coordination(root, f"terminal-{session}.log")
        subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--watchdog", root, session, log,
                          repr(os.path.getmtime(path(root))), str(GRACE)], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # o relato já foi gravado: o desmonte de segurança nunca o impede


if __name__ == "__main__":
    if sys.argv[1:2] == ["--watchdog"]:
        sys.exit(watchdog(sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5]), int(sys.argv[6])))
    sys.exit(main(sys.argv[1:]))
