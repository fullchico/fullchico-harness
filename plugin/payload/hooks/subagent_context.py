#!/usr/bin/env python3
"""SubagentStart: entrega as regras de execução a cada subagente que vai trabalhar.

Os revisores do harness ficam de fora: eles recebem só o pedido de formato fixo,
para que o que leem seja o documento e mais nada. Nunca bloqueia.
"""
import json
import os
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

REVIEWERS = {"harness:seguranca", "harness:revisor", "harness:revisor-spec"}
RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "subagent-rules.md")


def main():
    payload = json.load(sys.stdin)
    agent = payload.get("agent_type") if isinstance(payload, dict) else None
    if not isinstance(agent, str) or agent in REVIEWERS:
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
