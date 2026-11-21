#!/usr/bin/env python3
"""SubagentStart: entrega as regras de execução a quem vai implementar.

Recebem as regras o implementador do harness e os agentes do próprio projeto
(.claude/agents/). Revisores recebem só o pedido de formato fixo, e agentes de
pesquisa ou de outros plugins não têm nada a fazer com regras de implementação.
Nunca bloqueia.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "subagent-rules.md")


def implements(agent, cwd) -> bool:
    if agent == "harness:implementador":
        return True
    if not isinstance(agent, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", agent) or not isinstance(cwd, str):
        return False
    folder = cwd
    while True:  # sobe até achar .claude/agents: a sessão pode estar numa subpasta
        if os.path.isfile(os.path.join(folder, ".claude", "agents", agent + ".md")):
            return True
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        folder = parent


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or not implements(payload.get("agent_type"), payload.get("cwd")):
        return
    with open(RULES, encoding="utf-8") as f:
        rules = f.read().strip()
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": rules}},
                     ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
