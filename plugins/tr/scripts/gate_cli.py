#!/usr/bin/env python3
"""`gate`: lista os portões com o estado, ou roda a verificação de um portão (comando ou artefato).

Não grava carimbo: o sandbox não deixaria, e quem assina é o hook `sign.py`, que lê a última linha
desta saída (`gate <name>: passou`).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402

STAGE = {"start": "início", "middle": "meio (por ticket)", "end": "fim"}


def list_all(root, reg):
    print("Portões deste projeto (os de início, antes de escrever código; os de fim, na entrega):\n")
    top = registry.ledger.head(root)
    request = registry.passport(root, reg)
    required = set(registry.required(root, "end", reg)) | set(registry.required(root, "start", reg))
    task_gates = tasks.required_gates(root)
    for name, gate in reg["gates"].items():
        if gate["stage"] == "middle":
            print(f"[ticket] {name} (meio, carimbo vinculado à versão do ticket)")
            continue
        if name not in required:
            if name in task_gates:
                print(f"[task] {name} ({STAGE[gate['stage']]}, exigido nos passaportes dos tickets indicados abaixo)")
            else:
                print(f"[fora] {name} ({STAGE[gate['stage']]}, fora do passaporte desta demanda)")
            continue
        stamped = registry.stamped_commit(root, name, gate)
        approved = registry.satisfied(root, name, reg)
        desc = f" — {gate['description']}" if gate.get("description") else ""
        print(f"[{'ok' if approved else 'falta'}] {name} ({STAGE[gate['stage']]}, assina por {gate['signs']}){desc}")
        if stamped and not approved:
            print("        validação técnica passou; falta aprovação humana deste estado")
            continue
        if not stamped:
            print(f"        fazer: {registry.howto(name, gate, reg.get('models'), root=root)}")
        elif gate["stage"] == "end" and stamped != top:
            print(f"        carimbo de {stamped[:10]}; depois dele só mudou documentação")
    end_ts = {n for n, g in reg["gates"].items() if g["stage"] == "end"}
    for name in sorted((request or set()) - end_ts):
        print(f"aviso: o passaporte pede `{name}`, que não é portão de fim do registro; ignorado")
    passports, frontier = tasks.audit(root, reg)
    if tasks.tickets(root):
        print("\nPassaportes dos tickets:")
        for item in passports:
            print(f"[falta] {item}")
        if not passports:
            print("[ok] todos os tickets concluídos e carimbados")
        if frontier:
            print("Fronteira liberada: " + ", ".join(frontier))
    if not registry.missing(root, "start", reg) and not registry.missing(root, "end", reg) and not passports:
        print("\nTodos os portões carimbados: a entrega está validada pelo trilho.")
    return 0


def run(command, root, *args):
    sys.stdout.flush()
    return subprocess.run(["bash", "-c", command, "_", *args], cwd=root).returncode


def verify(root, reg, name, ticket=None):
    gate = reg["gates"].get(name)
    if gate is None:
        print(f"gate {name}: FALHOU (portão desconhecido; existem: {', '.join(reg['gates'])})")
        return 2
    if gate["stage"] == "middle" and not ticket:
        print(f"gate {name}: FALHOU (portão de meio exige --ticket <caminho>)")
        return 2
    if gate["stage"] == "middle" and ticket not in tasks.tickets(root):
        print(f"gate {name}: FALHOU (ticket não encontrado no passaporte da demanda)")
        return 2
    if gate["signs"] == "agent":
        print(f"O portão `{name}` só é assinado pelo agente `{gate['agent']}`: "
              f"{registry.howto(name, gate, reg.get('models'), root=root)}.\n"
              "O harness só carimba depois do veredito APPROVED no estado atual.")
        return 2
    if gate["signs"] == "command" and gate["command"] == registry.TO_DEFINE:
        print(f"gate {name}: FALHOU ({registry.howto(name, gate, root=root)})")
        return 2
    if gate["signs"] == "command":
        code, reason_text = run(gate["command"], root), gate["command"]
    else:
        files = registry.artifact_files(root, gate)
        if not files:
            print(f"gate {name}: FALHOU (nenhum arquivo `{gate['artifact']}` encontrado no projeto)")
            return 1
        if registry.dirty(root, files):
            print(f"gate {name}: FALHOU (o artefato tem alteração sem commit: {' '.join(files)})")
            return 1
        code, reason_text = 0, ""
        if gate.get("check"):
            code, reason_text = run(gate["check"] + ' "$@"', root, *files), gate["check"]
    print()
    if code == 0:
        print(f"gate {name}{' ticket ' + ticket if ticket else ''}: passou")
        return 0
    print(f"gate {name}: FALHOU ({reason_text})")
    return 1


def main(argv):
    root = registry.toplevel(os.getcwd())
    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        print(e)
        return 2
    if not reg:
        print("Este projeto não tem portões (.claude/harness.json, chave `gates`).")
        return 1 if argv and argv[0] == "delivery" else 0
    if argv and argv[0] == "delivery":
        missing_gates = registry.missing(root, "start", reg) + registry.missing(root, "end", reg)
        passports, _ = tasks.audit(root, reg)
        for name in missing_gates:
            print(f"[falta] portão `{name}`: {registry.howto(name, reg['gates'][name], reg.get('models'), root=root)}")
        for problem in passports:
            print(f"[falta] {problem}")
        if missing_gates or passports:
            print("Entrega pendente: corrija e execute `gate delivery` novamente.")
            return 1
        print("Entrega validada: portões de início, fim e passaportes concluídos.")
        return 0
    if not argv:
        return list_all(root, reg)
    name = argv[0]
    ticket = None
    if "--ticket" in argv:
        i = argv.index("--ticket")
        if i + 1 >= len(argv) or i != 1:
            print("uso: gate <nome> [--ticket <caminho>]")
            return 2
        ticket = argv[i + 1]
    return verify(root, reg, name, ticket)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
