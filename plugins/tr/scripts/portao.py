#!/usr/bin/env python3
"""`portao`: lista os portões com o estado, ou roda a verificação de um portão (comando ou artefato).

Não grava carimbo: o sandbox não deixaria, e quem assina é o hook `sign.py`, que lê a última linha
desta saída (`portao <nome>: passou`).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402

MOMENTO = {"inicio": "início", "meio": "meio (por ticket)", "fim": "fim"}


def listar(root, reg):
    print("Portões deste projeto (os de início, antes de escrever código; os de fim, na entrega):\n")
    top = registry.ledger.head(root)
    pedido = registry.passaporte(root, reg)
    exigidos = set(registry.exigidos(root, "fim", reg)) | set(registry.exigidos(root, "inicio", reg))
    task_gates = tasks.required_gates(root)
    for name, gate in reg["portoes"].items():
        if gate["momento"] == "meio":
            print(f"[ticket] {name} (meio, carimbo vinculado à versão do ticket)")
            continue
        if name not in exigidos:
            if name in task_gates:
                print(f"[task] {name} ({MOMENTO[gate['momento']]}, exigido nos passaportes dos tickets indicados abaixo)")
            else:
                print(f"[fora] {name} ({MOMENTO[gate['momento']]}, fora do passaporte desta demanda)")
            continue
        stamped = registry.stamped_commit(root, name, gate)
        desc = f" — {gate['descricao']}" if gate.get("descricao") else ""
        print(f"[{'ok' if stamped else 'falta'}] {name} ({MOMENTO[gate['momento']]}, assina por {gate['assina']}){desc}")
        if not stamped:
            print(f"        fazer: {registry.howto(name, gate, reg.get('modelos'))}")
        elif gate["momento"] == "fim" and stamped != top:
            print(f"        carimbo de {stamped[:10]}; depois dele só mudou documentação")
    fim = {n for n, g in reg["portoes"].items() if g["momento"] == "fim"}
    for name in sorted((pedido or set()) - fim):
        print(f"aviso: o passaporte pede `{name}`, que não é portão de fim do registro; ignorado")
    passaportes, fronteira = tasks.audit(root, reg)
    if tasks.tickets(root):
        print("\nPassaportes dos tickets:")
        for item in passaportes:
            print(f"[falta] {item}")
        if not passaportes:
            print("[ok] todos os tickets concluídos e carimbados")
        if fronteira:
            print("Fronteira liberada: " + ", ".join(fronteira))
    if not registry.missing(root, "inicio", reg) and not registry.missing(root, "fim", reg) and not passaportes:
        print("\nTodos os portões carimbados: a entrega está validada pelo trilho.")
    return 0


def run(command, root, *args):
    sys.stdout.flush()
    return subprocess.run(["bash", "-c", command, "_", *args], cwd=root).returncode


def verificar(root, reg, name, ticket=None):
    gate = reg["portoes"].get(name)
    if gate is None:
        print(f"portao {name}: FALHOU (portão desconhecido; existem: {', '.join(reg['portoes'])})")
        return 2
    if gate["momento"] == "meio" and not ticket:
        print(f"portao {name}: FALHOU (portão de meio exige --ticket <caminho>)")
        return 2
    if gate["momento"] == "meio" and ticket not in tasks.tickets(root):
        print(f"portao {name}: FALHOU (ticket não encontrado no passaporte da demanda)")
        return 2
    if gate["assina"] == "agente":
        print(f"O portão `{name}` só é assinado pelo agente `{gate['agente']}`: "
              f"{registry.howto(name, gate, reg.get('modelos'))}.\n"
              "O harness só carimba depois do veredito APPROVED no estado atual.")
        return 2
    if gate["assina"] == "comando" and gate["comando"] == registry.DEFINIR:
        print(f"portao {name}: FALHOU ({registry.howto(name, gate)})")
        return 2
    if gate["assina"] == "comando":
        code, motivo = run(gate["comando"], root), gate["comando"]
    else:
        files = registry.artifact_files(root, gate)
        if not files:
            print(f"portao {name}: FALHOU (nenhum arquivo `{gate['artefato']}` encontrado no projeto)")
            return 1
        if registry.dirty(root, files):
            print(f"portao {name}: FALHOU (o artefato tem alteração sem commit: {' '.join(files)})")
            return 1
        code, motivo = 0, ""
        if gate.get("valida"):
            code, motivo = run(gate["valida"] + ' "$@"', root, *files), gate["valida"]
    print()
    if code == 0:
        print(f"portao {name}{' ticket ' + ticket if ticket else ''}: passou")
        return 0
    print(f"portao {name}: FALHOU ({motivo})")
    return 1


def main(argv):
    root = registry.toplevel(os.getcwd())
    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        print(e)
        return 2
    if not reg:
        print("Este projeto não tem portões (.claude/trilho.json, chave `portoes`).")
        return 1 if argv and argv[0] == "entrega" else 0
    if argv and argv[0] == "entrega":
        faltam = registry.missing(root, "inicio", reg) + registry.missing(root, "fim", reg)
        passaportes, _ = tasks.audit(root, reg)
        for name in faltam:
            print(f"[falta] portão `{name}`: {registry.howto(name, reg['portoes'][name], reg.get('modelos'))}")
        for problem in passaportes:
            print(f"[falta] {problem}")
        if faltam or passaportes:
            print("Entrega pendente: corrija e execute `portao entrega` novamente.")
            return 1
        print("Entrega validada: portões de início, fim e passaportes concluídos.")
        return 0
    if not argv:
        return listar(root, reg)
    name = argv[0]
    ticket = None
    if "--ticket" in argv:
        i = argv.index("--ticket")
        if i + 1 >= len(argv) or i != 1:
            print("uso: portao <nome> [--ticket <caminho>]")
            return 2
        ticket = argv[i + 1]
    return verificar(root, reg, name, ticket)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
