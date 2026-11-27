#!/usr/bin/env python3
"""`tr-harness orchestrate [--agent <cli>] [--model <id>] [--executors <cli:modelo>] [--reviewers <cli:modelo>]
[--terminals] [--print | --wait | --status | --read | --stop]`: o maestro entrega a demanda aceita ao orquestrador.

O maestro é a sessão com quem o dono conversa: fecha a definição, recebe o que foi entregue e fica livre. O
orquestrador é descartável: uma sessão inteira aberta num terminal próprio (tmux), na pasta da demanda, sob os
mesmos trilhos (o harness do projeto), montada com os modelos escolhidos para esta demanda e desmontada ao fim.
Ele avisa o maestro gravando o relato (`tr-harness report`); `--wait` é a espera do maestro por esse relato.
A prova continua nos certificados e no Git, nunca só no relato.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import certs  # noqa: E402
import registry  # noqa: E402
import report_cli  # noqa: E402
import tasks  # noqa: E402
import terminal  # noqa: E402

STALE = 600  # tela do orquestrador sem mudar por tanto tempo: provavelmente travou


def _flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def preflight(root, reg, every=False):
    """Embarque: roda uma vez cada verificador de comando dos portões de fim, para saber antes de partir se ele
    funciona. `não roda` (comando ou script inexistente) é diferente de `reprova` (o trabalho ainda não existe)."""
    lines = []
    for gate, spec in sorted((reg.get("gates") or {}).items()):
        if spec.get("signs") != "command" or not spec.get("command") or (spec.get("stage") != "end" and not every):
            continue
        try:
            run = subprocess.run(spec["command"], shell=True, cwd=root, capture_output=True, text=True, timeout=300)
            text, code = (run.stdout + run.stderr), run.returncode
        except subprocess.TimeoutExpired:
            text, code = "timeout", 124
        missing = code in (126, 127) or any(mark in text for mark in (
            "command not found", "Missing script", "No such file or directory", "ENOENT", "not recognized", ": not found"))
        state = "passes" if code == 0 else ("DOES NOT RUN" if missing else "runs and fails")
        rows = [r.strip() for r in text.strip().splitlines() if r.strip()]
        # a linha que explica: a primeira que fala de erro, não o rodapé do gerenciador de pacotes
        last = next((r for r in rows if any(m in r for m in ("Missing script", "not found", "ENOENT", "No such file",
                                                              "Error", "error")) and "complete log" not in r),
                    rows[-1] if rows else "")[:140]
        lines.append(f"- `{gate}` (`{spec['command']}`): {state}" + (f": {last}" if code else ""))
    return lines


def shared_files(root):
    """Tickets que podem rodar na mesma onda (nenhum bloqueia o outro) e declaram o mesmo arquivo em `Files:`:
    integrados em paralelo, dão conflito de merge certo. Devolve as linhas de aviso."""
    import re
    info = {}
    for path in sorted(tasks.open_tickets(root) if hasattr(tasks, "open_tickets") else tasks.tickets(root)):
        try:
            with open(os.path.join(root, path), encoding="utf-8") as stream:
                text = stream.read()
        except OSError:
            continue
        files = re.search(r"(?mi)^\s*files:\s*(.+)$", text)
        blocked = re.search(r"(?mi)^\s*blocked by:\s*(.+)$", text)
        info[path] = ({f.strip() for f in (files.group(1) if files else "").split(",") if f.strip() and "*" not in f},
                      (blocked.group(1) if blocked else "").lower())
    def blocks(a, b):  # `a` espera por `b`?
        stem = os.path.basename(b)[:-3].lower()
        number = stem.split("-")[0]
        return stem in info[a][1] or re.search(rf"(?<![\w]){re.escape(number)}(?![\w])", info[a][1]) is not None
    lines, paths = [], list(info)
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            common = sorted(info[a][0] & info[b][0])
            if common and not blocks(a, b) and not blocks(b, a):
                lines.append(f"- `{os.path.basename(a)}` and `{os.path.basename(b)}` can run together and both declare "
                             f"`{', '.join(common)}`")
    return lines


def running_executors(root):
    """Executores em terminal que seguem vivos de uma partida anterior (o orquestrador deles relatou um bloqueio
    e foi desmontado; o dono destravou depois). O próximo orquestrador os adota em vez de despachar de novo."""
    import glob
    lines = []
    runs = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root,
                          capture_output=True, text=True).stdout.strip()
    for path in sorted(glob.glob(os.path.join(runs, "harness-runs", "*", "dispatch.json"))):
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            continue
        report = data.get("report") or ""
        report = report if os.path.isabs(report) else os.path.join(root, report)
        if data.get("session") and (terminal.alive(data["session"]) or os.path.isfile(report)) and data.get("worktree") \
                and os.path.isdir(data["worktree"]):
            run_id = os.path.basename(os.path.dirname(path))
            lines.append(f"- `{data.get('ticket') or run_id}`: terminal `{data['session']}`, run `{run_id}`")
    return lines


def unwritable_for_codex(root, executors):
    """Um executor Codex roda num sandbox que não grava em `.git`, `.codex` nem `.agents`: ticket que declara
    arquivo ali não fecha com ele. Devolve as linhas de aviso (vazio se nenhum executor é Codex)."""
    import re
    if "codex:" not in (executors or ""):
        return []
    lines = []
    for path in sorted(tasks.open_tickets(root)):
        try:
            with open(os.path.join(root, path), encoding="utf-8") as stream:
                files = re.search(r"(?mi)^\s*files:\s*(.+)$", stream.read())
        except OSError:
            continue
        hit = sorted({f.strip() for f in (files.group(1) if files else "").split(",")
                      if re.match(r"\.?/?(\.git|\.codex|\.agents)(/|$)", f.strip())})
        if hit:
            lines.append(f"- `{os.path.basename(path)}` declares `{', '.join(hit)}`")
    return lines


def brief(root, cli="claude", executors=None, reviewers=None, checks=(), overlaps=(), terminals=False,
          adopted=(), unwritable=()):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instructions = (os.path.join(here, "agents", "orchestrator.md") if cli == "claude"
                    else "the `tr-orchestrator` agent in `.codex/agents/` and the `tr-process-plan` skill, section 5")
    cli_path = "tr-harness" if cli == "claude" else ".codex/harness/tr/bin/tr-harness"
    gate_path = "gate" if cli == "claude" else ".codex/harness/tr/bin/gate"
    slug = certs.demand(root)
    spec = certs.document(root)
    tickets = sorted(tasks.tickets(root))
    return "\n".join([
        f"You are the tr orchestrator of the demand `{slug}` in this project. The maestro already closed the "
        "definition with the owner; the owner accepted the criterion and the start gates are certified. You are "
        "disposable: you exist for this demand and are dismantled when it closes.",
        "",
        f"- Spec: {spec}",
        *[f"- Ticket: {t}" for t in tickets],
        f"- Demand branch: {registry.branch(root)}",
        f"- Accepted criterion: {certs.criterion(root)[:10]}",
        (f"- Executors: `{executors}`, each one in its OWN TERMINAL and its own worktree. For every ticket of a "
         f"wave run `{cli_path} models run execution --ticket <path> --prompt \"<handoff>\" --detach` (one call per "
         f"ticket, all in the same message), then ONE `{cli_path} models wait <id> <id> ... --timeout 540` for the "
         "whole wave: it returns when all of them reported, with each report and the branch to merge. Merge each "
         "branch into the demand branch, then `git worktree remove --force` and delete the branch. An executor on "
         "Codex cannot write to `.git` nor listen on a port inside its sandbox: when its report says so, run its "
         "checks yourself in its worktree and commit its worktree for it before merging. Each report comes with the "
         "paths of a log of that terminal and of the agent's own transcript. Open them only by the criteria in your "
         "instructions (a report that is BLOCKED or contradicted by a check, a terminal that ended without a "
         "report, a rejection you cannot explain), and never whole: `grep` for what you look for or `tail` the "
         "last lines. A DONE report whose merge and verifier pass needs no log. Do not "
         "dispatch executor subagents in this demand.") if executors and terminals else
        f"- Executors: `{executors}`, chosen for this demand." if executors else
        "- Executors: the model comes from each ticket's `Complexity:` (the hook applies it).",
        (f"- Reviewers: `{reviewers or 'the review role'}`, each one in its OWN TERMINAL. At the arrival, for every end "
         f"gate signed by an agent run `{cli_path} models validate-gate <gate> --detach` (one call per gate, all in "
         f"the same message), then ONE `{cli_path} models wait <id> <id> ... --timeout 540`: it returns each verdict; "
         "the certificate is written by the command. Command and artifact gates keep going through the checker. Do "
         "not dispatch reviewer subagents for agent gates in this demand.") if terminals else
        f"- Reviewers: `{reviewers}`, chosen for this demand." if reviewers else
        "- Reviewers: the model of each gate is in `tr-harness models show`.",
        *(["", "Verifiers checked at boarding (each end command gate was run once, before any work):", *checks,
           "A verifier marked DOES NOT RUN must be made to run as soon as the ticket that creates it is integrated: "
           "run it then, do not discover it at the arrival."] if checks else []),
        *(["", "Tickets of the same wave that declare the same file (a parallel merge will conflict there):", *overlaps,
           "Sequence them yourself: dispatch one, integrate it, then dispatch the next from the updated branch. Do "
           "NOT edit the tickets to do it (a changed `Blocked by` changes the criterion the owner accepted)."]
          if overlaps else []),
        *(["", "Executors still running from a previous departure (do NOT dispatch these tickets again: wait for "
           f"them with `{cli_path} models wait <run> ... --timeout 540` and integrate what they report):", *adopted]
          if adopted else []),
        *(["", "Tickets a Codex executor cannot finish (its sandbox does not write to `.git`, `.codex` or `.agents`); "
           "give these to a Claude executor, or report the block to the maestro before dispatching:", *unwritable]
          if unwritable else []),
        "",
        f"An executor that cannot run a command where it is (no network, a folder it cannot write) asks you instead "
        f"of giving up: `{cli_path} models wait` returns with `pede um comando` and exit 6. You decide, without "
        "asking the owner: grant what its ticket needs and stays inside the project (install a dependency the "
        "ticket adds, run a test that needs the database), with the command it asked or a better one; refuse what "
        "does not belong to its ticket. Then wait again. Report BLOCKED only when the work needs something beyond "
        "your own limits.",
        "",
        "What you commit is public to whoever reads the repository: in tickets, adjustments, the balance and commit "
        "messages, write paths relative to the project and never a path of this machine (home folder, temp folder), "
        "a user name, a token or the content of an env file.",
        "",
        "A command gate that fails keeps its whole output in `.harness-run/evidence/<state>/gate-<name>.log` "
        f"(`{cli_path} evidence` lists it). Read it before opening an adjustment or reporting: say which test or "
        "step failed, not only that the gate failed.",
        "",
        f"Integrate an executor that ran in a terminal ONLY with `{cli_path} models integrate <run> [<run>...]`: it "
        "commits what a Codex executor left, merges into the demand branch and dismantles the seat only after "
        "checking the work is in. Never remove a seat or delete an executor branch by hand, and never mark a "
        "ticket done before its integrate printed `integrado`.",
        "",
        f"Read and follow the orchestrator instructions of the tr harness: {instructions}. They describe the trip, "
        "the arrival audit and the adjustment trains, until `tr-harness deliver` passes. The same rails apply to "
        "you: the project hooks, the gates and the certificates. Do not change the spec or the tickets' criterion; "
        "if it must change, stop and report.",
        "",
        f"The harness CLI here is `{cli_path}` (and `{gate_path}` for the gates).",
        "",
        "Executors and reviewers report to you; you report to the maestro. When the delivery passes, or when you "
        f"cannot continue, run `{cli_path} balance --write`, commit it, and then, as the LAST thing you do, run "
        f"`{cli_path} report done \"<what was delivered>\"` or `{cli_path} report blocked \"<the exact block and "
        "error>\"`, alone in the call. That report is how the maestro is woken; without it nobody knows you "
        "stopped. Do not ask questions in this terminal: nobody answers them here. A decision only the owner can "
        "take is a `report blocked`.",
    ])


def _state(root):
    return tasks.coordination(root, "orchestrator.json")


def _session(root):
    try:
        with open(_state(root), encoding="utf-8") as stream:
            return json.load(stream)["session"]
    except (OSError, ValueError, KeyError):
        return None


def wait(root, seconds):
    """A espera do maestro: 0 com o relato; 1 se o terminal fechou sem relato; 5 se a tela espera uma pessoa;
    4 se a tela não muda há `STALE` s; 3 no fim do prazo (chame de novo)."""
    session, deadline = _session(root), time.time() + seconds
    last, since = None, time.time()
    while True:
        if os.path.isfile(report_cli.path(root)):
            with open(report_cli.path(root), encoding="utf-8") as stream:
                print(stream.read())
            if session and terminal.alive(session):
                log = tasks.coordination(root, f"terminal-{session}.log")
                terminal.stop(session, log)  # o orquestrador é descartável: relatou, é desmontado
                print(f"(orquestrador desmontado: terminal `{session}` encerrado; o que passou pela tela dele: {log})")
            return 0
        if not session or not terminal.alive(session):
            print("o orquestrador encerrou sem gravar o relato: confira `tr-harness status` e abra outro a partir dos "
                  "handoffs", file=sys.stderr)
            return 1
        try:
            screen = terminal.read(session)
        except terminal.Unavailable:
            continue
        if terminal.settle(session, screen):
            time.sleep(2)
            continue
        human = terminal.waiting_on_human(screen)
        if human:
            print("o terminal do orquestrador mostra uma tela que só o dono responde; mostre-a ao dono "
                  f"(`tmux attach -t {session}`):\n{human}", file=sys.stderr)
            return 5
        if screen != last:
            last, since = screen, time.time()
        elif time.time() - since > STALE:
            print(f"a tela do orquestrador não muda há {STALE} s (provavelmente travou):\n" +
                  "\n".join(screen.splitlines()[-15:]), file=sys.stderr)
            return 4
        if time.time() >= deadline:
            print(f"o orquestrador segue trabalhando (terminal `{session}`); chame `tr-harness orchestrate --wait` de novo")
            return 3
        time.sleep(4)


def supervise(root, action, argv):
    session = _session(root)
    if not session:
        print("nenhum orquestrador aberto por `tr-harness orchestrate` para a demanda desta pasta", file=sys.stderr)
        return 1
    if action == "--wait":
        return wait(root, int(_flag(argv, "--seconds") or 540))
    alive = terminal.alive(session)
    if action == "--status":
        print(f"terminal `{session}`: {'vivo' if alive else 'encerrado'}; relato: "
              f"{'gravado' if os.path.isfile(report_cli.path(root)) else 'ainda não'} (`tmux attach -t {session}` para ver)")
        return 0
    if action == "--read":
        try:
            print(terminal.read(session, 80))
        except terminal.Unavailable as error:
            print(error, file=sys.stderr)
            return 1
        return 0
    terminal.stop(session)  # --stop: o socorro; o trabalho commitado fica, e o próximo parte dos handoffs
    print(f"terminal `{session}` encerrado")
    return 0


def main(argv):
    root = registry.toplevel(os.getcwd())
    action = next((a for a in argv if a in ("--wait", "--status", "--read", "--stop")), None)
    if action:
        return supervise(root, action, argv)
    reg = registry.load(root) or {}
    choice = dict((reg.get("models") or {}).get("orchestration") or {"cli": "claude"})
    # os modelos são escolhidos por demanda, na partida: valem para este trem e não mudam o registro do projeto
    if _flag(argv, "--agent"):
        choice = {"cli": _flag(argv, "--agent")}
    if _flag(argv, "--model"):
        choice["model"] = _flag(argv, "--model")
    if choice["cli"] not in ("claude", "codex"):
        print("--agent deve ser claude ou codex", file=sys.stderr)
        return 2
    if choice["cli"] == "claude" and not choice.get("model"):
        choice["model"] = "sonnet"
    executors, reviewers = _flag(argv, "--executors"), _flag(argv, "--reviewers")
    if "--print" not in argv and not (_flag(argv, "--model") and executors and reviewers):
        # Os três modelos são decisão do dono a cada partida (o maestro é sempre o mesmo; o resto é montado por
        # onda). Sem os três no comando, o trem não sai: é o que obriga a pergunta a ser feita.
        print("a partida precisa dos três modelos desta onda, escolhidos pelo dono: `--model <orquestrador>`, "
              "`--executors <cli:modelo[,cli:modelo]>` e `--reviewers <cli:modelo>`.\n"
              "Pergunte ao dono com AskUserQuestion, numa mensagem só, três perguntas (a sua recomendação primeiro em "
              "cada uma): quem orquestra, quem executa e quem valida. \"Siga o recomendado\" na entrevista não responde "
              "isto; só vale pular a pergunta se o dono já disse os três modelos para esta partida.", file=sys.stderr)
        return 2
    if executors == "auto":
        executors = None  # pela complexidade de cada ticket
    if not certs.demand(root) or not tasks.tickets(root):
        print("sem demanda ativa com tickets (.claude/current-demand)", file=sys.stderr)
        return 2
    if not certs.accepted(root):
        print("o dono ainda não aceitou o critério atual: `tr-harness gates --accept`", file=sys.stderr)
        return 1
    pointer = subprocess.run(["git", "status", "--porcelain", "--", ".claude/current-demand"], cwd=root,
                             capture_output=True, text=True).stdout.strip()
    if pointer:
        # os worktrees dos executores nascem do commit: sem isto eles leriam outra demanda e outro quadro
        print("`.claude/current-demand` não está commitado: commite antes de partir.", file=sys.stderr)
        return 1
    import models_cli
    pending = models_cli.unfinished_operation(root)
    if pending and "--print" not in argv:
        print(f"há um {pending} pela metade neste checkout (`git status` mostra): o trem não parte assim, porque o "
              "próximo commit o concluiria e traria trabalho que ninguém pediu. Mostre ao dono o que ficou e "
              f"conclua ou aborte (`git {pending} --abort`) com a decisão dele.", file=sys.stderr)
        return 1
    checks = [] if "--print" in argv or "--no-preflight" in argv else preflight(root, reg)
    overlaps = shared_files(root)
    terminals = "--terminals" in argv
    if terminals and not executors:
        executors = "claude:sonnet"
    adopted = running_executors(root)
    unwritable = unwritable_for_codex(root, executors)
    text = brief(root, choice["cli"], executors, reviewers, checks, overlaps, terminals, adopted, unwritable)
    session = terminal.name("orq", certs.demand(root), choice.get("model") or choice["cli"])
    if "--print" in argv:
        print(text + "\n\n$ tmux new-session -d -s " + session + " ...")
        return 0
    if not terminal.executable():
        print("o orquestrador abre num terminal do tmux, e o `tmux` não está no PATH. Instale (`brew install tmux`) e "
              "rode de novo.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(_state(root)), exist_ok=True)
    path = tasks.coordination(root, "orchestrator-brief.md")  # fora do repositório: não suja a árvore
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text + "\n")
    tasks.run_choice(root, {"executors": executors, "reviewers": reviewers, "terminals": "yes" if terminals else None})
    if os.path.isfile(report_cli.path(root)):
        os.remove(report_cli.path(root))  # o relato é desta partida
    try:
        terminal.open_agent(root, session, choice["cli"], choice.get("model"), path,
                            {"TR_ROLE": "orchestrator", "TR_DEMAND": certs.demand(root)},
                            record=tasks.coordination(root, f"terminal-{session}.raw.log"))
    except terminal.Unavailable as error:
        print(f"o orquestrador não abriu: {error}", file=sys.stderr)
        return 1
    with open(_state(root), "w", encoding="utf-8") as stream:
        json.dump({"session": session, "cli": choice["cli"], "model": choice.get("model"), "at": time.time()}, stream)
    for line in checks:
        print("embarque " + line)
    for line in overlaps:
        print("embarque: mesma onda, mesmo arquivo " + line)
    for line in unwritable:
        print("embarque: um executor Codex não grava ali " + line)
    for line in adopted:
        print("embarque: executor já rodando, será adotado " + line)
    print(f"orquestrador {choice['cli']}{':' + choice['model'] if choice.get('model') else ''} aberto no terminal "
          f"`{session}` (para ver: `tmux attach -t {session}`).\nAgora rode `tr-harness orchestrate --wait` em segundo "
          "plano: ele volta quando o orquestrador gravar o relato, ou se ele parar numa tela que só o dono responde.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
