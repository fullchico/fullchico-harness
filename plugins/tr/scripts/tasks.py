"""Grafo e passaportes dos tickets da demanda atual.

Tickets vivem em docs/specs/<demanda>/issues/*.md e declaram bloqueadores,
portões e estado. Este módulo só lê os carimbos do ledger.
"""
import os
import re

FIELD = re.compile(r"(?mi)^\s*(Status|Blocked by|Start|Middle|Gates|Files|Delivery):\s*(.*?)\s*$")


def tickets(root):
    """Tickets presentes no projeto, com ou sem Git."""
    import glob
    out = {}
    active = os.path.join(root, ".claude", "current-demand")
    demand = None
    if os.path.isfile(active):
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", demand):
            return {}
    for file in glob.glob(os.path.join(root, "docs/specs/*/issues/*.md")):
        path = os.path.relpath(file, root).replace(os.sep, "/")
        if demand and not path.startswith(f"docs/specs/{demand}/issues/"):
            continue
        with open(file, encoding="utf-8") as stream:
            out[path] = {key.lower(): value.strip() for key, value in FIELD.findall(stream.read())}
    return out


def progress_dir(root):
    """A área de andamento da demanda ativa (`docs/specs/<demanda>/progress/`): ajustes, handoffs e balanço.
    É andamento, não critério: fica fora do hash do critério e não derruba o aceite do dono."""
    import certs
    slug = certs.demand(root)
    return f"docs/specs/{slug}/progress" if slug else None


def adjustments(root):
    """Os ajustes da demanda (`progress/adjust-*.md`), com o passaporte de cada um (Status, Files, Gates)."""
    import glob
    folder = progress_dir(root)
    out = {}
    for file in sorted(glob.glob(os.path.join(root, folder or "-", "adjust-*.md"))):
        with open(file, encoding="utf-8") as stream:
            out[os.path.relpath(file, root).replace(os.sep, "/")] = {
                key.lower(): value.strip() for key, value in FIELD.findall(stream.read())}
    return out


def open_work(root):
    """Tickets e ajustes ainda abertos: enquanto houver, o trem não chegou e a auditoria não começa."""
    pending = [path for path, f in adjustments(root).items() if f.get("status", "").lower() != "done"]
    return open_tickets(root) + pending


def open_tickets(root):
    """Tickets da demanda que ainda não terminaram: enquanto houver, o código é dos executores."""
    return [path for path, fields in tickets(root).items() if fields.get("status", "").lower() != "done"]


def required_gates(root):
    """Portões locais pedidos pelos passaportes dos tickets."""
    return {gate for fields in tickets(root).values()
            for field in ("start", "middle", "gates")
            for gate in (_names(fields.get(field)) or []) if gate.lower() != "none"}


def _names(value):
    if value is None:
        return None
    return [name.strip(" `*") for name in re.split(r"[,;]", value) if name.strip(" `*")]


def _blockers(root, path, value, all_tickets):
    if not value or value.lower() in ("none", "-"):
        return [], []
    folder = os.path.dirname(path)
    indexed = {os.path.basename(p).split("-", 1)[0]: p for p in all_tickets if os.path.dirname(p) == folder}
    found, errors = [], []
    for item in _names(value) or []:
        token = item.split("-", 1)[0].split()[0]
        target = indexed.get(token)
        if target and target != path:
            found.append(target)
        else:
            errors.append(f"{path}: bloqueio `{item}` não aponta para outro ticket da demanda")
    return found, errors


def audit(root, reg):
    """Devolve (pendências, fronteira). Nenhum carimbo é criado aqui."""
    active = os.path.join(root, ".claude", "current-demand")
    if os.path.isfile(active):
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", demand):
            return [".claude/current-demand: slug inválido"], []
    all_tickets = tickets(root)
    if not all_tickets:
        return [], []
    import certs
    if not certs.accepted(root):
        # o critério é do dono: sem o aceite dele sobre o texto atual, nada começa nem se entrega
        return [f"critério da demanda `{certs.demand(root)}` sem aceite do dono (ou mudou depois do aceite): "
                "o dono roda `tr-harness gates --accept`"], []
    problems, graph, completed, ids, entries_ok, plan_ok = [], {}, set(), {}, {}, {}
    integrated = set()
    for path, fields in all_tickets.items():
        first_problem = len(problems)
        ticket_id = (os.path.dirname(path), os.path.basename(path).split("-", 1)[0])
        if ticket_id in ids:
            problems.append(f"{path}: número de ticket duplicado com {ids[ticket_id]}")
        ids[ticket_id] = path
        blockers, errors = _blockers(root, path, fields.get("blocked by"), all_tickets)
        graph[path] = blockers
        problems.extend(errors)
        if "blocked by" not in fields:
            problems.append(f"{path}: falta `Blocked by:`")
        entry = _names(fields.get("start"))
        if entry is None:
            problems.append(f"{path}: falta `Start:` no passaporte")
            entry = []
        if len(entry) == 1 and entry[0].lower() == "none":
            entry = []
        entries_ok[path] = True
        for gate in entry:
            item = reg["gates"].get(gate)
            if not item or item["stage"] != "start":
                problems.append(f"{path}: `{gate}` não é portão de início do registro")
                entries_ok[path] = False
            elif not registry_satisfied(root, gate, reg):
                problems.append(f"{path}: falta carimbo de entrada `{gate}`")
                entries_ok[path] = False
        gates = _names(fields.get("gates"))
        if gates is None:
            problems.append(f"{path}: falta `Gates:` no passaporte")
            gates = []
        if len(gates) == 1 and gates[0].lower() == "none":
            gates = []
        middle = _names(fields.get("middle"))
        if middle is None:
            middle = []
        if len(middle) == 1 and middle[0].lower() == "none":
            middle = []
        status = fields.get("status", "").lower()
        for gate in middle:
            item = reg["gates"].get(gate)
            if not item or item["stage"] != "middle":
                problems.append(f"{path}: `{gate}` não é portão de meio do registro")
            elif status == "done" and not registry_satisfied(root, gate, reg, ticket=path):
                problems.append(f"{path}: falta carimbo de meio `{gate}` para esta versão do ticket")
        for gate in gates:
            item = reg["gates"].get(gate)
            if not item or item["stage"] != "end":
                problems.append(f"{path}: `{gate}` não é portão de fim do registro")
        paths = _names(fields.get("files"))
        if paths is None or not paths:
            problems.append(f"{path}: falta `Files:` no passaporte")
            paths = []
        for pattern in paths:
            if pattern.startswith("/") or ".." in pattern.split("/"):
                problems.append(f"{path}: caminho inválido em `Files:`: {pattern}")
        plan_ok[path] = len(problems) == first_problem
        if status not in ("open", "done"):
            problems.append(f"{path}: `Status:` deve ser open ou done")
            plan_ok[path] = False
        if status != "done":
            problems.append(f"{path}: Status ainda não é done")
            continue
        if len(problems) == first_problem and plan_ok[path]:
            integrated.add(path)  # chegou: libera os dependentes; os portões de fim são da auditoria, na chegada
        import registry
        missing_stamp = []
        # Além dos portões do ticket, os de comando sempre obrigatórios (typecheck, lint, test, build) valem a
        # cada integração: são baratos e apontam o ticket que quebrou. Os de agente (caros) ficam para o fim.
        cheap = [n for n, g in reg["gates"].items()
                 if g["stage"] == "end" and g["signs"] == "command" and g.get("always", True) and n not in gates]
        for gate in gates + cheap:
            if gate in reg["gates"] and reg["gates"][gate]["stage"] == "end" and not registry.satisfied(root, gate, reg):
                problems.append(f"{path}: falta carimbo `{gate}` no estado atual do projeto")
                missing_stamp.append(gate)
        if not missing_stamp and len(problems) == first_problem:
            completed.add(path)
    # Ciclos impedem uma fronteira válida, inclusive se os tickets foram marcados done à força.
    visiting, visited = set(), set()

    def visit(path):
        if path in visiting:
            problems.append(f"{path}: ciclo em `Blocked by:`")
            return
        if path in visited:
            return
        visiting.add(path)
        for blocker in graph[path]:
            visit(blocker)
        visiting.remove(path)
        visited.add(path)

    for path in graph:
        visit(path)
    for a, b, pa, pb in _overlaps(all_tickets, graph):
        problems.append(f"{a}: pode rodar junto com {b} e os dois ocupam `{pa}` / `{pb}`; ponha a parte comum "
                        f"num ticket anterior (ou no scaffold) e faça os dois dependerem dele, ou faça um "
                        f"depender do outro")
        plan_ok[a] = plan_ok[b] = False
    # Um ticket dependente só é concluído quando seus bloqueadores estão carimbados.
    changed = True
    while changed:
        changed = False
        for path in list(completed):
            for blocker in graph[path]:
                if blocker not in completed:
                    problems.append(f"{path}: bloqueador {blocker} ainda não está concluído e carimbado")
                    completed.remove(path)
                    changed = True
                    break
    # A fronteira anda com o que foi integrado (`Status: done`); o certificado de fim só é exigido na entrega.
    changed = True
    while changed:
        changed = False
        for path in list(integrated):
            if any(blocker not in integrated for blocker in graph[path]):
                integrated.remove(path)
                changed = True
    ready = [path for path, blockers in graph.items()
             if all(blocker in integrated for blocker in blockers)
             and plan_ok[path]
             and entries_ok[path]
             and all_tickets[path].get("status", "").lower() != "done"]
    if any("ciclo em `Blocked by:`" in problem for problem in problems):
        ready = []
    return problems, ready


def _area(pattern):
    """Prefixo fixo (em segmentos) de um padrão com curinga ou pasta; None para um arquivo exato."""
    parts = pattern.strip().rstrip("/").split("/")
    if not pattern.endswith("/") and not any(c in pattern for c in "*?["):
        return None
    fixed = []
    for part in parts:
        if any(c in part for c in "*?["):
            break
        fixed.append(part)
    return fixed


def _overlaps(all_tickets, graph):
    """Pares de tickets abertos, sem dependência entre si, que reclamam a mesma área de código.

    Dois executores na mesma área criam cada um a sua versão do mesmo módulo e a integração conflita.
    ponytail: arquivo exato compartilhado (um `app.module.ts`, um `package.json`) não conta: é merge pequeno;
    nomes diferentes para o mesmo conceito escapam e ficam com o planejamento."""
    def ancestors(path, seen=None):
        seen = set() if seen is None else seen
        for blocker in graph.get(path, []):
            if blocker not in seen:
                seen.add(blocker)
                ancestors(blocker, seen)
        return seen

    open_ = sorted(p for p, f in all_tickets.items() if f.get("status", "").lower() != "done")
    areas = {p: [(pat, _area(pat)) for pat in (_names(all_tickets[p].get("files")) or [])] for p in open_}
    above = {p: ancestors(p) for p in open_}
    for i, a in enumerate(open_):
        for b in open_[i + 1:]:
            if a in above[b] or b in above[a]:
                continue
            hit = next(((pa, pb) for pa, x in areas[a] for pb, y in areas[b]
                        if x is not None and y is not None and (x[:len(y)] == y or y[:len(x)] == x)), None)
            if hit:
                yield a, b, *hit


def registry_satisfied(root, name, reg, ticket=None):
    import registry  # evita ciclo: registry.exigidos consulta tickets
    return registry.satisfied(root, name, reg, ticket=ticket)


READ_ONLY_AGENTS = {"Explore", "Plan", "claude-code-guide"}
IN_FLIGHT_TTL = 4 * 3600  # um executor que não voltou em 4 h não segura mais o ticket


def _in_flight_path(root):
    import ledger
    return os.path.join(ledger.state_dir(root), "in-flight.json")


PENDING_TTL = 90  # disparo que não abriu subagente nesse tempo foi negado depois do guard (classificador, outro hook)


def _raw_in_flight(root):
    """{ticket: [início, abriu]}; um número solto (formato antigo) conta como aberto."""
    import json, time
    try:
        with open(_in_flight_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    now = time.time()
    current = set(tickets(root)) | set(adjustments(root))  # um ticket de outra demanda (ou rodada) não ocupa vaga
    live = {}
    for k, v in data.items():
        if isinstance(v, (int, float)):
            v = [v, True]
        if not isinstance(v, list) or len(v) < 2:
            continue
        at, opened, agent = v[0], bool(v[1]), (v[2] if len(v) > 2 else None)
        if k in current and now - at < (IN_FLIGHT_TTL if opened else PENDING_TTL):
            live[k] = [at, opened, agent]
    return live


def _in_flight(root):
    return {k: v[0] for k, v in _raw_in_flight(root).items()}


def executor_opened(root, agent_id=None):
    """SubagentStart: o disparo mais antigo ainda sem subagente ganhou o dele (e o quadro guarda quem é).
    ponytail: casa por ordem, não por ticket (o SubagentStart não traz o pedido); dois disparos na mesma
    mensagem com um negado podem trocar de dono, e o trocado expira em PENDING_TTL."""
    data = _raw_in_flight(root)
    pending = sorted((v[0], k) for k, v in data.items() if not v[1])
    if pending:
        data[pending[0][1]][1] = True
        data[pending[0][1]][2] = agent_id
        _save_in_flight(root, data)


def _save_in_flight(root, data):
    import json
    os.makedirs(os.path.dirname(_in_flight_path(root)), exist_ok=True)
    with open(_in_flight_path(root), "w", encoding="utf-8") as f:
        json.dump(data, f)


STALE_AFTER = 600  # segundos sem nenhuma ferramenta: o subagente aparece como possivelmente parado
# Aceita um prefixo curto que os agentes costumam pôr (`result: DONE: …`, `**DONE:** …`).
REPORT_LINE = re.compile(r"(?m)^\s*(?:[*_`>]+\s*|\w+:\s*)?(DONE|BLOCKED):[*_`]*\s*(\S+)\s*(?:[—-]+\s*)?(.*)$")
EXECUTOR_PROTOCOL = ("\n\nYou work in your own git worktree, which may have been created from another branch. Before "
                     "anything else, bring it to the demand branch `{branch}`: if `git merge-base --is-ancestor "
                     "{branch} HEAD` fails, run `git merge --ff-only {branch}` (or `git reset --hard {branch}` while "
                     "you have no commits of your own). The plan and `.claude/harness.json` must be there before you "
                     "write code. Commit your changes on your branch before finishing. If you stop before the "
                     "ticket is done (blocked, out of time, anything), first write the handoff `{progress}/"
                     "handoff-{name}.md`: what is done (with commits), what is left, why you stopped, your branch and "
                     "the files involved; commit it, so whoever picks it up continues from there. End your final "
                     "message with exactly one line: `DONE: {ticket} — <one-sentence summary>` when the ticket is "
                     "finished, or `BLOCKED: {ticket} — <reason>` when you cannot finish it.")


def protocol(root, ticket):
    import registry
    return EXECUTOR_PROTOCOL.format(ticket=ticket, branch=registry.branch(root),
                                    progress=progress_dir(root) or "docs/specs/<demand>/progress",
                                    name=os.path.splitext(os.path.basename(ticket))[0])


STALE_WAIT = 600  # segundos sem ferramenta: o executor travou e o orquestrador socorre


def wait(root, seconds=540, stale=STALE_WAIT):
    """`tr-harness wait`: a sessão principal vigia o trem enquanto o orquestrador (parado, esperando os
    executores) não pode. Volta quando o trem parou (0: sem executor em voo nem orquestrador ativo), quando um
    executor travou (4: sem ferramenta há `stale` s) ou no fim do prazo (3: ainda rodando)."""
    import time
    deadline = time.time() + seconds
    while True:
        flying = _raw_in_flight(root)
        agents = board(root).get("agents") or {}
        now = time.time()
        import registry
        driving = [a for a, v in agents.items() if v.get("type") in registry.ORCHESTRATORS
                   and now - v.get("last", 0) < stale]
        if not flying and not driving:
            return 0, {"arrived": True}  # nenhum executor em voo e nenhum orquestrador ativo
        stuck = {k: v[2] for k, v in flying.items() if v[1] and v[2] and
                 now - (agents.get(v[2]) or {}).get("last", v[0]) > stale}
        if stuck:
            return 4, {"stuck": stuck, "running": sorted(set(flying) - set(stuck))}
        if time.time() >= deadline:
            return 3, {"running": sorted(flying)}
        time.sleep(5)


def _board_path(root):
    import ledger
    return os.path.join(ledger.state_dir(root), "board.json")


BOARD_AGENT_TTL = 2 * 3600  # subagente sem atividade há mais que isso já acabou (sessão encerrada)


def board(root):
    import json, time
    try:
        with open(_board_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    now = time.time()
    agents = data.get("agents") or {}
    data["agents"] = {k: v for k, v in agents.items() if now - v.get("last", 0) < BOARD_AGENT_TTL}
    return data


def _save_board(root, data):
    import json
    os.makedirs(os.path.dirname(_board_path(root)), exist_ok=True)
    with open(_board_path(root), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def beat(root, agent_id, agent_type):
    """Batimento: o subagente acabou de usar uma ferramenta."""
    import time
    data = board(root)
    data.setdefault("agents", {})[agent_id] = {"type": agent_type, "last": time.time()}
    _save_board(root, data)
    keep_awake(root)


AWAKE_FOR = 30 * 60   # cada pedido mantém a máquina acordada por 30 min
AWAKE_RENEW = 10 * 60  # renovado no batimento depois de 10 min; sem atividade, solta sozinho


def _awake_path(root):
    import ledger
    return os.path.join(ledger.state_dir(root), "awake.json")


def awake_until(root):
    import json
    try:
        with open(_awake_path(root), encoding="utf-8") as f:
            return float(json.load(f).get("until", 0))
    except (OSError, ValueError, AttributeError):
        return 0.0


def _spawn(command):
    import subprocess
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def keep_awake(root):
    """Cafeína: enquanto há subagente trabalhando, a máquina não dorme por ociosidade (tela pode apagar).

    Cada batimento renova um pedido de 30 min ao sistema (`caffeinate` no macOS, `systemd-inhibit` no Linux);
    quando a entrega para, o último pedido expira e a máquina volta ao normal. Desliga com `"keep_awake": false`
    em `.claude/harness.json`. Limite: com a tampa fechada na bateria, o macOS dorme mesmo assim."""
    import json, shutil, sys, time
    if os.environ.get("FULLCHICO_KEEP_AWAKE") == "0":
        return
    try:
        with open(os.path.join(root, ".claude", "harness.json"), encoding="utf-8") as f:
            if json.load(f).get("keep_awake") is False:
                return
    except (OSError, ValueError, AttributeError):
        pass
    now = time.time()
    if awake_until(root) - now > AWAKE_FOR - AWAKE_RENEW:
        return
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        command = ["caffeinate", "-i", "-s", "-t", str(AWAKE_FOR)]
    elif sys.platform.startswith("linux") and shutil.which("systemd-inhibit"):
        command = ["systemd-inhibit", "--what=idle:sleep", "--who=fullchico-harness", "--why=entrega em andamento",
                   "sleep", str(AWAKE_FOR)]
    else:
        return
    try:
        _spawn(command)
    except OSError:
        return
    path = _awake_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"until": now + AWAKE_FOR}, f)


def report(root, agent_id, message):
    """Fim do subagente: grava `DONE:`/`BLOCKED:` do ticket e tira o subagente da lista de ativos."""
    import time
    data = board(root)
    data.get("agents", {}).pop(agent_id, None)
    flying = _raw_in_flight(root)  # o executor em segundo plano terminou: a vaga dele fica livre
    if any(v[2] == agent_id for v in flying.values()):
        _save_in_flight(root, {k: v for k, v in flying.items() if v[2] != agent_id})
    known = list(tickets(root)) + list(adjustments(root))
    for kind, ref, note in REPORT_LINE.findall(message or ""):
        number = ref.strip("`*#").split("-", 1)[0]
        rel = next((p for p in known if p == ref or p.endswith(ref) or ref.endswith(p)
                    or (number.isdigit() and os.path.basename(p).split("-", 1)[0] == number)), None)
        if rel:
            data.setdefault("tickets", {})[rel] = {"state": kind.lower(), "at": time.time(), "note": note.strip()[:200]}
    _save_board(root, data)


def executor_env(ticket):
    """Portas e banco do executor, derivados do número do ticket: executores em paralelo (e outros projetos da
    máquina) não disputam a mesma porta nem o mesmo banco. Ticket 07 → portas 3700–3799, banco `app_t07`."""
    number = os.path.basename(ticket).split("-", 1)[0]
    slot = int(number) if number.isdigit() else 99
    base = 3000 + 100 * slot
    return (f"\n\nYour environment for this ticket: use only ports {base}–{base + 99} (web on {base}, API on "
            f"{base + 1}, test servers inside that range) and the database `app_t{slot:02d}` on the project's "
            f"database server (create it if missing). Read them from environment variables (PORT, API_PORT, "
            f"DATABASE_URL), never hard-code them, and never reuse a server already listening on another port: "
            f"it may belong to another executor or another project. Never stop a process you did not start (the tr hook "
            f"refuses killing processes from outside this project). Before finishing, stop every server you started "
            f"and run `docker compose down` for any compose project you brought up in your worktree.")


def orphan_containers(root):
    """Contêineres de compose cujo diretório é um worktree deste projeto que já não existe.

    Só lê (`docker ps`), e só quando alguém roda `tr-harness status`; quem remove é o dono ou o orquestrador."""
    import json, subprocess
    try:
        out = subprocess.run(["docker", "ps", "-a", "--format", "{{json .}}"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    prefix = os.path.join(os.path.realpath(root), ".claude", "worktrees") + os.sep
    found = []
    for line in out.stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        labels = dict(item.split("=", 1) for item in (row.get("Labels") or "").split(",") if "=" in item)
        folder = labels.get("com.docker.compose.project.working_dir", "")
        if folder.startswith(prefix) and not os.path.isdir(folder):
            found.append(row.get("Names") or row.get("ID"))
    return found


def ticket_refs(root, prompt):
    """Tickets e ajustes citados no pedido (um ajuste é despachado como um ticket)."""
    return [path for path in list(tickets(root)) + list(adjustments(root)) if path in (prompt or "")]


def start_executor(root, prompt):
    """Marca os tickets do pedido como em execução. Devolve o primeiro que já tinha executor, ou None."""
    import time
    data = _raw_in_flight(root)
    refs = ticket_refs(root, prompt)
    busy = next((ref for ref in refs if ref in data), None)
    if busy:
        return busy
    for ref in refs:
        data[ref] = [time.time(), False, None]
    _save_in_flight(root, data)
    return None


def release_if_idle(root):
    """Sessão nova depois de uma queda: se nenhum subagente usou ferramenta há `STALE_AFTER`, ninguém está
    executando; os tickets marcados como em execução são liberados para a retomada. Devolve os liberados."""
    import time
    data = _in_flight(root)
    current = board(root)
    last = max((a.get("last", 0) for a in (current.get("agents") or {}).values()), default=0)
    if time.time() - last < STALE_AFTER:
        return []
    if current.get("agents"):  # os subagentes da sessão que caiu também saem do quadro
        current["agents"] = {}
        _save_board(root, current)
    if data:
        _save_in_flight(root, {})
    return sorted(data)


def finish_executor(root, prompt):
    """O executor voltou (ou o disparo falhou): os tickets do pedido dele ficam livres de novo."""
    data = _raw_in_flight(root)
    for ref in ticket_refs(root, prompt):
        data.pop(ref, None)
    _save_in_flight(root, data)


def dispatch_problem(root, reg, prompt, caller=None, kind=None):
    """Impede iniciar um ticket antes de seus bloqueadores estarem integrados e carimbados.

    Quando quem dispara é o orquestrador, todo executor precisa citar o ticket: sem ele, a fronteira
    não teria o que conferir."""
    all_tickets = tickets(root)
    if not all_tickets:
        return None
    references = [path for path in all_tickets if path in (prompt or "")]
    if not references:
        import registry
        if caller in registry.ORCHESTRATORS and kind not in READ_ONLY_AGENTS and open_tickets(root):
            return "o orquestrador dispara executor só com o caminho do ticket no pedido"
        return None  # exploração e validadores sem ticket seguem livres
    problems, ready = audit(root, reg)
    for path in references:
        if path not in ready:
            plan_problem = next((p for p in problems if p.startswith(path + ":") and
                                 "Status ainda não" not in p), None)
            if plan_problem:
                return plan_problem
            return f"{path}: ticket fora da fronteira; conclua e carimbe os bloqueadores antes de executar"
    return None
