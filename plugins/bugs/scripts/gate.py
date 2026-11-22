#!/usr/bin/env python3
"""Barra `git push` e `gh pr create` enquanto o commit do topo não tem o carimbo `bugs`."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402


def trilho_aplica(cwd):
    """O projeto tem registro de portões? Então o plugin `trilho` aplica, e este não barra em dobro."""
    try:
        with open(os.path.join(ledger._git(cwd, "rev-parse", "--show-toplevel") or cwd, ".claude", "trilho.json"), encoding="utf-8") as f:
            return "portoes" in json.load(f)
    except (OSError, ValueError, TypeError):
        return False

STAMP = "bugs"
MESSAGE = (
    "Envio barrado pelo plugin bugs: o commit {top} ainda não passou pela caça de bugs.\n"
    "Rode a skill bugs:cacar (ela dispara o agente bugs:cacador sobre este commit). Se ele reprovar,\n"
    "corrija, faça o commit e cace de novo: o carimbo é do commit, e commit novo pede caça nova."
)


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not ledger.is_send(command):
        return 0
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if trilho_aplica(cwd):
        return 0
    top = ledger.head(cwd)
    if not top or ledger.has(cwd, STAMP, top):
        return 0
    ledger.log(cwd, STAMP, "barrou", f"{top[:10]}: {command[:120]}")
    print(MESSAGE.format(top=top[:10]), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # sem leitura confiável, não barra por engano
        code = 0
    sys.exit(code)
