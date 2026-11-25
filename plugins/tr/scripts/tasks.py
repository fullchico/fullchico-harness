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
    problems, graph, completed, ids, entries_ok, plan_ok = [], {}, set(), {}, {}, {}
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
        import registry
        missing_stamp = []
        for gate in gates:
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
    ready = [path for path, blockers in graph.items()
             if all(blocker in completed for blocker in blockers)
             and plan_ok[path]
             and entries_ok[path]
             and all_tickets[path].get("status", "").lower() != "done"]
    if any("ciclo em `Blocked by:`" in problem for problem in problems):
        ready = []
    return problems, ready


def registry_satisfied(root, name, reg, ticket=None):
    import registry  # evita ciclo: registry.exigidos consulta tickets
    return registry.satisfied(root, name, reg, ticket=ticket)


READ_ONLY_AGENTS = {"Explore", "Plan", "claude-code-guide"}


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
