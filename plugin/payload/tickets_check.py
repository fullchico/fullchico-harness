#!/usr/bin/env python3
"""Valida o grafo de tickets de uma spec e diz o que já pode ser trabalhado.

Cada ticket é um arquivo docs/specs/<slug>/issues/<NN>-<nome>.md. Nas dez
primeiras linhas ele traz `Status: open|claimed|done`, `Blocked by:` com os
números dos tickets que o bloqueiam, separados por vírgula, ou vazio, e `Owns:`
com as pastas ou arquivos que são só dele.

Um dono por arquivo: dois tickets que podem rodar ao mesmo tempo não possuem o
mesmo caminho. Contrato primeiro: se o harness.conf declara CONTRACT_PATHS, todo
ticket que não possui um caminho de contrato espera os que possuem.

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
    status = blocked = owns = None
    for line in head:
        m = re.match(r"^Owns:\s*(.*?)\s*$", line)
        if m and owns is None:
            owns = m.group(1)
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
    if owns is None:
        raise ValueError(f"{path}: falta a linha `Owns:` no começo do arquivo, com as pastas ou arquivos que são só deste ticket")
    paths = [part.strip().rstrip("/") for part in owns.split(",") if part.strip()]
    if not paths:
        raise ValueError(f"{path}: `Owns:` está vazio; todo ticket é dono de pelo menos um caminho")
    for item in paths:
        if os.path.isabs(item) or ".." in item.split("/") or item in ("", "."):
            raise ValueError(f"{path}: `Owns:` aceita só caminhos relativos dentro do repositório; encontrei `{item}`")
    return {"path": path, "status": status, "blocked_by": numbers, "owns": paths}


def _overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def owned(ticket_path: str) -> list:
    """Os caminhos que um ticket possui. Usado pelo `integrate`."""
    return _read(ticket_path)["owns"]


def contract_paths(spec_dir: str) -> list:
    """CONTRACT_PATHS do harness.conf do repositório a que a spec pertence."""
    folder = os.path.abspath(spec_dir)
    while True:
        conf = os.path.join(folder, "harness.conf")
        if os.path.isfile(conf):
            with open(conf, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"""^CONTRACT_PATHS=["']?(.*?)["']?\s*$""", line.strip())
                    if m:
                        return [p.rstrip("/") for p in m.group(1).split()]
            return []
        parent = os.path.dirname(folder)
        if parent == folder:
            return []
        folder = parent


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


def _ancestors(tickets: dict) -> dict:
    """Para cada ticket, todos os que precisam terminar antes dele."""
    memo = {}

    def walk(number):
        if number not in memo:
            memo[number] = set()
            for other in tickets[number]["blocked_by"]:
                memo[number] |= {other} | walk(other)
        return memo[number]

    return {number: walk(number) for number in tickets}


def _ownership_problems(tickets: dict, contract: list) -> list:
    found = []
    before = _ancestors(tickets)
    numbers = sorted(tickets)
    for i, a in enumerate(numbers):
        for b in numbers[i + 1:]:
            if a in before[b] or b in before[a]:
                continue  # um espera o outro: nunca rodam juntos
            shared = sorted({x if len(x) >= len(y) else y for x in tickets[a]["owns"] for y in tickets[b]["owns"]
                             if _overlap(x, y)})
            if shared:
                found.append(f"os tickets {a:02d} e {b:02d} podem rodar juntos e possuem o mesmo caminho "
                             f"({', '.join(shared)}). Um dono por arquivo: faça um bloquear o outro, ou separe a posse")
    if contract:
        owners = [n for n in numbers if any(_overlap(p, c) for p in tickets[n]["owns"] for c in contract)]
        for number in numbers:
            missing = [c for c in owners if number not in owners and c not in before[number]]
            if missing:
                found.append(f"o ticket {number:02d} não espera o contrato (ticket "
                             f"{', '.join(f'{c:02d}' for c in missing)}). Contrato primeiro: acrescente-o em `Blocked by:`")
    return found


def problems(tickets: dict, contract=None) -> list:
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
    return _ownership_problems(tickets, contract or [])


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
        found = problems(tickets, contract_paths(args[0]))
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
