#!/usr/bin/env python3
"""Escrita em código pelo efeito, não pelo texto do comando.

O `guard.py` só reconhece formas óbvias de escrita no Bash (`>`, `sed -i`, `tee`, `cp`, `mv`). Um
`python -c`, um script ou um volume do Docker escrevem por outros caminhos. Quando escrever código
não é permitido para quem roda o comando, o `PreToolUse` guarda o estado dos arquivos de código sujos;
o `PostToolUse` compara e, se algum mudou, devolve ao agente o que desfazer. Detecta depois, não impede:
a barreira de verdade nesse caso é o sandbox (perfil `isolado`).
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402


def _path(root, tool_use_id):
    safe = "".join(c for c in str(tool_use_id) if c.isalnum() or c in "-_")[:80]
    return os.path.join(ledger.state_dir(root), "write-watch", safe + ".json") if safe else None


def code_state(root, reg):
    """Hash de cada arquivo de código sujo (modificado, novo ou apagado) segundo o Git."""
    out = subprocess.run(["git", "status", "--porcelain=v1", "-z", "-uall"], cwd=root, capture_output=True)
    if out.returncode:
        return None
    state, entries = {}, out.stdout.decode(errors="replace").split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, rel = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            i += 1  # o nome de origem vem no campo seguinte
        if not registry.is_code(root, rel, reg):
            continue
        full = os.path.join(root, rel)
        try:
            with open(full, "rb") as stream:
                state[rel] = hashlib.sha1(stream.read()).hexdigest()
        except OSError:
            state[rel] = "removido"
    return state


def snapshot(root, reg, tool_use_id, reason):
    """PreToolUse: guarda o estado antes do comando de quem não pode escrever código."""
    path = _path(root, tool_use_id)
    state = code_state(root, reg) if path else None
    if state is None:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump({"reason": reason, "state": state}, stream)


def changed(before, after):
    return sorted(rel for rel in set(before) | set(after) if before.get(rel, "limpo") != after.get(rel, "limpo"))


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    path = _path(root, payload.get("tool_use_id"))
    if not path or not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as stream:
        saved = json.load(stream)
    os.remove(path)
    reg = registry.load(root)
    after = code_state(root, reg) if reg else None
    if after is None:
        return 0
    files = changed(saved["state"], after)
    if not files:
        return 0
    ledger.log(root, "tr", "blocked", f"escrita indireta em código: {', '.join(files[:5])}")
    reason = (f"This command changed code it was not allowed to write ({saved['reason']}): {', '.join(files[:10])}. "
              "Undo these changes now (restore the previous content), then follow the rail: "
              "pass the start gates, or hand the work to an executor with the ticket path.")
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # vigiar nunca derruba a sessão
        pass
    sys.exit(0)
