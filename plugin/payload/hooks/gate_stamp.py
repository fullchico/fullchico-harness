#!/usr/bin/env python3
"""SubagentStop: grava a aprovação de um portão a partir do veredito do revisor.

Nenhum agente carimba. Este hook lê a resposta final do subagente e só grava
quando o subagente é um revisor do harness, o veredito é APPROVED e o commit
revisado é o topo atual. Nunca bloqueia: na dúvida, não carimba e sai 0.
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

AGENT_GATE = {"harness:seguranca": "seguranca", "harness:revisor": "revisao"}
_VERDICT = re.compile(r"^VEREDITO: (APPROVED|REJECTED)$")
_COMMIT = re.compile(r"^COMMIT: ([0-9a-f]{40})$")
_RESUMO = re.compile(r"^RESUMO: (\S.*)$")


def gate_for(agent_type):
    return AGENT_GATE.get(agent_type) if isinstance(agent_type, str) else None


def parse_verdict(message):
    """Só aceita uma linha inteira de cada chave; qualquer ambiguidade vira None."""
    if not isinstance(message, str):
        return None
    found = {"verdict": [], "commit": [], "resumo": []}
    for raw in message.splitlines():
        line = raw.strip()
        for key, pattern in (("verdict", _VERDICT), ("commit", _COMMIT), ("resumo", _RESUMO)):
            m = pattern.match(line)
            if m:
                found[key].append(m.group(1).strip())
    if any(len(values) != 1 for values in found.values()):
        return None
    return {key: values[0] for key, values in found.items()}


def main():
    payload = common.read_payload()
    gate = gate_for(payload.get("agent_type"))
    verdict = parse_verdict(payload.get("last_assistant_message"))
    cwd = payload.get("cwd")
    if not gate or not verdict or not isinstance(cwd, str):
        return
    state = common.state_dir(cwd)
    if not state or verdict["commit"] != common.head_sha(cwd):
        return
    path = common.approval_path(state, gate, verdict["commit"])
    if verdict["verdict"] == "REJECTED":
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "gate": gate,
        "sha": verdict["commit"],
        "status": "PASS",
        "resumo": verdict["resumo"],
        "by": "hook",
        "agent_type": payload.get("agent_type"),
        "transcript": payload.get("agent_transcript_path"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
