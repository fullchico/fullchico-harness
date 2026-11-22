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

MOMENTO = {"inicio": "início", "fim": "fim"}


def listar(root, reg):
    print("Portões deste projeto (os de início, antes de escrever código; os de fim, antes de enviar):\n")
    for name, gate in reg["portoes"].items():
        ok = registry.satisfied(root, name, reg)
        desc = f" — {gate['descricao']}" if gate.get("descricao") else ""
        print(f"[{'ok' if ok else 'falta'}] {name} ({MOMENTO[gate['momento']]}, assina por {gate['assina']}){desc}")
        if not ok:
            print(f"        fazer: {registry.howto(name, gate)}")
    return 0


def run(command, root, *args):
    sys.stdout.flush()
    return subprocess.run(["bash", "-c", command, "_", *args], cwd=root).returncode


def verificar(root, reg, name):
    gate = reg["portoes"].get(name)
    if gate is None:
        print(f"portao {name}: FALHOU (portão desconhecido; existem: {', '.join(reg['portoes'])})")
        return 2
    if gate["assina"] == "agente":
        print(f"O portão `{name}` só é assinado pelo agente `{gate['agente']}`: dispare-o sobre o commit do topo.\n"
              "O carimbo nasce do veredito APPROVED dele, não de um comando.")
        return 2
    if gate["assina"] == "comando":
        code, motivo = run(gate["comando"], root), gate["comando"]
    else:
        files = registry.artifact_files(root, gate)
        if not files:
            print(f"portao {name}: FALHOU (nenhum arquivo `{gate['artefato']}` adicionado ou alterado nesta branch, "
                  f"em commit, em relação a {registry.base(root) or 'base'})")
            return 1
        if registry.dirty(root, files):
            print(f"portao {name}: FALHOU (o artefato tem alteração sem commit: {' '.join(files)})")
            return 1
        code, motivo = 0, ""
        if gate.get("valida"):
            code, motivo = run(gate["valida"] + ' "$@"', root, *files), gate["valida"]
    print()
    if code == 0:
        print(f"portao {name}: passou")
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
        return 0
    return verificar(root, reg, argv[0]) if argv else listar(root, reg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
