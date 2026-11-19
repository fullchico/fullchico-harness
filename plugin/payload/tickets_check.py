#!/usr/bin/env python3
"""Valida o grafo de tickets de uma spec e diz o que já pode ser trabalhado.

Cada ticket é um arquivo docs/specs/<slug>/issues/<NN>-<nome>.md. Nas dez
primeiras linhas ele traz `Status: open|claimed|done` e `Blocked by:` com os
números dos tickets que o bloqueiam, separados por vírgula, ou vazio.

Uso: tickets_check.py <pasta da spec> [--frontier]
Sai 0 com `ok: N tickets`; ou, com --frontier, um caminho por linha dos tickets
abertos cujos bloqueadores estão concluídos. Sai 1 com os problemas em stderr.
"""
import os
import re
import sys

sys.dont_write_bytecode = True

STATUSES = ("open", "claimed", "done")
NAME = re.compile(r"^(\d{2})-[a-z0-9][a-z0-9-]*\.md$")
HEADER_LINES = 10


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        head = [next(f, "") for _ in range(HEADER_LINES)]
    status = blocked = None
    for line in head:
        m = re.match(r"^Status:\s*(.*?)\s*$", line)
        if m and status is None:
            status = m.group(1)
        m = re.match(r"^Blocked by:\s*(.*?)\s*$", line)
        if m and blocked is None:
            blocked = m.group(1)
    if status is None or blocked is None:
        raise ValueError(f"{path}: faltam as linhas `Status:` e `Blocked by:` no começo do arquivo")
    if status not in STATUSES:
        raise ValueError(f"{path}: Status `{status}` inválido; use {', '.join(STATUSES)}")
    numbers = []
    for item in filter(None, (part.strip() for part in blocked.split(","))):
        if not item.isdigit():
            raise ValueError(f"{path}: `Blocked by:` aceita só números de ticket; encontrei `{item}`")
        numbers.append(int(item))
    return {"path": path, "status": status, "blocked_by": numbers}


def load(issues_dir: str) -> dict:
    tickets = {}
    for name in sorted(os.listdir(issues_dir)) if os.path.isdir(issues_dir) else []:
        path = os.path.join(issues_dir, name)
        if not name.endswith(".md") or not os.path.isfile(path):
            continue
        m = NAME.match(name)
        if not m:
            raise ValueError(f"{path}: o nome precisa ser <NN>-<nome>.md, com dois dígitos e minúsculas")
        number = int(m.group(1))
        if number in tickets:
            raise ValueError(f"{path}: o número {number:02d} já é usado por {tickets[number]['path']}")
        tickets[number] = _read(path)
    return tickets


def problems(tickets: dict) -> list:
    found = []
    for number, ticket in sorted(tickets.items()):
        for other in ticket["blocked_by"]:
            if other == number:
                found.append(f"ticket {number:02d} está bloqueado por ele mesmo")
            elif other not in tickets:
                found.append(f"ticket {number:02d} é bloqueado pelo {other:02d}, que não existe")
    if found:
        return found
    state = {}  # número -> "visitando" | "pronto"

    def visit(number, trail):
        if state.get(number) == "pronto":
            return None
        if state.get(number) == "visitando":
            return trail[trail.index(number):] + [number]
        state[number] = "visitando"
        for other in tickets[number]["blocked_by"]:
            cycle = visit(other, trail + [number])
            if cycle:
                return cycle
        state[number] = "pronto"
        return None

    for number in sorted(tickets):
        cycle = visit(number, [])
        if cycle:
            return ["ciclo entre os tickets " + " → ".join(f"{n:02d}" for n in cycle)]
    return []


def frontier(tickets: dict) -> list:
    return [number for number, ticket in sorted(tickets.items())
            if ticket["status"] == "open"
            and all(tickets[other]["status"] == "done" for other in ticket["blocked_by"])]


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--frontier"]
    if len(args) != 1:
        sys.stderr.write("uso: tickets_check.py <pasta da spec> [--frontier]\n")
        return 1
    try:
        if not os.path.isdir(args[0]):
            raise ValueError("a pasta da spec não existe")
        tickets = load(os.path.join(args[0], "issues"))
        found = problems(tickets)
    except (ValueError, OSError) as exc:
        found = [str(exc)]
        tickets = {}
    if found:
        for item in found:
            sys.stderr.write(f"grafo de tickets inválido em {args[0]}: {item}\n")
        return 1
    if "--frontier" in sys.argv[1:]:
        for number in frontier(tickets):
            print(tickets[number]["path"])
    else:
        print(f"ok: {len(tickets)} tickets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
