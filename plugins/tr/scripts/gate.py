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
import saida  # noqa: E402
from saida import quadro  # noqa: E402

PROTEGIDOS = (".claude/trilho.json", ".claude/settings.json")
EDICAO = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRAPPERS = ledger._WRAPPERS


def deny(root, what, message):
    ledger.log(root, "trilho", "barrou", what[:160])
    return saida.barrar(message)


def lista(reg, names):
    linhas = []
    for n in names:
        gate = reg["portoes"][n]
        linhas.append(f"  ✗ {n} · {gate.get('descricao') or '(sem descrição)'}")
        linhas += [f"    → {p}" for p in registry.passos(n, gate)]
    return linhas


# BSD: `sed -i '' 's/a/b/' alvo`; GNU: `sed -i 's/a/b/' alvo` ou `sed -i.bak ...`.
_SED_INPLACE = re.compile(r"\bsed\s+-i\S*\s+(?:\S+\s+)+?(\S+?)\s*(?:$|[;|&\n])")


def bash_targets(command):
    """Caminhos que o comando escreve nas formas óbvias: `>`/`>>`, `sed -i`, `tee`, `cp`/`mv`.

    O corpo de um heredoc é texto do arquivo, não comando: um `.md` que cita `> apps/x.ts` não escreve em `apps/`.
    """
    command = ledger.strip_heredocs(command)
    try:
        parts = ledger._split(command)
    except ValueError:
        return []
    found = _SED_INPLACE.findall(command)
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
    # O arquivo de portões é protegido sempre, mesmo sem registro ainda: o agente não cria um
    # registro fraco por conta própria. Só o plugin tr (os scripts do dono) escreve ali.
    if tool in EDICAO:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets_pre = [path] if isinstance(path, str) else []
    elif tool == "Bash" and isinstance(ti.get("command"), str):
        targets_pre = bash_targets(ti["command"])
    else:
        targets_pre = []
    for t in targets_pre:
        if registry.relative(root, t) == ".claude/trilho.json":
            return deny(root, f"registro: {t}", quadro("registro protegido", [
                ("arquivo", ".claude/trilho.json"),
                ("motivo", "só o dono altera, por `fullchico-harness portoes` no terminal"),
            ], rodape="o plugin tr escreve ali; o agente não"))

    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        if tool == "Bash" and isinstance(ti.get("command"), str) and ledger.is_send(ti["command"]):
            return deny(root, "registro inválido", quadro("envio barrado", [
                ("registro", ".claude/trilho.json"), ("motivo", f"registro de portões inválido: {e}")]))
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
            return deny(root, f"envio: {command[:100]}", quadro("envio barrado", [
                ("commit", (ledger.head(root) or "?")[:10]), ("motivo", "faltam portões de fim"),
            ], lista(reg, faltam), "o carimbo é do commit: commit novo pede os portões de novo · estado: `portao`"))
        targets = bash_targets(command)
    elif tool in EDICAO:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets = [path] if isinstance(path, str) else []
    else:
        return 0

    for t in targets:
        if registry.relative(root, t) == ".claude/settings.json":
            return deny(root, f"registro: {t}", quadro("registro protegido", [
                ("arquivo", ".claude/settings.json"),
                ("motivo", "só o dono altera: ele liga os plugins que barram você"),
            ], rodape="o dono muda no terminal (`fullchico-harness install`, `fullchico-harness portoes`) ou à mão"))
    for t in targets:
        if registry.is_code(root, t, reg):
            faltam = registry.missing(root, "inicio", reg)
            if faltam:
                return deny(root, f"escrita em código: {t}", quadro("escrita barrada", [
                    ("arquivo", registry.relative(root, t)), ("motivo", "falta a etapa de início"),
                ], lista(reg, faltam), "estado: `portao`"))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # sem leitura confiável, não barra por engano
        code = 0
    sys.exit(code)
