#!/usr/bin/env python3
"""Registra os candidatos `NOTE: <name>` que o `memory:extractor` propôs.

Roda em `SubagentStop` e em `PreToolUse` de `SubagentHandback`: o relatório do subagente pode sair por
um ou por outro. O registro fica no estado do projeto (`~/.claude/tr/<id>/candidates/`), que o
agente com sandbox não grava: `memory note add` só aceita nota nova cujo nome esteja ali.
Nunca bloqueia e nunca quebra.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

AGENT = "memory:extractor"
CANDIDATE = re.compile(r"^NOTE: ([a-z0-9][a-z0-9-]{0,60})$")


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or payload.get("agent_type") != AGENT:
        return
    if payload.get("hook_event_name") == "PreToolUse":
        if payload.get("tool_name") != "SubagentHandback":
            return
        text = (payload.get("tool_input") or {}).get("message")
    else:
        text = payload.get("last_assistant_message")
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    state = ledger.state_dir(cwd) if isinstance(cwd, str) else None
    if not state or not isinstance(text, str):
        return
    names = [m.group(1) for m in (CANDIDATE.match(line.strip()) for line in text.splitlines()) if m]
    if names:
        folder = os.path.join(state, "candidates")
        os.makedirs(folder, exist_ok=True)
        for name in names:
            open(os.path.join(folder, name), "w").close()
        ledger.log(cwd, "memory", "candidates", ", ".join(names))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # um hook de memória nunca derruba a sessão
        pass
    sys.exit(0)
