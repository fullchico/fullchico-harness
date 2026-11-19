#!/usr/bin/env python3
"""PreToolUse (Bash): protege o que um agente não pode tocar pela linha de comando.

Neste arquivo: o estado dos portões de push e os atalhos que pulam os hooks de
git. As regras de serviço e de porta entram aqui no plano de ambiente.

Qualquer erro do próprio hook vira negação, nunca liberação.
"""
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DENY_STATE = ("O estado dos portões de push não é alterado por agente. A aprovação nasce do "
              "veredito do revisor; o carimbo manual (.harness/approve) é do dono, no terminal.")
DENY_SKIP = ("Pular os hooks de git (--no-verify, core.hooksPath, HUSKY=) não é permitido a "
             "agentes. Se o push foi negado, corrija o motivo; a exceção é do dono.")
DENY_PARSE = "Comando que o guard não consegue interpretar é negado. Reescreva de forma simples."


def tokenize(command: str):
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def classify(command: str, state):
    if (state and state in command) or "/harness/approvals" in command:
        return DENY_STATE
    try:
        tokens = tokenize(command)
    except ValueError:
        return DENY_PARSE
    in_harness_dir = any(
        tok == "cd" and i + 1 < len(tokens) and tokens[i + 1].rstrip("/").endswith(".harness")
        for i, tok in enumerate(tokens)
    )
    for tok in tokens:
        base = os.path.basename(tok)
        if base == "gate_stamp.py":
            return DENY_STATE
        if base == "approve" and (".harness/" in tok or in_harness_dir):
            return DENY_STATE
        if tok == "--no-verify" or "core.hooksPath" in tok or tok.startswith("HUSKY="):
            return DENY_SKIP
    return None


def main():
    try:
        import json
        payload = json.load(sys.stdin)
    except Exception:
        common.deny("service-guard: entrada do hook inválida; comando negado.")
    if not isinstance(payload, dict):
        common.deny("service-guard: entrada do hook inválida; comando negado.")
    if payload.get("tool_name") != "Bash":
        return
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        common.deny("service-guard: comando ausente na entrada do hook; negado.")
    cwd = payload.get("cwd")
    reason = classify(command, common.state_dir(cwd) if isinstance(cwd, str) else None)
    if reason:
        common.deny(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # falha do guard nunca libera
        common.deny(f"service-guard: erro interno ({exc}); comando negado.")
