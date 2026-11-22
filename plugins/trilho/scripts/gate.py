#!/usr/bin/env python3
"""O aplicador único dos portões do projeto (`PreToolUse`).

- Envio (`git push`, `gh pr create`) com portão de `fim` faltando: barra.
- Escrita em código (ferramentas de edição, ou o terminal nas formas óbvias) com portão de `inicio`
  faltando: barra, e diz qual etapa cumprir. No terminal é um aviso cedo; a barreira de verdade é a do envio.
- Edição do próprio registro (`.claude/trilho.json`, `.claude/settings.json`): barra. Só o dono muda.
Sem `.claude/trilho.json` ou sem `portoes`, não faz nada.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402

PROTEGIDOS = (".claude/trilho.json", ".claude/settings.json")
EDICAO = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRAPPERS = ledger._WRAPPERS


def deny(root, what, message):
    ledger.log(root, "trilho", "barrou", what[:160])
    print(message, file=sys.stderr)
    return 2


def lista(root, reg, names):
    return "\n".join(f"- {n}: {reg['portoes'][n].get('descricao') or '(sem descrição)'}\n    como: "
                     f"{registry.howto(n, reg['portoes'][n])}" for n in names)


def bash_targets(command):
    """Caminhos que o comando escreve nas formas óbvias: `>`/`>>`, `sed -i`, `tee`, `cp`/`mv`."""
    try:
        parts = ledger._split(command)
    except ValueError:
        return []
    found = []
    for words in parts:
        for i, w in enumerate(words):
            m = re.fullmatch(r"\d*>>?(.*)", w)
            if m:
                target = m.group(1) or (words[i + 1] if i + 1 < len(words) else "")
                if target and not target.startswith("&"):
                    found.append(target)
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if not words:
            continue
        cmd, args = os.path.basename(words[0]), [a for a in words[1:] if not a.startswith(">")]
        plain = [a for a in args if not a.startswith("-")]
        if cmd == "sed" and any(a == "--in-place" or re.fullmatch(r"-[a-zA-Z]*i.*", a) for a in args):
            found += plain[1:]  # o primeiro é o roteiro do sed
        elif cmd == "tee":
            found += plain
        elif cmd in ("cp", "mv") and plain:
            found.append(plain[-1])
    return found


def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") or {}
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        if tool == "Bash" and isinstance(ti.get("command"), str) and ledger.is_send(ti["command"]):
            return deny(root, "registro inválido", f"Envio barrado pelo trilho: o registro de portões está inválido. {e}")
        return 0
    if not reg:
        return 0

    if tool == "Bash":
        command = ti.get("command")
        if not isinstance(command, str):
            return 0
        if ledger.is_send(command):
            faltam = registry.missing(root, "fim", reg)
            if not faltam:
                return 0
            return deny(root, f"envio: {command[:100]}",
                        "Envio barrado pelo trilho: faltam portões de fim para o commit do topo "
                        f"({(ledger.head(root) or '?')[:10]}).\n{lista(root, reg, faltam)}\n"
                        "O carimbo é do commit: commit novo pede os portões de novo.")
        targets = bash_targets(command)
    elif tool in EDICAO:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets = [path] if isinstance(path, str) else []
    else:
        return 0

    for t in targets:
        if registry.relative(root, t) in PROTEGIDOS:
            return deny(root, f"registro: {t}",
                        f"Barrado pelo trilho: `{registry.relative(root, t)}` define os portões que barram você, "
                        "então só o dono o altera, por `fullchico-harness portoes`.")
    for t in targets:
        if registry.is_code(root, t, reg):
            faltam = registry.missing(root, "inicio", reg)
            if faltam:
                return deny(root, f"escrita em código: {t}",
                            f"Escrita em código barrada pelo trilho: falta cumprir a etapa de início antes de "
                            f"escrever em `{registry.relative(root, t)}`.\n{lista(root, reg, faltam)}\n"
                            "Veja o estado com `portao`.")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # sem leitura confiável, não barra por engano
        code = 0
    sys.exit(code)
