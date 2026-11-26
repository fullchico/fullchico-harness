#!/usr/bin/env python3
"""`tr-harness balance [--write]`: o balanço da chegada do trem, montado do que está registrado.

Planejado (tickets e ajustes, com o andamento) × chegada (cada portão de fim exigido: certificado, reprovado com o
motivo do revisor, pendente) e as tentativas. Com `--write`, acrescenta ao `progress/balance.md` da demanda (é
andamento, fora do critério); quem fez commit do resto commita junto."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attempts  # noqa: E402
import certs  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402


def balance(root):
    reg = registry.load(root) or {"gates": {}}
    lines = [f"## Chegada de {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "**Planejado**", ""]
    for kind, items in (("ticket", tasks.tickets(root)), ("ajuste", tasks.adjustments(root))):
        for path, fields in items.items():
            lines.append(f"- {kind} `{os.path.basename(path)}`: {fields.get('status', '?')}")
    lines += ["", "**Portões de fim**", ""]
    doc = certs.document(root)
    for name in registry.required(root, "end", reg):
        gate = reg["gates"][name]
        found = [e for e in certs.entries(root, doc) if e["name"] == name]
        tries = attempts.status(root, name, gate)["rejections"]
        if registry.satisfied(root, name, reg):
            state = "certificado"
        elif found and found[-1]["verdict"] == "REJECTED":
            state = f"reprovado: {found[-1]['summary']}"
        else:
            state = "pendente"
        lines.append(f"- `{name}`: {state} (reprovações: {tries}/{gate.get('attempts', 3)})")
    pending = tasks.open_work(root)
    lines += ["", "**Em aberto**: " + (", ".join(f"`{os.path.basename(p)}`" for p in pending) or "nada"), ""]
    return "\n".join(lines)


def main(argv):
    root = registry.toplevel(os.getcwd())
    text = balance(root)
    print(text)
    if "--write" in argv:
        folder = tasks.progress_dir(root)
        if not folder:
            print("sem demanda ativa (.claude/current-demand)", file=sys.stderr)
            return 2
        os.makedirs(os.path.join(root, folder), exist_ok=True)
        with open(os.path.join(root, folder, "balance.md"), "a", encoding="utf-8") as stream:
            stream.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
