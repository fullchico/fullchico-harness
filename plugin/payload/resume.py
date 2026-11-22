#!/usr/bin/env python3
"""Retomada de uma entrega: o estado real de cada ticket que não está concluído na feature.

Cruza três fontes: o arquivo do ticket na feature, as branches dos worktrees de agente e o
estado dos portões. Para cada ticket em andamento diz onde está o trabalho (branch e commit),
em que pé está a revisão e qual é a próxima ação. Só lê: não muda arquivo, branch nem estado.

Uso: resume.py <raiz> <pasta da spec> [--json]
Sai 0 quando consegue ler, 2 para uso errado, 1 se os tickets não puderem ser lidos.

O `dispatch_guard.py` e o `orchestrator_stop.py` usam as mesmas funções, para que o comando e
os trilhos nunca digam coisas diferentes.
"""
import hashlib
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "hooks"))
import common  # noqa: E402
import tickets_check  # noqa: E402

AGENT_REFS = "refs/heads/worktree-agent-*"
IMPLEMENTER = "harness:implementador"
REVIEWER = {"bugs": "harness:revisor-bugs", "ambiente": "harness:revisor-ambiente"}
DEFAULT_TIMEOUT_MIN = 30
_STATUS = re.compile(r"^Status:\s*(.*?)\s*$")


def now() -> int:
    """A hora, em segundos. `HARNESS_NOW` existe para os testes controlarem o relógio."""
    forced = os.environ.get("HARNESS_NOW", "")
    return int(forced) if forced.isdigit() else int(time.time())


def timeout_min(root) -> int:
    """Quanto um despacho pode ficar sem dar sinal antes de ser dito parado (`DISPATCH_TIMEOUT_MIN`)."""
    value = common.read_conf(os.path.join(root, "harness.conf")).get("DISPATCH_TIMEOUT_MIN", "")
    return int(value) if value.isdigit() and int(value) > 0 else DEFAULT_TIMEOUT_MIN


def _minutes(since, when) -> int:
    return max(0, when - since) // 60


def status_at(root, rev, ticket):
    """O `Status:` do ticket num commit; None se o arquivo não existe ali."""
    text = common._git(root, "show", f"{rev}:{ticket}")
    for line in (text or "").splitlines()[:tickets_check.HEADER_LINES]:
        m = _STATUS.match(line)
        if m:
            return m.group(1)
    return None


def claim_commit(root, ticket):
    """O commit da feature em que o ticket chegou ao estado atual (o `claim`, numa retomada).

    É o que separa a tentativa que vale da que foi abandonada: branch de agente que não saiu
    dele é de antes de um `reopen`. Editar o ticket sem mudar o estado (o `Owns:`) não conta.
    """
    for sha in (common._git(root, "log", "--first-parent", "--format=%H", "HEAD", "--", ticket) or "").split():
        if status_at(root, sha, ticket) != status_at(root, sha + "^", ticket):
            return sha
    return None


def agent_branches(root) -> list:
    """As branches dos worktrees de agente, com a ponta, a hora dela e a pasta do worktree."""
    trees, path = {}, None
    for line in (common._git(root, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and path:
            trees[line[len("branch refs/heads/"):]] = path
    found = []
    listed = common._git(root, "for-each-ref", "--format=%(refname:short) %(objectname) %(committerdate:unix)", AGENT_REFS)
    for line in (listed or "").splitlines():
        name, sha, when = line.rsplit(" ", 2)
        found.append({"branch": name, "commit": sha, "time": int(when), "worktree": trees.get(name)})
    return found


def _ahead(root, tip) -> bool:
    count = common._git(root, "rev-list", "--count", f"HEAD..{tip}")
    return bool(count) and count.isdigit() and int(count) > 0


def _descends(root, base, tip) -> bool:
    return bool(base) and common._git(root, "merge-base", base, tip) == base


def attempts(root, ticket, owns=(), claim=None, branches=None):
    """O trabalho que existe para um ticket fora da feature.

    Devolve `(pronto, superadas, em_andamento)`: a branch mais nova que saiu do `claim` atual e
    fechou o ticket; as outras que também o fecharam (mais velhas, ou de antes de um `reopen`);
    e a branch mais nova que saiu do `claim` atual e mexe no que o ticket possui sem tê-lo fechado.
    """
    claim = claim or claim_commit(root, ticket)
    done, old, working = [], [], []
    for item in branches if branches is not None else agent_branches(root):
        tip = item["commit"]
        if not _ahead(root, tip):
            continue
        current = _descends(root, claim, tip)
        if status_at(root, tip, ticket) == "done":
            if current:
                done.append(item)
            elif status_at(root, common._git(root, "merge-base", "HEAD", tip) or tip, ticket) != "done":
                old.append(item)  # foi esta branch que fechou o ticket, numa tentativa anterior
        elif current and owns:
            base = common._git(root, "merge-base", "HEAD", tip)
            changed = (common._git(root, "diff", "--name-only", base, tip) or "").splitlines() if base else []
            if any(name == p or name.startswith(p + "/") for name in changed for p in owns):
                working.append(item)
    newest = lambda items: sorted(items, key=lambda i: (i["time"], i["branch"]), reverse=True)
    done, working = newest(done), newest(working)
    return (done[0] if done else None), done[1:] + newest(old), (working[0] if working else None)


def dispatch_path(state, root, ticket, agent) -> str:
    """Um arquivo por ticket e agente: o despacho novo substitui o anterior."""
    key = hashlib.sha256((os.path.realpath(root) + "\0" + ticket).encode("utf-8")).hexdigest()[:16]
    return os.path.join(state, "dispatches", f"{key}-{agent.split(':')[-1]}.json")


def record_dispatch(root, agent, fields) -> None:
    """Guarda a hora em que um implementador ou revisor foi despachado para um ticket.

    É por aqui que o `resume` distingue "trabalhando" de "parado", e que o orquestrador é
    segurado quando tenta encerrar com filho em andamento.
    """
    state = common.state_dir(root)
    ticket = fields.get("ticket")
    if not state or not ticket:
        return
    record = {"at": now(), "agent": agent, "ticket": ticket, "spec": os.path.dirname(fields["spec"]),
              "root": os.path.realpath(root), "claim": claim_commit(root, ticket), "fix": "achado" in fields}
    if fields.get("commit"):
        named = common._git(root, "for-each-ref", "--format=%(refname:short)", "--points-at", fields["commit"], AGENT_REFS)
        record.update(commit=fields["commit"], branch=(named or "").splitlines()[0] if named else None)
    path = dispatch_path(state, root, ticket, agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
    os.replace(tmp, path)


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_dispatch(root, ticket, agent):
    state = common.state_dir(root)
    record = _load(dispatch_path(state, root, ticket, agent)) if state else None
    return record if record and isinstance(record.get("at"), int) else None


def review(root, gate, tip, ticket, when) -> dict:
    """Em que pé está um portão (`bugs` ou `ambiente`) para a ponta de uma branch de agente."""
    state = common.state_dir(root)
    approval = _load(common.approval_path(state, gate, tip))
    if approval and approval.get("status") == "PASS" and approval.get("gate") == gate and approval.get("sha") == tip:
        return {"state": "approved"}
    path = common.request_path(state, gate, tip)
    request = _load(path)
    if request is None:
        return {"state": "none"}
    if request.get("answer") in ("REJECTED", "PENDINGS"):
        return {"state": request["answer"].lower()}
    record = read_dispatch(root, ticket, REVIEWER[gate])
    asked = record["at"] if record and record.get("commit") == tip else int(os.path.getmtime(path))
    return {"state": "waiting", "age_min": _minutes(asked, when)}


REVIEW_LABEL = {"none": "sem pedido", "approved": "aprovada", "rejected": "reprovada",
                "pendings": "aprovada com pendências demais"}
GATE_LABEL = {"bugs": "caça a bugs", "ambiente": "ambiente"}


def _review_text(gate, found) -> str:
    label = REVIEW_LABEL.get(found["state"]) or f"pedida há {found['age_min']} min, sem resposta"
    return f"{GATE_LABEL[gate]}: {label}"


def ticket_state(root, spec, number, ticket, contract, branches, limit, when) -> dict:
    """O estado de um ticket em andamento e a próxima ação."""
    path = ticket["path"]
    name = os.path.basename(path)[:-3]
    claim = claim_commit(root, path)
    ready, old, working = attempts(root, path, ticket["owns"], claim, branches)
    item = {"ticket": path, "number": number, "name": name, "status": ticket["status"], "contract": contract,
            "branch": None, "commit": None, "base": None, "worktree": None, "working": None, "waiting_min": None,
            "superseded": [{"branch": o["branch"], "commit": o["commit"]} for o in old]}
    reopen = f'.harness/ticket reopen {spec} {number:02d} "<motivo>"'
    sent = read_dispatch(root, path, IMPLEMENTER)
    sent = sent if sent and sent.get("claim") == claim else None  # despacho de antes de um `reopen` não conta
    stalled = lambda minutes, who: (
        "parado", f"{who} há {minutes} min, além do limite de {limit}, sem commit novo nem resposta: confira "
                  f"`.harness/logs` e se há pedido de permissão esperando; depois reabra o ticket ({reopen}) ou "
                  "pare e relate ao dono. Não espere em laço.")

    def running(since, who, wait):
        minutes = _minutes(since, when)
        item["waiting_min"] = minutes
        return stalled(minutes, who) if minutes > limit else ("esperar", f"{who} há {minutes} min: {wait}")

    if ready and sent and sent["at"] > ready["time"]:
        # Rodada de correção despachada depois deste commit: o que vale é o que ela vai trazer.
        item["action"], item["next"] = running(sent["at"], "implementador despachado",
                                               "espere o aviso de término dele.")
    elif ready:
        tip = ready["commit"]
        base = common._git(root, "merge-base", "HEAD", tip)
        item.update(branch=ready["branch"], commit=tip, base=base, worktree=ready["worktree"])
        gates = ("bugs", "ambiente") if contract else ("bugs",)
        for gate in gates:
            item[gate] = review(root, gate, tip, path, when)
        states = {gate: item[gate]["state"] for gate in gates}
        missing = [REVIEWER[g] for g in gates if states[g] == "none"]
        waiting = [item[g]["age_min"] for g in gates if states[g] == "waiting"]
        if "rejected" in states.values() or "pendings" in states.values():
            item["action"], item["next"] = "corrigir", (
                f"rodada de correção: grave o achado em {spec}/achados/, reabra ({reopen}), pegue o ticket de "
                f"novo e despache o implementador com `achado:`, dizendo no achado a branch {ready['branch']}.")
        elif missing:
            item["action"], item["next"] = "revisar", (
                f"despache {' e '.join(missing)} com `ticket: {path}`, `diff: {base}...{tip}` e `commit: {tip}`.")
        elif waiting:
            item["waiting_min"] = max(waiting)
            item["action"], item["next"] = (
                stalled(max(waiting), "revisão pedida") if max(waiting) > limit
                else ("esperar", f"revisão pedida há {max(waiting)} min: espere o aviso do revisor, "
                                 "não peça outra do mesmo commit."))
        else:
            item["action"], item["next"] = "integrar", f".harness/integrate {path} {ready['branch']}"
    elif sent or working:
        if working:
            item.update(working=working["branch"], worktree=working["worktree"])
        since = max([sent["at"]] if sent else [], default=0)
        since = max(since, working["time"] if working else 0)
        who = "implementador despachado" if sent and since == sent["at"] else f"último commit em {working['branch']}"
        item["action"], item["next"] = running(since, who, "espere o aviso de término dele.")
    else:
        item["action"], item["next"] = "despachar", (
            "nenhum commit deste ticket em lugar nenhum: despache o implementador (o ticket já está `claimed`).")
    return item


def report(root, spec) -> dict:
    """O retrato da entrega de uma spec. `spec` é a pasta, relativa à raiz do repositório."""
    tickets = tickets_check.load(os.path.join(root, spec, "issues"))
    for ticket in tickets.values():
        ticket["path"] = os.path.relpath(ticket["path"], root).replace(os.sep, "/")
    contract = tickets_check.contract_paths(os.path.join(root, spec))
    branches, limit, when = agent_branches(root), timeout_min(root), now()
    is_contract = lambda t: any(tickets_check._overlap(o, c) for o in t["owns"] for c in contract)
    return {
        "spec": spec,
        "feature": common._git(root, "branch", "--show-current"),
        "timeout_min": limit,
        "done": sum(1 for t in tickets.values() if t["status"] == "done"),
        "open": sum(1 for t in tickets.values() if t["status"] == "open"),
        "frontier": [tickets[n]["path"] for n in tickets_check.frontier(tickets)],
        "tickets": [ticket_state(root, spec, n, t, is_contract(t), branches, limit, when)
                    for n, t in sorted(tickets.items()) if t["status"] == "claimed"],
    }


def running(root) -> list:
    """Tickets desta feature com agente em andamento, dentro do tempo limite: o que o orquestrador tem de esperar."""
    state = common.state_dir(root)
    folder = os.path.join(state, "dispatches") if state else ""
    limit, when, here = timeout_min(root) * 60, now(), os.path.realpath(root)
    specs = set()
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        record = _load(os.path.join(folder, name)) if name.endswith(".json") else None
        if (record and record.get("root") == here and isinstance(record.get("at"), int)
                and when - record["at"] <= limit and isinstance(record.get("spec"), str)):
            specs.add(record["spec"])
    found = []
    for spec in sorted(specs):
        try:
            found += [t for t in report(root, spec)["tickets"] if t["action"] == "esperar"]
        except (ValueError, OSError):
            continue
    return found


def render(data) -> str:
    claimed = data["tickets"]
    lines = [f"Retomada de {data['spec']} (branch {data['feature'] or '?'}): {data['done']} concluído(s), "
             f"{len(claimed)} em andamento, {data['open']} aberto(s). Limite por despacho: {data['timeout_min']} min.", ""]
    for item in claimed:
        lines.append(f"{item['name']}: {item['action']}")
        if item["commit"]:
            where = f"  trabalho pronto em {item['branch']}, commit {item['commit']}"
            lines.append(where + "".join(f"; {_review_text(g, item[g])}" for g in ("bugs", "ambiente") if g in item))
        elif item["working"]:
            lines.append(f"  em andamento em {item['working']}")
        for old in item["superseded"]:
            lines.append(f"  tentativa superada: {old['branch']}, commit {old['commit']} "
                         f"(descarte com `.harness/agents-clean --discard {old['branch']}`)")
        lines.append(f"  → {item['next']}")
        lines.append("")
    if not claimed:
        lines += ["Nenhum ticket em andamento.", ""]
    names = ", ".join(os.path.basename(p)[:-3] for p in data["frontier"]) or "nenhum"
    lines.append(f"Abertos: {data['open']}. Fronteira (podem ser pegos agora): {names}.")
    return "\n".join(lines) + "\n"


def main(argv) -> int:
    usage = "uso: resume <pasta da spec> [--json]\n"
    args = [a for a in argv if a != "--json"]  # a raiz do repositório, que o script de entrada passa, e a pasta da spec
    if not argv or len(args) != 2 or args[1].startswith("-"):
        sys.stderr.write(usage)
        return 2
    root = os.path.realpath(args[0])
    target = os.path.realpath(os.path.join(os.getcwd(), args[1]))
    if os.path.isfile(target):
        target = os.path.dirname(target)  # o caminho da spec também serve
    if not os.path.isdir(target) or not (target + os.sep).startswith(root + os.sep) or target == root:
        sys.stderr.write(f"resume: {args[1]} não é a pasta de uma spec deste repositório.\n{usage}")
        return 2
    try:
        data = report(root, os.path.relpath(target, root).replace(os.sep, "/"))
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"resume: não consegui ler os tickets: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n" if "--json" in argv else render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
